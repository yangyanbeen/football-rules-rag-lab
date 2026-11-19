"""E5-A packing boundaries; no model or retrieval requests."""
import json,sys,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
from answer_eval_core import config,canonical
namespace={'__file__':str(R/'scripts/answer_eval_engine.py'),'__name__':'e5a_candidate'}
exec(compile(subprocess.check_output(['git','show','ba48ba1:scripts/answer_eval_engine.py'],cwd=R),namespace['__file__'],'exec'),namespace)
pack=namespace['pack']
c=config();p=(R/c['prompt_file']).read_text('utf8');row=dict(chunk_id='x',law_number=1,content_zh='正文',needs_rule_review=False,review_notes=[]);rows=[dict(row,chunk_id=f'x{i}') for i in range(11)];checks={}
a,m,n=pack('问题',rows,c,p);checks['max_five_full_messages_budget']=len(a)==5 and n==len(canonical(m))<=6200
big=[dict(v,content_zh='长'*3000) for v in rows];big[7]=rows[7];a,m,n=pack('问题',big,c,p);checks['rank8_fills_skipped_slot']=[x['chunk_id'] for x in a]==['x7']
big[7]=dict(rows[7],content_zh='长'*3000);big[10]=rows[10];a,m,n=pack('问题',big,c,p);checks['candidate11_excluded']=not a
try:pack('问'*3000,rows,c,p)
except ValueError:checks['oversize_question_rejected']=True
checks['source_not_mutated']=rows[0]==dict(row,chunk_id='x0')
print(json.dumps(dict(passed=sum(checks.values()),total=5,checks=checks),ensure_ascii=False));raise SystemExit(not all(checks.values()))
