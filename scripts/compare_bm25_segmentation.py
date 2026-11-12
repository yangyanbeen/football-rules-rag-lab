"""Supplemental dev-only accurate/search comparison after the immutable B0 run."""
from __future__ import annotations
import argparse,json,re,time,unicodedata,uuid,subprocess
from pathlib import Path
from bm25_index import (ROOT,Tokenizer,chinese_number,corpus,payload_for,rank,normalize,
                        SOURCE_FIELDS,TIMINGS,record,write_new,committed,RESOURCES)
from bm25_retrieval_eval import (now,summary,validate_predictions,replay,V1_EXECUTION_FILES,
                                instant,finite,producer_before,validate_identity)
from eval_dataset import EVAL,digest,load_jsonl,canonical

SOURCES=V1_EXECUTION_FILES+('scripts/compare_bm25_segmentation.py',)


class SearchTokenizer(Tokenizer):
    def tokens(self,text):
        text=' '.join(unicodedata.normalize('NFKC',text).casefold().split());result=[]
        for value in re.findall(r'第\s*(?:\d+|[零一二三四五六七八九十]+)\s*条|\d+(?:\.\d+)?|[a-z]+|[\u3400-\u9fff]+',text):
            if value.startswith('第') and value.endswith('条'):
                number=chinese_number(re.sub(r'\s','',value)[1:-1]);result.extend(['rule:'+str(number),str(number)])
            elif re.fullmatch(r'\d+(?:\.\d+)?|[a-z]+',value):result.append(value)
            else:result.extend(t for t in self.engine.cut_for_search(value,HMM=False) if t.strip() and t not in self.stop)
        return result


def replay_comparison(directory):
    directory=Path(directory).resolve()
    if (directory/'failure.json').exists():raise ValueError('Failed supplemental run')
    m=json.loads((directory/'manifest.json').read_text('utf-8'))
    fields={'version','run_id','split','mode','HMM','source_commit','sources','inputs','index',
            'started_at','completed_at','wall_seconds','warmups','test_questions_read','new_test_runs','artifacts'}
    if (set(m)!=fields or m['version']!='bm25-segmentation-dev-1.0' or m['split']!='dev'
        or m['mode']!='search' or m['HMM'] is not False or m['test_questions_read'] is not False
        or type(m['new_test_runs']) is not int or m['new_test_runs']!=0):
        raise ValueError('Supplement is development only')
    validate_identity(m['split'],'title_body',m['run_id'])
    producer_before(m['source_commit'],m['started_at'])
    start,end=instant(m['started_at']),instant(m['completed_at'])
    if end<start or not finite(m['wall_seconds']):raise ValueError('Invalid supplement times')
    if set(m['artifacts'])!={'predictions.jsonl','summary.json','comparison.json'}:raise ValueError('Incomplete supplement artifacts')
    for name,entry in m['artifacts'].items():
        if record(directory/name)!=entry:raise ValueError('Supplement artifact hash mismatch')
    if set(m['sources'])!=set(SOURCES):raise ValueError('Incomplete supplement sources')
    for name,entry in m['sources'].items():
        raw=subprocess.check_output(['git','show',m['source_commit']+':'+name],cwd=ROOT)
        if entry!={'path':name,'sha256':digest(raw),'size_bytes':len(raw)}:raise ValueError('Supplement source provenance differs')
    if set(m['inputs'])!=set(RESOURCES+('data/eval/retrieval_dev.jsonl',)):raise ValueError('Incomplete supplement inputs')
    for path,entry in m['inputs'].items():
        if record(ROOT/path)!=entry:raise ValueError('Supplement development/resources changed')
    questions=load_jsonl(EVAL/'retrieval_dev.jsonl');pred=load_jsonl(directory/'predictions.jsonl')
    source=json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8'))
    validate_predictions(questions,pred,source,'dev','title_body',m['run_id'])
    current=summary(questions,pred,'title_body','dev',m['run_id'])
    saved=json.loads((directory/'summary.json').read_text('utf-8'))
    if canonical(current)!=canonical(saved):raise ValueError('Supplement summary differs from raw measurements')
    if not isinstance(m['warmups'],list) or len(m['warmups'])!=3:raise ValueError('Three supplement warmups required')
    for t in m['warmups']:
        if (not isinstance(t,dict) or set(t)!=set(TIMINGS) or any(not finite(t[k]) for k in TIMINGS)
            or abs(t['total_seconds']-sum(t[k] for k in TIMINGS[:-1]))>1e-8):raise ValueError('Invalid supplement warmup timing')
    measured=sum(v['total_seconds'] for row in pred for v in row['measurements'])+sum(t['total_seconds'] for t in m['warmups'])
    if m['wall_seconds']+1e-6<measured or (end-start).total_seconds()+.1<m['wall_seconds']:raise ValueError('Supplement wall timing omits work')
    original=json.loads((ROOT/'reports/retrieval/bm25_b0/segmentation-dev/manifest.json').read_text('utf-8'))
    index=m['index'];path=Path(index['path'])
    if (set(index)!={'path','sha256','size_bytes'} or path.is_absolute() or '..' in path.parts
        or not (ROOT/path).resolve().is_relative_to(ROOT/'data/indexes/bm25-search-dev')
        or path.name!='index.json' or any(canonical(index[k])!=canonical(original['index'][k]) for k in ('sha256','size_bytes'))):
        raise ValueError('Supplement deterministic index identity differs')
    accurate=replay(ROOT/'reports/retrieval/bm25_b0/development/title_body')
    expected=comparison_for(accurate,current,{'rule':True,'decimal':True,'mode_is_distinct':True})
    if canonical(json.loads((directory/'comparison.json').read_text('utf-8')))!=canonical(expected):raise ValueError('Comparison differs from saved measurements and fixed policy')
    return current


def comparison_for(accurate,search,token_checks):
    return {'scope':'Exploratory development-only comparison performed after the B0 test; not prior selection evidence',
            'accurate':{'metrics':accurate['quality']['metrics'],'latency':accurate['latency']['all']['total_seconds']},
            'search':{'metrics':search['quality']['metrics'],'latency':search['latency']['all']['total_seconds']},
            'formal_b0_mode':'accurate','formal_b0_and_test_unchanged':True,'new_test_runs':0,
            'numeric_rule_and_term_checks':token_checks}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--replay-only',action='store_true');a=p.parse_args();out=a.output_dir.resolve()
    if not out.is_relative_to(ROOT/'reports/retrieval'):raise ValueError('Use a reports/retrieval directory')
    if a.replay_only:
        s=replay_comparison(out);print(json.dumps({'status':'PASS','metrics':s['quality']['metrics']}));return
    if out.exists():raise ValueError('Preserve prior development comparison')
    commit=committed(SOURCES+RESOURCES);started=now();wall=time.perf_counter()
    tokenizer=SearchTokenizer();rows=corpus();payload=payload_for(rows,'title_body',tokenizer)
    run_id=uuid.uuid4().hex
    indexdir=ROOT/'data/indexes/bm25-search-dev'/run_id/'title_body'
    if indexdir.exists():raise ValueError('Preserve the supplemental index')
    write_new(indexdir/'index.json',payload)
    sources=[{k:r[k] for k in SOURCE_FIELDS} for r in rows];by_id={r['chunk_id']:r for r in sources}
    def query(question):
        s=time.perf_counter_ns();q=normalize(question);a=time.perf_counter_ns()
        tokens=tokenizer.tokens(q);b=time.perf_counter_ns()
        ranked=[{**r,**by_id[r['chunk_id']]} for r in rank(payload,tokens)];e=time.perf_counter_ns()
        return q,tokens,ranked,dict(zip(TIMINGS,((a-s)/1e9,(b-a)/1e9,(e-b)/1e9,(e-s)/1e9)))
    warmups=[query('足球比赛场地的边线如何判断球出界？')[3] for _ in range(3)]
    questions=load_jsonl(EVAL/'retrieval_dev.jsonl');predictions=[]
    out.mkdir(parents=True,exist_ok=False)
    with (out/'predictions.jsonl').open('x',encoding='utf-8',newline='\n') as f:
        for question in questions:
            measures=[];first=None
            for rep in range(1,4):
                value=query(question['question']);first=first or value
                measures.append({'repetition':rep,'ranked_ids':[r['chunk_id'] for r in value[2]],'scores':[r['score'] for r in value[2]],**value[3]})
            row={'question_id':question['question_id'],'question_sha256':digest(question['question'].encode()),'query':first[0],
                 'query_tokens':first[1],'split':'dev','template':'title_body','run_id':run_id,'results':first[2],'measurements':measures}
            f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');f.flush();predictions.append(row)
    s=summary(questions,predictions,'title_body','dev',run_id);write_new(out/'summary.json',s)
    accurate=replay(ROOT/'reports/retrieval/bm25_b0/development/title_body')
    comparison=comparison_for(accurate,s,{'rule':tokenizer.tokens('第十一条')==['rule:11','11'],
                    'decimal':'7.32' in tokenizer.tokens('７．３２米'),'mode_is_distinct':tokenizer.tokens('间接任意球')!=Tokenizer().tokens('间接任意球')})
    write_new(out/'comparison.json',comparison)
    manifest={'version':'bm25-segmentation-dev-1.0','run_id':run_id,'split':'dev','mode':'search','HMM':False,
              'source_commit':commit,'sources':{p:record(ROOT/p) for p in SOURCES},
              'inputs':{p:record(ROOT/p) for p in RESOURCES+('data/eval/retrieval_dev.jsonl',)},
              'index':record(indexdir/'index.json'),'started_at':started,'completed_at':now(),
              'wall_seconds':time.perf_counter()-wall,'warmups':warmups,'test_questions_read':False,'new_test_runs':0,
              'artifacts':{n:record(out/n) for n in ('predictions.jsonl','summary.json','comparison.json')}}
    committed(SOURCES+RESOURCES,commit)
    write_new(out/'manifest.json',manifest);replay_comparison(out)
    print(json.dumps({'status':'COMPLETE','scope':'dev only; original test unchanged','comparison':comparison},ensure_ascii=False))

if __name__=='__main__':main()
