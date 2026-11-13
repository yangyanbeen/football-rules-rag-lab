"""Add partial-support diagnostics from saved ranks; original reports stay intact."""
import argparse,json
from pathlib import Path
from eval_dataset import ROOT,EVAL,load_jsonl
from bm25_index import record,write_new
import reranker_eval as ev


def payload(split):
    summary=ev.replay(ev.DIRECTORY/split)
    questions=load_jsonl(EVAL/('retrieval_'+split+'.jsonl'));rows=load_jsonl(ev.DIRECTORY/split/'predictions.jsonl')
    return {'version':'reranker-support-supplement-1.0','split':split,
            'source_manifest':record(ev.DIRECTORY/split/'run_manifest.json'),
            'original_error_analysis':record(ev.DIRECTORY/split/'error_analysis.json'),
            'historical_quality_unchanged':{m:r['quality']['metrics'] for m,r in summary['methods'].items()},
            'diagnostics':ev.errors_for(questions,rows,split,include_partial=True),
            'source_sha256':{n:record(ROOT/n)['sha256'] for n in ('scripts/analyze_reranker_support.py','scripts/reranker_eval.py')},
            'new_model_requests':0,'new_locked_test_queries':0,
            'scope':'New diagnostic interpretation of existing saved ranks; not a new retrieval evaluation or parameter selection.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();out=a.output_dir.resolve()
    if not out.is_relative_to(ROOT/'reports/rechecks'):raise ValueError('Use reports/rechecks')
    if any((out/(s+'_support_diagnostics.json')).exists() for s in ('dev','test')):raise FileExistsError('Keep existing supplemental diagnostics')
    for split in ('dev','test'):
        result=payload(split);write_new(out/(split+'_support_diagnostics.json'),result)
        print(json.dumps({'status':'PASS','split':split,'counts':result['diagnostics']['counts']}))


if __name__=='__main__':main()
