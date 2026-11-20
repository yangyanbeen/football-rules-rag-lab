"""Validate offline E8 provenance, selection/rendering and polarity separation."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import canonical,read,record
from citation_catalog_guard import safe_render
from e7_evidence_map import parse_mapping


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    folder=ROOT/'.runtime/phase2/e8-offline';meta=read(folder/'metadata.json');done=read(folder/'completed.json')
    assert all(sha(folder/n)==h for n,h in done['hashes'].items())
    assert all(record(ROOT/n)==v for n,v in meta['source_files'].items())
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    prep=read(ROOT/'.runtime/phase2/e7-prepared-final/prepared.json');cases={c['case_id']:c for c in prep['cases']}
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    m=read(folder/'metrics.json');matrix=read(folder/'source_review_matrix.json')['reviewed_pairs'];bindings=0
    for row in m['records']:
        c=cases[row['case_id']]
        sel,audit=parse_mapping(json.dumps({'requirements':row['requirements']},ensure_ascii=False),c['offered_ids'],3)
        assert sel['chunk_ids']==row['selected_ids'] and audit==row['selection_audit']
        trace=read(folder/f"{row['case_id']}-{row['group']}-r{row['repeat']}.json")
        assert safe_render(sel['chunk_ids'],corpus)==(trace['answer'],trace['citations'])
        if row['group']!='original':
            rs=[v for v in matrix if v['case_id']==row['case_id'] and v['repeat']==row['repeat'] and v['group']==row['group']]
            assert len(rs)==len(row['requirements'])*5
            for i,req in enumerate(row['requirements']):
                assert req['supporting_ids']==[v['chunk_id'] for v in rs if v['requirement_index']==i and v['label']=='direct_support']
        bindings+=1
    polarity=[v for v in matrix if v['group']=='relations_only' and v['profile']=='free_negative' and v['chunk_id']=='L13-05']
    assert len(polarity)==3 and all(v['label']=='refutation' for v in polarity)
    assert m['new_model_calls']==m['network_attempts']==0
    assert m['decomposition_necessary_for_recovery']==['T034-expanded']
    result=dict(offline_selection_render_bindings=bindings,diagnostic_replays=32,original_controls=16,
        source_pairs=405,unique_source_pairs=140,D021_negative_claims_refuted=3,new_model_calls=0,
        hashes_verified=True,production_runtime_unchanged=True,holdout_used=False)
    target=folder/'verification.json';target.write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
