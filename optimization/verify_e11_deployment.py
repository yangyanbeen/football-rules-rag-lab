"""No-inference integration checks: failed preflights cannot reach quality work."""
import copy,json
from e11_deployment import ROOT,E10,canonical,preflight_sequence,read

def main():
    resource=dict(samples=2,resource_abort=False,process_rss_peak_GiB=5.2,available_min_GiB=1.2)
    good=dict(protocol_pass=True,technical_complete=True,seconds=20,resources=resource)
    scenarios=[('generic_memory',{'resources':dict(resource,available_min_GiB=.8)},None,'GENERIC_PREFLIGHT_FAILED',1),
        ('generic_protocol',{'protocol_pass':False},None,'GENERIC_PREFLIGHT_FAILED',1),
        ('representative_memory',None,{'resources':dict(resource,available_min_GiB=.8)},'REPRESENTATIVE_PREFLIGHT_FAILED',2),
        ('representative_protocol',None,{'protocol_pass':False},'REPRESENTATIVE_PREFLIGHT_FAILED',2),
        ('representative_latency',None,{'seconds':91},'REPRESENTATIVE_PREFLIGHT_FAILED',2),
        ('pass',None,None,'PREFLIGHTS_PASSED',2)]
    checks=[]
    for name,first,second,expected,count in scenarios:
        calls=[]
        def call(label,change):calls.append(label);return {**copy.deepcopy(good),**(change or {})}
        result=preflight_sequence(lambda:call('generic',first),lambda:call('representative',second))
        assert result['status']==expected and len(calls)==count
        checks.append(name)
    prepared=read(ROOT/'.runtime/phase2/e11-prepared/prepared.json');old=read(E10)
    assert prepared['e10']['schedule']==old['schedule'] and prepared['e10']['configs']==old['configs']
    assert prepared['e10']['cases']==old['cases'];checks.append('frozen_36_and_inputs_identical')
    c=prepared['representative'];t=read(ROOT/c['source_trace']);at=t['observations']['model_attempts'][0]
    assert c['question_id'].startswith('D') and c['messages']==at['messages'] and c['schema']==at['schema']
    assert 5580<=len(canonical(c['messages']))==c['prompt_bytes']<=6200;checks.append('representative_real_development_packet')
    print(json.dumps(dict(passed=len(checks),checks=checks,model_inference_calls=0)))

if __name__=='__main__':main()
