"""Timeout-safe revised worker boundary; operational errors cannot become semantic refusals."""
import os,threading,time
from task13_audit import *
from task13_query_rewrite import bounded_history

LOCK=threading.RLock()


def call_worker(question=None,check=False, *, history=()):
    cfg=audit_config();start=time.perf_counter();trace=ROOT/cfg['private_root']/'workers'/(uuid.uuid4().hex+'.json')
    if check and history:
        raise ValueError('Readiness does not accept conversation history')
    turns = bounded_history(history)
    if not check:question=normalize_question(question)
    command=[str(ROOT/cfg['environment']),'-B','-X','faulthandler',str(ROOT/'scripts/query_task13_audit.py')]
    command+=['--check'] if check else ['--question='+question,'--trace',str(trace)]
    worker_input = {}
    if turns:
        command.append('--history-stdin')
        worker_input['input'] = canonical(turns).decode('utf-8')
    def fail(kind,stdout='',stderr=''):
        write_new(trace.with_suffix('.failure.json'),{'version':'task13-worker-failure-1.0','captured_at':now(),'kind':kind,'question_sha256':digest((question or '').encode()),'history_turns':len(turns),'stdout':stdout.decode('utf-8','replace') if isinstance(stdout,bytes) else stdout,'stderr':stderr.decode('utf-8','replace') if isinstance(stderr,bytes) else stderr,'private_trace':record(trace) if trace.exists() else None})
        raise RuntimeError('本次问答未完成；请检查本机服务。详细信息已保存在本机。')
    with LOCK:
        try:
            proc=subprocess.run(command,cwd=ROOT,env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,encoding='utf-8',timeout=cfg['worker_timeout_seconds'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**worker_input)
        except subprocess.TimeoutExpired as exc:fail('timeout',exc.stdout,exc.stderr)
        except OSError as exc:fail('launch_failed','',str(exc))
    if proc.returncode:fail('worker_failed',proc.stdout,proc.stderr)
    try:
        packet=json.loads(proc.stdout)
        if check:
            exact(packet,('status','profile','records','implementation'),'readiness')
            if packet['status']!='READY' or packet['profile']!=cfg['version'] or type(packet['records']) is not int or packet['records']!=99:raise ValueError('Worker not ready')
            validate_implementation(packet['implementation']);return packet
        exact(packet,('status','trace_id','private_trace'),'worker packet')
        if packet['private_trace']!=record(trace):raise ValueError('Worker trace identity differs')
        result = read(trace)
        effective_question = question
        if turns:
            resolution = result['query_resolution']
            exact(resolution, ('original_question_sha256','history_turns','outcome','seconds','error'), 'query resolution')
            effective_question = result['question']
            outcome = resolution['outcome']
            if (resolution['original_question_sha256'] != digest(question.encode('utf-8'))
                    or type(resolution['history_turns']) is not int or resolution['history_turns'] != len(turns)
                    or outcome not in ('unchanged', 'rewritten', 'fallback')
                    or (outcome == 'rewritten') != (effective_question != question)
                    or (outcome == 'fallback') != isinstance(resolution['error'], str)
                    or (outcome != 'fallback' and resolution['error'] is not None)
                    or type(resolution['seconds']) not in (int, float)
                    or not math.isfinite(resolution['seconds']) or resolution['seconds'] < 0):
                raise ValueError('Worker query resolution differs from request')
        elif 'query_resolution' in result:
            raise ValueError('Unexpected worker query resolution')
        validate_private(result, effective_question, True)
        if packet['trace_id']!=result['trace_id'] or packet['status']!=result['status']:raise ValueError('Worker status differs')
        if result['error'] is not None:fail('runtime_or_validation_error',proc.stdout,proc.stderr)
        return result,record(trace),time.perf_counter()-start
    except (ValueError,TypeError,KeyError,OSError) as exc:fail('invalid_worker_packet',proc.stdout,proc.stderr+'\n'+type(exc).__name__)
