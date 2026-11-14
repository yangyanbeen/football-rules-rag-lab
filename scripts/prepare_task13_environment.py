"""Create a new, pinned Windows task13 environment without changing existing runtimes."""
import argparse,importlib.metadata,json,os,subprocess,sys,time
from pathlib import Path
from answer_eval_core import ROOT,record,read,write_new,now,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--environment',default='.runtime/task13/venv')
    p.add_argument('--uv',default='.runtime/uv/uv.exe')
    p.add_argument('--python',default='.runtime/python/cpython-3.10.22/python.exe')
    p.add_argument('--offline',action='store_true');p.add_argument('--report',required=True);a=p.parse_args()
    envpath=(ROOT/a.environment).resolve();uv=(ROOT/a.uv).resolve();base=(ROOT/a.python).resolve();report=(ROOT/a.report).resolve()
    if not envpath.is_relative_to(ROOT/'.runtime/task13') or envpath==ROOT/'.runtime/task13' or envpath.exists():raise ValueError('Use a new task13 environment directory')
    if report.exists():raise ValueError('Receipt already exists')
    if not uv.is_file() or not base.is_file():raise ValueError('Prepare uv and pinned standalone Python first; see TASK_13_REPRODUCTION')
    version=subprocess.check_output([str(base),'-c','import platform;print(platform.python_version())'],text=True).strip()
    if version!='3.10.22':raise ValueError('Pinned Python3.10.22 required')
    upstream=ROOT/'third_party/kotaemon-v0.12.0'
    commit=subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()
    if commit!='9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9':raise ValueError('Pinned upstream differs')
    # The exported lock is public; never resolve floating requirements here.
    requirements=ROOT/'infra/task13-runtime-requirements.txt'
    started=now();commands=[];folder=ROOT/'.runtime/task13/environment-install';folder.mkdir(parents=True,exist_ok=True)
    log=folder/('install-'+str(time.time_ns())+'.log');python=envpath/'Scripts/python.exe'
    offline=['--offline'] if a.offline else []
    operations=[['venv',*offline,'--cache-dir',str(ROOT/'.cache/uv'),'--python',str(base),str(envpath)],
        ['pip','install',*offline,'--require-hashes','--cache-dir',str(ROOT/'.cache/uv'),'--python',str(python),'-r',str(requirements)],
        ['pip','install',*offline,'--no-deps','--cache-dir',str(ROOT/'.cache/uv'),'--python',str(python),'-e',str(upstream/'libs/kotaemon'),'-e',str(upstream/'libs/ktem')]]
    try:
        with log.open('xb') as handle:
            for operation in operations:
                proc=subprocess.run([str(uv),*operation],cwd=ROOT,stdout=handle,stderr=handle,
                    env={**os.environ,'UV_NO_PROGRESS':'1','PYTHONIOENCODING':'utf-8'},timeout=1800,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                commands.append({'operation':operation[0:2],'exit_code':proc.returncode})
                print(json.dumps(commands[-1]),flush=True)
                if proc.returncode:raise RuntimeError('Pinned install failed; private log '+log.relative_to(ROOT).as_posix())
        code="import json,sys,platform,importlib.metadata as m;print(json.dumps({'python':platform.python_version(),'isolated':sys.prefix!=sys.base_prefix,'packages':{d.metadata['Name']:d.version for d in m.distributions()}}))"
        actual=json.loads(subprocess.check_output([str(python),'-B','-c',code],cwd=ROOT,text=True,encoding='utf-8'))
        if actual['python']!='3.10.22' or actual['isolated'] is not True or actual['packages'].get('kotaemon')!='0.12.0' or actual['packages'].get('ktem')!='0.12.0':raise ValueError('New environment verification differs')
        write_new(report,{'version':'task13-environment-1.0','status':'PASS','started_at':started,'completed_at':now(),
            'new_environment':envpath.relative_to(ROOT).as_posix(),'fresh_environment':True,'system_site_packages':False,
            'requirements':record(requirements),'upstream_commit':commit,'operations':commands,'actual':actual,'private_log':record(log),
            'offline_install':a.offline,'existing_environment_changed':False})
        print(json.dumps({'status':'PASS','packages':len(actual['packages']),'environment':envpath.relative_to(ROOT).as_posix()}),flush=True)
    except BaseException as exc:
        write_new(report,{'version':'task13-environment-1.0','status':'FAIL','started_at':started,'failed_at':now(),'operations':commands,'error':type(exc).__name__+': '+str(exc),'private_log':record(log) if log.exists() else None})
        raise


if __name__=='__main__':main()
