"""E8 offline diagnostic: E7 original, corrected relations, corrected decomposition.

No inference module is imported. Socket activity is rejected before replay.
Reviewed questions and source judgments are diagnosis-only, never runtime input.
"""
import argparse
import copy
import csv
import hashlib
import io
import itertools
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
NETWORK_ATTEMPTS=[]
def deny_network(event,args):
    if event.startswith('socket.'):
        NETWORK_ATTEMPTS.append(event)
        raise RuntimeError('E8 offline replay prohibits networking and model calls')
sys.addaudithook(deny_network)

from answer_eval_core import canonical,read,record
from citation_catalog_guard import safe_render
from e7_evidence_map import parse_mapping
from e8_source_audit import NEUTRAL,ALIASES,NEW_PROFILES,PROFILES,DIRECT

CASES=['T026-expanded','T034-expanded','D017-native','D021-native']
PREPARED=ROOT/'.runtime/phase2/e7-prepared-final/prepared.json'
RUN=ROOT/'.runtime/phase2/e7-pilot'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def write(p,v):
    with p.open('xb') as f:f.write(canonical(v))

def score(ids,c):
    mask=[bool(set(ids)&set(v)) for v in c['support_per_point']]
    supported=[cid for cid in ids if any(cid in v for v in c['support_per_point'])]
    grade='false_refusal' if not ids else 'correct' if all(mask) else 'partial' if any(mask) else 'incorrect'
    return dict(grade=grade,point_mask=mask,supported_ids=supported,unsupported_ids=[cid for cid in ids if cid not in supported])

def audit_matrix(requirements,profiles,c,corpus):
    result=[]
    for i,(req,profile) in enumerate(zip(requirements,profiles)):
        ratings=PROFILES[profile];assert len(ratings)==len(c['offered_ids'])==5
        for cid,rating in zip(c['offered_ids'],ratings):
            text=corpus[cid]['content_zh']
            assert all(isinstance(q,str) and 1<=len(q)<=120 and q in text for q in rating['quotes']),(profile,cid,rating)
            assert rating['label']=='unrelated' or rating['quotes']
            result.append(dict(requirement_index=i,requirement=req['requirement'],chunk_id=cid,profile=profile,
                **copy.deepcopy(rating),body_sha256=hashlib.sha256(text.encode()).hexdigest(),quote_substrings_verified=True))
    return result

def corrected(requirements,matrix):
    return {'requirements':[dict(requirement=req['requirement'],
        supporting_ids=[v['chunk_id'] for v in matrix if v['requirement_index']==i and v['label']==DIRECT])
        for i,req in enumerate(requirements)]}

def minimal_full(c):
    for size in range(1,4):
        for ids in itertools.combinations(c['offered_ids'],size):
            if all(score(list(ids),c)['point_mask']):return list(ids)
    return None

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    prep=read(PREPARED);by={c['case_id']:c for c in prep['cases']};manifest=read(RUN/'completed.json')
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    refs={**prep['source_files'],**prep['candidate_files']}
    refs.update({str(PREPARED.relative_to(ROOT)).replace('\\','/'):record(PREPARED),
        'optimization/e8_source_audit.py':record(ROOT/'optimization/e8_source_audit.py'),
        'optimization/e8_offline_replay.py':record(Path(__file__))})
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    pairs=[];results=[];raw_hashes={};normalized_changes=[]
    for key in CASES:
        c=by[key]
        assert sha(ROOT/c['source_trace'])==c['source_sha256']
        evidence=json.loads(c['messages'][1]['content'])['evidence']
        for ev in evidence:
            actual=corpus[ev['chunk_id']]
            assert ev['content_zh']==actual['content_zh']
            assert hashlib.sha256(actual['content_zh'].encode()).hexdigest()==actual['content_zh_sha256']
        for repeat in range(1,5):
            path=RUN/f'{key}-B-r{repeat}.json';raw_hashes[path.name]=sha(path)
            assert raw_hashes[path.name]==manifest['hashes'][path.name]
            trace=read(path);original=trace['observations']['model_attempts'][-1]['mapping_validation']['requirements']
            profiles=[ALIASES[r['requirement']] for r in original]
            old_matrix=audit_matrix(original,profiles,c,corpus)
            for v in old_matrix:
                v.update(case_id=key,repeat=repeat,group='relations_only')
                pairs.append(v)
            new=[dict(requirement=q,supporting_ids=[]) for q in NEUTRAL[key]]
            new_matrix=audit_matrix(new,NEW_PROFILES[key],c,corpus)
            for v in new_matrix:
                v.update(case_id=key,repeat=repeat,group='relations_and_decomposition')
                pairs.append(v)
            packets={'original':{'requirements':original},'relations_only':corrected(original,old_matrix),
                     'relations_and_decomposition':corrected(new,new_matrix)}
            for group,packet in packets.items():
                selection,selection_audit=parse_mapping(json.dumps(packet,ensure_ascii=False),c['offered_ids'],3)
                ids=selection['chunk_ids'];answer,citations=safe_render(ids,corpus)
                if group=='original':
                    assert ids==trace['result']['selected_ids']
                    assert (answer,citations)==(trace['result']['answer'],trace['result']['citations'])
                if group=='relations_only':
                    assert [v['requirement'] for v in packet['requirements']]==[v['requirement'] for v in original]
                    for i,(before,after) in enumerate(zip(original,packet['requirements'])):
                        normalized_changes.append(dict(case_id=key,repeat=repeat,requirement_index=i,requirement=before['requirement'],
                            old_ids=before['supporting_ids'],new_ids=after['supporting_ids'],
                            removed=[cid for cid in before['supporting_ids'] if cid not in after['supporting_ids']],
                            added=[cid for cid in after['supporting_ids'] if cid not in before['supporting_ids']]))
                name=f'{key}-{group}-r{repeat}.json'
                value=dict(case_id=key,question_id=c['question_id'],repeat=repeat,group=group,question=c['question'],
                    offered_ids=c['offered_ids'],requirements=packet['requirements'],selection_audit=selection_audit,
                    selected_ids=ids,answer=answer,citations=citations,**score(ids,c),
                    source_trace=path.relative_to(ROOT).as_posix(),source_trace_sha256=sha(path),new_model_calls=0)
                write(a.out/name,value)
                results.append({k:v for k,v in value.items() if k not in ('answer','citations')})
    groups={}
    for key in CASES:
        groups[key]={}
        for group in ('original','relations_only','relations_and_decomposition'):
            vals=[v for v in results if v['case_id']==key and v['group']==group]
            groups[key][group]=dict(grades=dict(Counter(v['grade'] for v in vals)),
                selected_ids=[v['selected_ids'] for v in vals],point_masks=[v['point_mask'] for v in vals])
    for name,ref in refs.items():assert record(ROOT/name)==ref,name
    assert not NETWORK_ATTEMPTS
    review= dict(kind='Diagnostic source-reading judgments, never inference inputs',
        reviewer='Codex review of original paragraphs, not new human/expert adjudication',
        label_definitions={'direct_support':'Answers the whole requirement with its scope and polarity.',
            'partial_support':'Supports only part, one side, or an insufficiently specified scope.',
            'refutation':'Directly contradicts a claim, retaining polarity; not applicable just because a neutral question has a negative answer.',
            'unrelated':'No direct answer to the requested entity/relation, even if the football topic overlaps.'},
        caveats=['Generic multi-part E7 requirements are retained, not silently made atomic.',
                 'A true support relation can lead full original text to cover unlisted points; output recovery alone does not prove decomposition correct.',
                 'Partial support never enters E7 maximum coverage. Equivalent offered paragraphs are allowed.'],
        reviewed_pairs=pairs)
    write(a.out/'source_review_matrix.json',review)
    write(a.out/'relation_changes.json',normalized_changes)
    unique={(v['case_id'],v['requirement'],v['chunk_id']) for v in pairs}
    metrics=dict(groups=groups,records=results,new_model_calls=0,network_attempts=0,
        offline_replay_records=32,original_control_replays=16,reviewed_pair_observations=len(pairs),unique_reviewed_pairs=len(unique),
        decomposition_necessary_for_recovery=[key for key in CASES if groups[key]['relations_only']['grades'].get('correct',0)<4 and groups[key]['relations_and_decomposition']['grades'].get('correct',0)==4],
        contexts_fit_within_3={key:dict(minimum_full_support_ids=minimal_full(by[key]),within_existing_cap=minimal_full(by[key]) is not None) for key in CASES},
        not_model_quality=True,full90_executed=False,holdout_used=False,
        reviewer=review['reviewer'],scope='Offline diagnostic ceiling under reviewed relations/questions; labels never supplied to an answering model.')
    write(a.out/'metrics.json',metrics)
    write(a.out/'metadata.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_files=refs,raw_E7_hashes=raw_hashes,prepared_sha256=sha(PREPARED),baseline='5986781 + Prompt A',new_model_calls=0))
    completed={p.name:sha(p) for p in a.out.glob('*.json')}
    write(a.out/'completed.json',dict(hashes=completed,new_model_calls=0,source_inputs_unchanged=True))
    print(json.dumps({k:metrics[k] for k in ('groups','new_model_calls','offline_replay_records','original_control_replays','reviewed_pair_observations','unique_reviewed_pairs','decomposition_necessary_for_recovery','contexts_fit_within_3')},ensure_ascii=False))

if __name__=='__main__':main()
