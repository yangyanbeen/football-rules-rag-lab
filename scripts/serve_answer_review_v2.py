"""Task12 strict review UI: bound evidence, validated durable judgments and honest completion."""
from __future__ import annotations
import argparse,hashlib,html,json,secrets,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import parse_qs,urlsplit
from answer_eval_core import *
import answer_review_v2 as review


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=7865);a=p.parse_args()
    if not 1024<=a.port<=65535:raise ValueError('Invalid port')
    context=review.review_context();qs=context['labels']
    predictions=context['predictions']
    corpus=review.source_corpus()
    ids=context['ids'];ledger=PRIVATE/'human_answer_reviews.jsonl';token=secrets.token_urlsafe(32);lock=threading.RLock()
    def latest():
        return review.snapshot(context)
    def evidence(qid):return review.evidence(qid,context)
    def field(name,label):
        return '<p>'+html.escape(label)+' '+''.join('<label><input required type="radio" name="'+name+'" value="'+v+'">'+txt+'</label> ' for v,txt in [('yes','是'),('no','否'),('uncertain','无法判定')])+'</p>'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def send(self,status,body):
            raw=body.encode('utf-8');self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            try:
                if self.headers.get('Host')!='127.0.0.1:'+str(a.port):raise ValueError('Invalid local host')
                if review.review_context()['identity']!=context['identity']:raise ValueError('Review context changed; restart required')
                review.source_corpus()
                self.render_GET()
            except (ValueError,KeyError,TypeError,OSError) as exc:self.send(409,'审核材料校验失败：'+html.escape(str(exc)))
        def render_GET(self):
            if self.path!='/':self.send(404,'Not found');return
            done=latest();blocks=['<!doctype html><meta charset="utf-8"><title>任务十二人工审核</title><style>body{max-width:1100px;margin:30px auto;font:16px/1.6 sans-serif}pre{white-space:pre-wrap;background:#f4f5f7;padding:16px}section{border-top:2px solid #ccc;padding:20px 0}label{margin-right:14px}button{padding:10px 20px}</style>',
              '<h1>任务十二人工审核</h1><p>已提交 '+str(done['reviewed_samples'])+'/12。需要逐题阅读后本人提交；没有默认勾选。AI成绩与原标签人审不能替代当前回答的人工判断。</p>']
            for qid in ids:
                q=qs[qid];pred=predictions[qid];actual=evidence(qid)
                blocks.append('<section><h2>'+html.escape(qid+' '+q['question'])+('（已提交，可追加修订）' if qid not in done['missing_ids'] else '')+'</h2>')
                blocks.append('<h3>实际回答与来源</h3><pre>'+html.escape(actual['answer'])+'</pre><p>答案SHA256：'+pred['answer_sha256']+'</p>')
                blocks.append('<details><summary>原标签支持段与当次可见证据（核对错误拒答和相关性）</summary>')
                for cid in dict.fromkeys(q['expected_chunk_ids']+pred['offered_ids']):
                    r=corpus[cid];blocks.append('<h4>'+html.escape(cid+' '+r['source_url'])+'</h4><pre>'+html.escape(r['content_zh'])+'</pre><p>'+html.escape(str(r['license'])+' · '+str(r['source_attribution']))+'</p>')
                blocks.append('<p>当次实际提供ID：'+html.escape(', '.join(pred['offered_ids']))+'</p></details>')
                blocks.append('<form action="/review" method="post"><input type="hidden" name="csrf" value="'+token+'"><input type="hidden" name="question_id" value="'+qid+'"><input type="hidden" name="answer_sha256" value="'+pred['answer_sha256']+'"><input type="hidden" name="context_sha256" value="'+context['identity']+'">')
                for i,label in enumerate(q['expected_answer_points']):blocks.append(field('point_'+str(i),'答案是否正确覆盖：'+label))
                for i,label in enumerate(q['required_conditions']):blocks.append(field('condition_'+str(i),'答案是否完整保留条件/例外：'+label))
                for i,cite in enumerate(pred['citations']):blocks.append(field('citation_'+str(i),'引用是否支持答案并直接回答所问：'+cite['chunk_id']))
                blocks.append(field('refusal_appropriate','回答/拒答选择是否恰当（标签要求'+('可回答' if q['answerable'] else '必须拒答')+'）'))
                blocks.append('<p>审阅者（仅本机保存）：<input required name="reviewer" maxlength="100"></p><p>理由/修改建议：<textarea required name="reason" maxlength="2000" rows="3" cols="70"></textarea></p><button>提交本题人工判断</button></form></section>')
            self.send(200,'\n'.join(blocks))
        def do_POST(self):
            try:
                origin=self.headers.get('Origin')
                if self.path!='/review' or self.headers.get('Host')!='127.0.0.1:'+str(a.port) or (origin is not None and origin!='http://127.0.0.1:'+str(a.port)):raise ValueError('Invalid local review origin')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16000:raise ValueError('Invalid submission size')
                form=parse_qs(self.rfile.read(length).decode('utf-8'),keep_blank_values=True)
                def one(key):
                    if key not in form or len(form[key])!=1:raise ValueError('Missing/duplicate field: '+key)
                    return form[key][0]
                if not secrets.compare_digest(one('csrf'),token):raise ValueError('Invalid review token')
                qid=one('question_id')
                if qid not in ids:raise ValueError('Not a selected sample')
                if review.review_context()['identity']!=context['identity']:raise ValueError('Changed review context')
                review.source_corpus()
                actual=evidence(qid);q=qs[qid];pred=predictions[qid]
                if one('answer_sha256')!=pred['answer_sha256'] or one('context_sha256')!=context['identity']:raise ValueError('Stale displayed answer or labels')
                allowed={'csrf','question_id','answer_sha256','context_sha256','reviewer','reason','refusal_appropriate'}
                for prefix,n in [('point_',len(q['expected_answer_points'])),('condition_',len(q['required_conditions'])),('citation_',len(pred['citations']))]:
                    allowed.update(prefix+str(i) for i in range(n))
                if set(form)!=allowed:raise ValueError('Unknown or missing form fields')
                def verdict(name):
                    v=one(name)
                    if v not in ('yes','no','uncertain'):raise ValueError('Missing explicit judgment')
                    return v
                reviewer=one('reviewer').strip();reason=one('reason').strip()
                if not 1<=len(reviewer)<=100 or not 1<=len(reason)<=2000:raise ValueError('Reviewer and reason required')
                result={'version':'answer-human-review-1.1','context_sha256':context['identity'],'question_id':qid,'answer_sha256':pred['answer_sha256'],
                  'private_trace':pred['trace'],'reviewer_type':'human','reviewer':reviewer,'reviewed_at':now(),
                  'point_decisions':[verdict('point_'+str(i)) for i in range(len(q['expected_answer_points']))],
                  'condition_decisions':[verdict('condition_'+str(i)) for i in range(len(q['required_conditions']))],
                  'citation_decisions':[verdict('citation_'+str(i)) for i in range(len(pred['citations']))],
                  'refusal_appropriate':verdict('refusal_appropriate'),'reason':reason,'submission_channel':'explicit local browser form'}
                with lock:review.save_review(result,context,ledger)
                self.send_response(303);self.send_header('Location','/');self.end_headers()
            except (ValueError,KeyError,TypeError,OSError) as exc:self.send(400,'提交未保存：'+html.escape(str(exc)))
    print('Human review ready: http://127.0.0.1:'+str(a.port)+'/; actual submissions '+str(latest()['reviewed_samples'])+'/12',flush=True)
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()


if __name__=='__main__':main()
