"""Local human annotation review form. Never auto-approve any real question."""
from __future__ import annotations

import argparse
import json
import secrets
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from eval_dataset import CHECKLIST, CORPUS, EVAL, REVIEW_LEDGER, active_reviews, load_jsonl

HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>足球规则评测集 · 人工复核</title><style>
body{font:16px/1.6 system-ui;background:#f4f6f8;color:#152332;margin:0}header{background:#163b40;color:white;padding:20px 5vw}main{max-width:1180px;margin:20px auto;padding:0 20px}.toolbar,.card{background:white;border:1px solid #d8e0e5;border-radius:10px;padding:18px;margin:14px 0}.columns{display:grid;grid-template-columns:1fr 1fr;gap:18px}pre{white-space:pre-wrap;font:inherit}button,select,input,textarea{font:inherit;padding:9px;border-radius:6px;border:1px solid #9eb0bc}button{background:#186a53;color:white;cursor:pointer}button.secondary{background:#63737d}button.reject{background:#9b3a32}button:disabled{opacity:.5}label{display:block;margin:9px 0}input[type=checkbox]{width:18px;height:18px}textarea{width:90%;min-height:65px}.warning{color:#93421d}.success{color:#176b48}a{color:#126587}#message{font-weight:600}summary{cursor:pointer}small{display:block;color:#586b78}@media(max-width:750px){.columns{grid-template-columns:1fr}}</style>
<header><h1>足球规则评测集：逐题人工复核</h1><p>AI 草稿不能代替人工确认。请阅读证据与校核提示后再勾选；发现问题选择“需要修改”。本页不调用模型。</p></header>
<main><div class="toolbar"><b id="progress">加载中</b><p>先审核开发题，再审核测试候选。当前测试未冻结，可用于标注复核；冻结后不能用来调参。</p>
<label>复核人姓名或昵称 <input id="reviewer" placeholder="请由实际复核人填写" autocomplete="off"></label>
<label>选择问题 <select id="question" onchange="showQuestion()"></select></label><button class="secondary" onclick="nextQuestion()">下一条未通过题</button></div>
<div class="card"><h2 id="questionTitle"></h2><p id="questionText"></p><small id="meta"></small><h3>拟定答案要点 / 拒答理由</h3><pre id="points"></pre><p class="warning">这是针对固定 Wikipedia 快照的证据评测，不是现行官方规则认证；裁判专家审校状态保持原样。</p></div>
<div class="columns"><section><h2>拟定支持段</h2><div id="supports"></div></section><section><h2>相似但不支持目标的难负例</h2><div id="negatives"></div></section></div>
<details class="card"><summary>查阅其他知识段（可搜索全部 99 段）</summary><input id="search" placeholder="输入规则号、ID 或关键词"><button class="secondary" onclick="searchCorpus()">查找</button><div id="searchResults"></div></details>
<div class="card"><h2>人工判定</h2><div id="checks"></div><label>修改意见或复核备注<textarea id="note" placeholder="需要修改时请写明问题；通过时可选填"></textarea></label>
<button id="approve" onclick="submitReview('approved')">已逐项核对，通过此题</button> <button class="reject" onclick="submitReview('changes_requested')">需要修改</button><p id="message"></p>
<small>只记录当前题。没有批量自动通过。通过记录绑定问题、答案要点、来源与难负例的哈希；内容改变后原确认失效。</small></div></main>
<script>
const csrf=__CSRF__;let state,current;const labels={support_and_conditions:'已逐项核对支持段与全部条件/例外；不可回答题已确认资料不足',negative_reasons:'已核对难负例主题相关且不能支持本题目标，理由正确',source_and_version:'已阅读来源、版本边界及待校核提示，没有当成官方已审校规则',answer_or_refusal:'已核对答案要点或拒答理由；没有遗漏改变结论的重要条件'};
const el=id=>document.getElementById(id);const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function refresh(selected){state=await(await fetch('/api/state')).json();el('progress').textContent=`人工通过 ${state.approved} / ${state.total}；${state.locked?'测试已冻结':'测试候选待复核'}`;el('question').innerHTML=state.questions.map(q=>`<option value="${q.question_id}">${q.approved?'✓ ':''}${q.question_id} · ${esc(q.topic)}</option>`).join('');if(selected)el('question').value=selected;showQuestion();}
function block(row){return `<article class="card"><b>${esc(row.chunk_id)} · ${esc(row.title_zh)}</b><pre>${esc(row.content_zh)}</pre><a href="${esc(row.source_url)}" target="_blank" rel="noreferrer">${esc(row.source_id)} · 行 ${row.source_lines.join('–')}</a><small>Wikipedia contributors · ${esc(row.license)}；翻译/版本正文未独立核验；专家审校：${row.expert_reviewed?'是':'否'}</small>${row.needs_rule_review?'<p class="warning">待校核：'+esc(row.review_notes.join('；'))+'</p>':''}</article>`;}
async function showQuestion(){current=await(await fetch('/api/question?id='+encodeURIComponent(el('question').value))).json();el('questionTitle').textContent=current.row.question_id+' · '+(current.row.answerable?'可回答候选':'应拒答候选');el('questionText').textContent=current.row.question;el('meta').textContent=`${current.row.split} · 规则 ${current.row.law_numbers.join(',')||'资料外'} · ${current.row.difficulty}`;el('points').textContent=current.row.answerable?current.row.required_conditions.map(x=>'• '+x).join(String.fromCharCode(10)):current.row.refusal_reason;el('supports').innerHTML=current.supports.map(block).join('')||'<p>没有支持块；请核对拒答边界。</p>';el('negatives').innerHTML=current.negatives.map(n=>'<p class="warning">拟定理由：'+esc(n.reason)+'</p>'+block(n.source)).join('');el('checks').innerHTML=Object.entries(labels).map(([k,v])=>`<label><input type="checkbox" id="${k}"> ${v}</label>`).join('');el('note').value='';el('message').textContent='';el('approve').disabled=state.locked;}
function nextQuestion(){const index=state.questions.findIndex(x=>x.question_id===el('question').value);const ordered=[...state.questions.slice(index+1),...state.questions.slice(0,index+1)];const q=ordered.find(x=>!x.approved);if(q){el('question').value=q.question_id;showQuestion();}else el('message').textContent='全部已确认，可运行冻结命令。';}
async function submitReview(decision){const checklist=Object.fromEntries(Object.keys(labels).map(k=>[k,el(k).checked]));if(!el('reviewer').value.trim()){el('message').textContent='请填写实际复核人姓名或昵称。';return;}if(decision==='approved'&&!Object.values(checklist).every(Boolean)){el('message').textContent='通过前需要亲自完成并勾选四项。';return;}const r=await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json','X-Review-CSRF':csrf},body:JSON.stringify({question_id:current.row.question_id,annotation_sha256:current.row.annotation_sha256,reviewer_name:el('reviewer').value.trim(),decision,checklist,note:el('note').value})});const data=await r.json();if(!r.ok){el('message').textContent=data.error;return;}const id=current.row.question_id;await refresh(id);el('message').textContent=decision==='approved'?'已记录此题人工通过，可点下一条。':'已记录修改请求，此题未通过。';}
async function searchCorpus(){const r=await(await fetch('/api/search?q='+encodeURIComponent(el('search').value))).json();el('searchResults').innerHTML=r.map(block).join('')||'没有匹配项';}
refresh();
</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=7862)
    args = parser.parse_args()
    corpus = {r['chunk_id']:r for r in load_jsonl(CORPUS)}
    rows = load_jsonl(EVAL/'retrieval_dev.jsonl') + load_jsonl(EVAL/'retrieval_test.jsonl')
    by_id = {r['question_id']:r for r in rows}
    negatives = load_jsonl(EVAL/'hard_negatives.jsonl')
    csrf, mutex = secrets.token_urlsafe(32), threading.Lock()
    loaded_revision = (EVAL/'dataset_manifest.json').stat().st_mtime_ns

    def refresh_data():
        nonlocal rows, by_id, negatives, loaded_revision
        revision = (EVAL/'dataset_manifest.json').stat().st_mtime_ns
        if revision != loaded_revision:
            rows = load_jsonl(EVAL/'retrieval_dev.jsonl') + load_jsonl(EVAL/'retrieval_test.jsonl')
            by_id = {r['question_id']:r for r in rows}
            negatives = load_jsonl(EVAL/'hard_negatives.jsonl')
            loaded_revision = revision

    def locked():
        return json.loads((EVAL/'dataset_manifest.json').read_text('utf-8'))['test_lock']['state'] == 'locked'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def send(self, status, value, html=False):
            data = value.encode('utf-8') if html else json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type','text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            with mutex:refresh_data()
            parsed=urlsplit(self.path); query=parse_qs(parsed.query)
            if parsed.path=='/': return self.send(200,HTML.replace('__CSRF__',json.dumps(csrf)),html=True)
            if parsed.path=='/api/state':
                approvals=active_reviews(rows)
                return self.send(200,{'approved':sum(v['approved'] for v in approvals.values()),'total':len(rows),'locked':locked(),
                                      'questions':[{'question_id':r['question_id'],'topic':r['topic'],'approved':approvals[r['question_id']]['approved']} for r in rows]})
            if parsed.path=='/api/question':
                row=by_id.get(query.get('id',[''])[0])
                if not row:return self.send(404,{'error':'未知问题'})
                return self.send(200,{'row':row,'supports':[corpus[k] for k in row['expected_chunk_ids']],
                                      'negatives':[{'reason':n['reason'],'source':corpus[n['chunk_id']]} for n in negatives if n['question_id']==row['question_id']]})
            if parsed.path=='/api/search':
                term=query.get('q',[''])[0].casefold()
                return self.send(200,[r for r in corpus.values() if term in (r['chunk_id']+r['title_zh']+r['content_zh']).casefold()][:20])
            self.send(404,{'error':'未找到'})

        def do_POST(self):
            with mutex:refresh_data()
            origin=self.headers.get('Origin')
            allowed={f'http://127.0.0.1:{args.port}',f'http://localhost:{args.port}'}
            if origin not in allowed or self.headers.get('X-Review-CSRF')!=csrf:
                return self.send(403,{'error':'请从本机复核页面提交'})
            if self.path!='/api/review':return self.send(404,{'error':'未找到'})
            if locked():return self.send(409,{'error':'测试已冻结；更改必须创建新版本'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384:raise ValueError('提交大小无效')
                value=json.loads(self.rfile.read(length))
                row=by_id[value['question_id']]
                if value.get('annotation_sha256')!=row['annotation_sha256']:raise ValueError('题目内容已变化，请刷新')
                name=value.get('reviewer_name','').strip()
                if len(name)<2 or len(name)>80:raise ValueError('请填写实际复核人姓名或昵称（2–80字符）')
                decision=value.get('decision')
                if decision not in ('approved','changes_requested'):raise ValueError('判定无效')
                if decision=='approved' and not all(value.get('checklist',{}).get(k) is True for k in CHECKLIST):raise ValueError('通过前请亲自核对全部四项')
                if decision=='changes_requested' and len(value.get('note','').strip())<4:raise ValueError('请写明需要修改的原因')
                event={'question_id':row['question_id'],'annotation_sha256':row['annotation_sha256'],'reviewer_type':'human',
                       'reviewer_name':name,'reviewed_at':datetime.now(timezone.utc).isoformat(),'decision':decision,
                       'checklist':value['checklist'],'note':str(value.get('note',''))[:4000],
                       'method':'local form: actual reviewer explicitly attests four checks'}
                with mutex:
                    REVIEW_LEDGER.parent.mkdir(parents=True,exist_ok=True)
                    with REVIEW_LEDGER.open('ab') as handle:handle.write((json.dumps(event,ensure_ascii=False)+'\n').encode('utf-8'))
                self.send(200,{'recorded':True})
            except (KeyError,TypeError,ValueError) as exc:self.send(400,{'error':str(exc)})

    print(f'Human review form: http://127.0.0.1:{args.port}/ (no automatic approval)',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__':main()
