"""Lossless paragraph children and coherent parents; original Corpus B0 is read-only."""
import argparse,collections,importlib.metadata,json,re,statistics
from pathlib import Path
from eval_dataset import ROOT,canonical,digest,source_ref
from bm25_index import corpus,record,write_new,committed
from bm25_retrieval_eval import now

CONFIG='config/structure_parent_child.json'
MAP='data/manifests/structure_parent_child.json'
DATA='data/processed/rag_chunks_parent_child.jsonl'
STATS='reports/chunking_structure.json'
AUDIT='reports/structure_preservation.json'
MARKERS=('如果','但是','除外','不得','必须','只有','除非','例外')


def config():
    value=json.loads((ROOT/CONFIG).read_text('utf-8'))
    if (type(value['child_max_body_tokens']) is not int or value['child_max_body_tokens']!=256
        or value['methods']!=['base','child','parent_child'] or value['context_token_budget']!=4096
        or value['tokenizers_version']!='0.22.1' or value['channel_top_k']!=80 or value['rrf_k']!=60
        or value['reranker'] is not False or value['cache'] is not False):raise ValueError('Fixed Task11 policy differs')
    return value


def tokenizer():
    cfg=config()
    from bge_reranker import HOME,file_sha
    from tokenizers import Tokenizer
    if importlib.metadata.version('tokenizers')!=cfg['tokenizers_version']:raise ValueError('Tokenizer package differs')
    if HOME.name!=cfg['tokenizer_revision'] or file_sha(HOME/'tokenizer.json')!=cfg['tokenizer_json_sha256']:raise ValueError('Tokenizer artifact differs')
    value=Tokenizer.from_file(str(HOME/'tokenizer.json'));value.no_padding();value.no_truncation();return value


def count(tok,text):return len(tok.encode(text,add_special_tokens=False).ids)


def split_spans(text,tok,limit=256,table=False):
    if type(limit) is not int or limit<1 or not isinstance(text,str) or not text:raise ValueError('Positive limit and nonempty body required')
    if table or count(tok,text)<=limit:return [(0,len(text))]
    # Delimiters belong to the preceding paragraph: concatenation is byte exact.
    ends=[m.end() for m in re.finditer(r'\n(?:[ \t]*\n)+',text)]
    if not ends or ends[-1]!=len(text):ends.append(len(text))
    spans=[];start=0;previous=0
    for end in ends:
        if previous>start and count(tok,text[start:end])>limit:
            spans.append((start,previous));start=previous
        previous=end
    if start<len(text):spans.append((start,len(text)))
    return spans


def distribution(values):
    values=sorted(values)
    if not values:raise ValueError('Empty distribution')
    pos=.95*(len(values)-1);lo=int(pos);hi=min(lo+1,len(values)-1)
    return {'count':len(values),'mean':sum(values)/len(values),'median':statistics.median(values),
            'P95':values[lo]+(values[hi]-values[lo])*(pos-lo),'min':values[0],'max':values[-1]}


def describe(entries):
    values=list(entries.values());hashes=[r['content_sha256'] for r in values]
    return {'chunks':len(values),'characters':distribution([r['characters'] for r in values]),
            'body_tokens':distribution([r['body_tokens'] for r in values]),
            'serialized_context_tokens':distribution([r['context_tokens'] for r in values]),
            'exact_duplicate_rate':(len(hashes)-len(set(hashes)))/len(hashes)}


def derive(rows,tok,cfg):
    originals={};children={};parents={};private=[];groups=collections.defaultdict(list);audit=[]
    for row in rows:
        key=(row['document_id'],tuple(row['section_path'][:2]));groups[key].append(row)
    def entry(cid,body,path,spans,**extra):
        text=' / '.join(path)+'\n\n'+body
        return {'chunk_id':cid,'section_path':path,'characters':len(body),'body_tokens':count(tok,body),
                'context_tokens':count(tok,text+'\n\n'),'content_sha256':digest(body.encode()),
                'passage_sha256':digest(text.encode()),'spans':spans,**extra}
    for key,members in groups.items():
        path=list(key[1]);pid='P%02d-'%members[0]['law_number']+digest(canonical(key))[:12]
        pbody='\n\n'.join('### '+r['title_zh']+'\n'+r['content_zh'] for r in members)
        pspans=[{'original_id':r['chunk_id'],'start':0,'end':len(r['content_zh'])} for r in members]
        parents[pid]=entry(pid,pbody,path,pspans,original_ids=[r['chunk_id'] for r in members],law_number=members[0]['law_number'])
        private.append({'kind':'parent',**parents[pid],'content_zh':pbody,'sources':[source_ref(r) for r in members]})
        for row in members:
            cid=row['chunk_id'];body=row['content_zh'];path=row['section_path'];limit=cfg['child_max_body_tokens']
            original_span=[{'original_id':cid,'start':0,'end':len(body)}]
            originals[cid]=entry(cid,body,path,original_span,parent_id=pid,title_zh=row['title_zh'],
                                 chunk_type=row['chunk_type'],law_number=row['law_number'],source=source_ref(row))
            spans=split_spans(body,tok,limit,row['chunk_type']=='table');parts=[];child_ids=[]
            for i,(a,b) in enumerate(spans,1):
                text=body[a:b];child_id=cid+'-C%02d-'%i+digest(text.encode())[:8]
                metadata=entry(child_id,text,path,[{'original_id':cid,'start':a,'end':b}],original_id=cid,parent_id=pid,
                               law_number=row['law_number'],title_zh=row['title_zh'],chunk_type=row['chunk_type'],
                               oversize_atomic=count(tok,text)>limit)
                children[child_id]=metadata;parts.append(text);child_ids.append(child_id)
                private.append({'kind':'child',**metadata,'content_zh':text,'sources':[source_ref(row)]})
            if ''.join(parts)!=body:raise ValueError('Lossless reconstruction failed')
            audit.append({'original_id':cid,'children':child_ids,'child_spans':spans,'lossless':True,
                          'conditions_and_exceptions_counts':{s:body.count(s) for s in MARKERS},
                          'reassembled_marker_counts':{s:''.join(parts).count(s) for s in MARKERS},
                          'table_atomic':row['chunk_type']!='table' or len(spans)==1,
                          'original_title_and_rule_preserved':all(children[x]['section_path']==path and children[x]['law_number']==row['law_number'] for x in child_ids)})
    if len({r['chunk_id'] for r in private})!=len(private):raise ValueError('Derived ID collision')
    mapping={'version':'structure-parent-child-map-1.0','originals':originals,'children':children,'parents':parents,
             'tokenizer':{k:cfg[k] for k in ('tokenizer_model','tokenizer_revision','tokenizer_json_sha256','tokenizers_version','special_tokens')},
             'source_corpus':record(ROOT/'data/processed/rag_chunks_zh.jsonl'),'config':record(ROOT/CONFIG),
             'body_distribution':'local-only; public map contains metadata, intervals and hashes only'}
    stats={'version':'structure-character-token-distributions-1.0','base':describe(originals),'child':describe(children),'parent':describe(parents),
           'overlong_originals':sum(r['body_tokens']>limit for r in originals.values()),
           'split_originals':sum(len(r['children'])>1 for r in audit),
           'oversize_atomic_children':[r['chunk_id'] for r in children.values() if r['oversize_atomic']],
           'definition':'Body characters and fixed tokenizer tokens; full serialized context including headings and trailing delimiters is reported separately. Duplicate rate counts excess identical body hashes within each layer.'}
    structural={'version':'structure-preservation-1.0','status':'PASS','samples':audit,
                'checks':{'all_originals_reassemble_exactly':all(r['lossless'] for r in audit),
                          'all_titles_rules_retained':all(r['original_title_and_rule_preserved'] for r in audit),
                          'all_marker_counts_retained':all(r['conditions_and_exceptions_counts']==r['reassembled_marker_counts'] for r in audit),
                          'complete_table_atomic':all(r['table_atomic'] for r in audit)},
                'scope':'All original units checked mechanically; marker equality and exact bytes are not expert factual/translation review.'}
    return private,mapping,stats,structural


def build():
    outputs=[ROOT/p for p in (DATA,MAP,STATS,AUDIT)]
    if any(p.exists() for p in outputs):raise FileExistsError('Keep existing derived corpus and reports; use a new version')
    source=committed(('scripts/structure_aware_chunking.py',CONFIG,'docs/TASK_11_SCOPE.md'))
    private,mapping,stats,audit=derive(corpus(),tokenizer(),config())
    path=ROOT/DATA;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as out:out.write(b''.join(canonical(r)+b'\n' for r in private))
    mapping.update(source_commit=source,source_sha256=record(__file__)['sha256'],derived_corpus=record(path),created_at=now())
    for name,value in ((MAP,mapping),(STATS,stats),(AUDIT,audit)):write_new(ROOT/name,value)
    return stats


def main():
    argparse.ArgumentParser(description=__doc__).parse_args();stats=build()
    print(json.dumps({'status':'PASS','base':stats['base']['chunks'],'children':stats['child']['chunks'],'parents':stats['parent']['chunks'],'split_originals':stats['split_originals']}))


if __name__=='__main__':main()
