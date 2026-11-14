"""Create/verify the reproducible runtime manifest; full corpora/models are hash-only."""
import argparse,subprocess
from task13_core import *

OUTPUT='reports/task13/delivery_manifest.json'
FIXED=('docs/TASK_13_SCOPE.md','docs/TASK_13_REPRODUCTION.md','docs/TASK_13_LICENSES.md',
    'infra/task13-runtime-requirements.txt','frontend/start_integrated_rag.ps1')
RECEIPTS=('environment-final.json','requirements-provenance.json','corpus-import.json','clean-corpus-import.json',
    'preflight.json','index-rebuild.json','backend-demo-first.json','contract-final.json','ui-demo.json','prior-task12.json')


def create():
    cfg=app_config();source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    paths=sorted(set(FIXED)|{p.relative_to(ROOT).as_posix() for folder in ('scripts','config') for p in (ROOT/folder).glob('*') if p.is_file() and p.suffix in ('.py','.ps1','.json','.txt')})
    # All runtime sources/configurations are committed before packaging.
    for p in paths:
        if p.startswith(('scripts/','config/')):
            if subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)!=(ROOT/p).read_bytes():raise ValueError('Commit runtime source before packaging: '+p)
    return {'version':'task13-runtime-package-1.0','created_at':now(),'source_commit':source,
        'public_members':[record(ROOT/p) for p in paths],
        'receipts':[record(ROOT/'reports/task13'/n) for n in RECEIPTS],
        'private_data':{'inventory':record(ROOT/'data/manifests/local_data_files.json'),'corpus':record(ROOT/cfg['corpus']),
            'indexes':{k:record(ROOT/cfg[k]/'index_manifest.json') for k in ('dense_index','bm25_index')}},
        'models':{'answer':read(ROOT/'config/answer_evaluation.json')['llm'],
            'embedding':read(ROOT/'config/dense_index.json')['model'],
            'reranker':{k:read(ROOT/'config/reranker_experiment.json')[k] for k in ('model_id','revision','files','provider','threads')}},
        'upstream_commit':'9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9',
        'policy':'Runtime code/config/docs and completed receipts frozen here. Full source tree and final delivery prose/gates/global indices are covered by the global project_file_manifest; excluded here to avoid recursive hashes. Full corpus, models, caches, user databases and answers are not packaged publicly.'}


def verify(value,private=False):
    if value['version']!='task13-runtime-package-1.0':raise ValueError('Unknown runtime manifest version')
    if not re.fullmatch('[a-f0-9]{40}',value['source_commit']) or subprocess.run(['git','merge-base','--is-ancestor',value['source_commit'],'HEAD'],cwd=ROOT,capture_output=True).returncode:raise ValueError('Invalid package producer')
    members=value['public_members']+value['receipts'];names=[r['path'] for r in members]
    if len(set(names))!=len(names) or not set(FIXED)<=set(names):raise ValueError('Duplicate/missing runtime package members')
    if any(n.startswith(('.runtime/','.models/','data/processed/','data/indexes/')) for n in names):raise ValueError('Private data in public package')
    if any(record(ROOT/r['path'])!=r for r in members):raise ValueError('Runtime package member hash differs')
    if {r['path'] for r in value['receipts']}!={'reports/task13/'+n for n in RECEIPTS}:raise ValueError('Incomplete completed receipt set')
    for r in value['public_members']:
        if r['path'].startswith(('scripts/','config/')):
            if digest(subprocess.check_output(['git','show',value['source_commit']+':'+r['path']],cwd=ROOT))!=r['sha256']:raise ValueError('Package source hash differs from producer')
    cfg=app_config()
    if value['models']['answer']!=read(ROOT/'config/answer_evaluation.json')['llm'] or value['models']['embedding']!=read(ROOT/'config/dense_index.json')['model'] or value['models']['reranker']!={k:read(ROOT/'config/reranker_experiment.json')[k] for k in ('model_id','revision','files','provider','threads')}:raise ValueError('Package model configuration differs')
    if private:
        for r in [value['private_data']['inventory'],value['private_data']['corpus'],*value['private_data']['indexes'].values()]:
            if record(ROOT/r['path'])!=r:raise ValueError('Package private data binding differs')
    return True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify',action='store_true');p.add_argument('--private',action='store_true');a=p.parse_args()
    if a.verify:verify(read(ROOT/OUTPUT),a.private);print(json.dumps({'status':'PASS','manifest':OUTPUT}))
    else:
        v=create();write_new(ROOT/OUTPUT,v);print(json.dumps({'status':'CREATED','public_members':len(v['public_members']),'receipts':len(v['receipts']),'source_commit':v['source_commit']}))
