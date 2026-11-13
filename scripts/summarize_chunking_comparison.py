"""Assemble the prescribed Task11 report exclusively from saved, validated runs."""
import argparse,json
from pathlib import Path
from eval_dataset import ROOT
from bm25_index import record,write_new,committed
from bm25_retrieval_eval import now
from structure_aware_chunking import STATS,MAP
import structure_retrieval_eval as ev


def payload():
    dev=ev.replay(ev.DIRECTORY/'dev');test=ev.replay(ev.DIRECTORY/'test');m=ev.mapping()
    return {'version':'chunking-comparison-1.0','created_at':now(),
            'source_commit':committed(ev.SOURCES+ev.INPUTS+('scripts/summarize_chunking_comparison.py',)),
            'formal_test_source_commit':json.loads((ev.DIRECTORY/'test/run_manifest.json').read_text('utf-8'))['source_commit'],
            'source_sha256':{p:record(ROOT/p)['sha256'] for p in ev.NATIVE+('scripts/summarize_chunking_comparison.py',)},
            'structure':json.loads((ROOT/STATS).read_text('utf-8')),'development':dev,'test':test,
            'selected_on_dev':dev['selected_on_this_split'],'dataset':m['derived_corpus'],'mapping':record(ROOT/MAP),
            'error_analysis':{s:record(ev.DIRECTORY/s/'error_analysis.json') for s in ('dev','test')},
            'label_policy':'Original human-reviewed labels retained. Complete source-span coverage required; partial same-source child is not automatically relevant.',
            'interpretation':'Parent expansion may improve coverage by returning more surrounding text. Report budgeted and raw metrics, unexpanded child control, tokens and repeated-source-position redundancy together.',
            'timing_policy':'One actual query embedding shared across base/child indices and derived parent contexts. Individual model requests are not independent per method. No latency/QPS improvement claim.',
            'no_new_model_requests_during_summary':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    from run_structure_comparison import output_path
    out=output_path(a.output);value=payload();write_new(out,value)
    print(json.dumps({'status':'PASS','selected_on_dev':value['selected_on_dev'],'metrics':{m:v['budgeted']['metrics'] for m,v in value['test']['methods'].items()}}))


if __name__=='__main__':main()
