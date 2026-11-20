"""Freeze sixteen E8-reviewed pairs before authoring E9 prompts."""
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,canonical,config

CHOICES=[
 ('T026-expanded','区分技术性违例与不当行为','L12-06'),
 ('T026-expanded','技术性违例与身体犯规的关系','L12-06'),
 ('T026-expanded','不当行为与身体犯规的关系','L12-15'),
 ('D021-native','直接接任意球的越位待遇','L13-05'),
 ('D021-native','直接接界外球不构成越位犯规。','L15-03'),
 ('D017-native','点球执行前，其他队员的位置条件。','L14-02'),
 ('T026-expanded','区分技术性违例与不当行为','L12-15'),
 ('T026-expanded','技术性违例与身体犯规的关系','L12-15'),
 ('T026-expanded','不当行为与身体犯规的关系','L12-01'),
 ('T034-expanded','罚球点球与点球决胜在本场计分上有何区别？','L14-01'),
 ('T034-expanded','罚球点球与点球决胜在本场计分上有何区别？','L07-03'),
 ('D021-native','直接接任意球不构成越位犯规。','L13-05'),
 ('T026-expanded','区分技术性违例与不当行为','L12-02'),
 ('D021-native','直接接界外球不构成越位犯规。','L16-03'),
 ('D017-native','点球执行前，守门员的位置条件。','L01-06'),
 ('T034-expanded','罚球点球与点球决胜在本场计分上有何区别？','L05-03'),
]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
    with p.open('xb') as f:f.write((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())

def main():
    d=ROOT/'optimization/experiments/E9_classification';d.mkdir(parents=True,exist_ok=False)
    private=ROOT/'.runtime/phase2/e9-frozen-samples';private.mkdir(parents=True,exist_ok=False)
    source=ROOT/'.runtime/phase2/e8-offline/source_review_matrix.json';review=read(source)
    meta=read(ROOT/'.runtime/phase2/e8-offline/metadata.json')
    refs=meta['source_files'];assert all(record(ROOT/n)==r for n,r in refs.items())
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    samples=[];inputs=[]
    for ix,(case,requirement,cid) in enumerate(CHOICES,1):
        rows=[r for r in review['reviewed_pairs'] if r['group']=='relations_only' and (r['case_id'],r['requirement'],r['chunk_id'])==(case,requirement,cid)]
        assert rows and len({r['label'] for r in rows})==1
        row=rows[0];body=corpus[cid]['content_zh']
        assert row['body_sha256']==hashlib.sha256(body.encode()).hexdigest()==corpus[cid]['content_zh_sha256']
        assert all(q in body for q in row['quotes'])
        payload=dict(requirement=requirement,evidence=dict(chunk_id=cid,content_zh=body))
        sid=f'S{ix:02d}'
        samples.append(dict(sample_id=sid,case_id=case,requirement=requirement,chunk_id=cid,
            reviewed_relation=row['label'],reviewed_quotes=row['quotes'],reviewed_note=row['note'],
            profile=row['profile'],body_sha256=row['body_sha256'],payload_sha256=hashlib.sha256(canonical(payload)).hexdigest()))
        inputs.append(dict(sample_id=sid,input=payload))
    assert len({(s['requirement'],s['chunk_id']) for s in samples})==16
    dump(d/'samples.json',dict(source_review=source.relative_to(ROOT).as_posix(),source_review_sha256=sha(source),
        reviewer=review['reviewer'],samples=samples,class_counts=dict(Counter(s['reviewed_relation'] for s in samples)),
        caveat='16 distinct pairs, not 16 independent user questions. E8 contains only one distinct reviewed refutation pair; this sample cannot estimate general refutation recall. No new labels or holdout questions.'))
    dump(d/'plan.json',dict(stage='E9 small classification comparison',control_runtime='5986781 + Prompt A',
        budget=dict(protocol_first_answers_max=16,semantic_first_answers_max=16,warmup_calls=0,retries=0,total_model_calls_max=32),
        variant_order=['P','S'],sample_order=[s['sample_id'] for s in samples],
        output='One JSON field relation with the same four-category enum for both arms; no quotes, explanations, or semantic retries.',
        model=config()['llm'],
        gates=dict(first_answer_protocol='16/16 valid',direct_support_recall='at least 5/6',
            false_direct_support='0/10 non-direct pairs',critical_L12_06='S01 and S02 both direct_support',
            critical_L12_15='S07 and S08 both partial_support',D021_polarity='S12 refutation',
            four_class_agreement='at least 13/16'),
        selection='Among passing arms: more correct four-class decisions, then higher direct recall; exact tie chooses P (fewer instruction changes). No passing arm => stop pairwise-verifier route; no T026-60 run.',
        conditional_expansion='Only after small-sample pass: freeze selected classifier, run T026-expanded 60 pairs once each; require four technical completions, >=3/4 correct and no concept-definition direct support from L12-15; then four false-refusal questions and D021. Sentence-ID evidence experiment and batching require separate acceptance.',
        labels_used_only_for_scoring=True,holdout_used=False,full90_executed=False))
    refs={**refs,source.relative_to(ROOT).as_posix():record(source),
          'optimization/e9_freeze_samples.py':record(Path(__file__))}
    dump(private/'inputs.json',dict(inputs=inputs,source_files=refs,model=config()['llm'],
        sample_review_sha256=sha(d/'samples.json'),plan_sha256=sha(d/'plan.json'),holdout_used=False))
    print(json.dumps(dict(samples=16,class_counts=dict(Counter(s['reviewed_relation'] for s in samples)),freeze=str(private/'inputs.json')),ensure_ascii=False))
if __name__=='__main__':main()
