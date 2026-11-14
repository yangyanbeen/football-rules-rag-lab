"""Read-only readiness and rejected HTTP forms; never submit a valid human review."""
import argparse,html,re
from urllib.request import Request,urlopen,build_opener,ProxyHandler
from urllib.error import HTTPError
from urllib.parse import urlencode
from answer_eval_core import *


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=7865);p.add_argument('--report',required=True);a=p.parse_args()
    if not 1024<=a.port<=65535:raise ValueError('Invalid local port')
    url='http://127.0.0.1:'+str(a.port);opener=build_opener(ProxyHandler({}))
    ledger=PRIVATE/'human_answer_reviews.jsonl';before=ledger.read_bytes() if ledger.exists() else None
    def request(path='/',fields=None,headers=None):
        data=urlencode(fields).encode() if fields is not None else None
        req=Request(url+path,data=data,headers=headers or {})
        try:
            with opener.open(req,timeout=30) as r:return r.status,r.read().decode('utf-8')
        except HTTPError as e:return e.code,e.read().decode('utf-8')
    status,body=request();checks={'actual_http200':status==200,'twelve_forms':body.count('<form ')==12,
        'no_default_checked':' checked' not in body,'bound_context_and_answer':'name="context_sha256"' in body and 'name="answer_sha256"' in body,
        'actual_sources_visible':'当次实际提供ID' in body and '<details>' in body,'private_review_names_not_echoed':'SYNTHETIC TEST ONLY' not in body}
    forms=re.findall(r'<form .*?</form>',body,re.S);form=forms[0]
    base={html.unescape(k):html.unescape(v) for k,v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">',form)}
    # Invalid requests only. No synthetic decision is sent to the real ledger.
    for name,fields,headers in (
        ('csrf',{'csrf':'invalid'},{}),
        ('foreign_origin',base,{'Origin':'https://example.invalid'}),
        ('stale_answer',dict(base,answer_sha256='0'*64),{}),
        ('stale_context',dict(base,context_sha256='0'*64),{}),
        ('missing_judgments',base,{}),
        ('unknown_fields',dict(base,approve_all='yes'),{})):
        checks['reject_'+name]=request('/review',fields,headers)[0]==400
    checks['foreign_host_rejected']=request(headers={'Host':'example.invalid'})[0]==409
    after=ledger.read_bytes() if ledger.exists() else None
    checks['no_review_ledger_changes']=before==after
    v={'version':'answer-review-http-1.1','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
        'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':[k for k,b in checks.items() if not b],
        'url':url+'/','new_human_judgments':0,'new_model_requests':0,'source_sha256':record(__file__)['sha256'],
        'scope':'Actual page and deliberately invalid submissions only; does not validate human semantic judgments.'}
    write_new(ROOT/a.report,v);print(json.dumps(v,ensure_ascii=False));return v['status']!='PASS'


if __name__=='__main__':raise SystemExit(main())
