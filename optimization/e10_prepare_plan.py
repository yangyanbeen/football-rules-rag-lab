"""Freeze E10's question/context packets and acceptance rules before model QA."""
import copy,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,canonical,config
from e5_second_candidate import inputs
from e10_resources import snapshot

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
    with p.open('xb') as f:f.write((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())

def main():
    d=ROOT/'optimization/experiments/E10_answer_model';d.mkdir(parents=True,exist_ok=False)
    out=ROOT/'.runtime/phase2/e10-frozen';out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'.runtime/phase2/e7-prepared-final/prepared.json';by={c['case_id']:c for c in read(source)['cases']}
    stress=['T026-expanded','T034-expanded','D017-native','D021-native']
    controls=[q+'-native' for q in ('D001','D002','D003','D012','D004','D009')]
    cases=[copy.deepcopy(by[k]) for k in stress+controls]
    for c in cases:
        assert sha(ROOT/c['source_trace'])==c['source_sha256']
        assert c['messages'][0]['content']==(ROOT/'config/answer_evaluation_system.txt').read_text('utf8')
    schedule=[];pair=0
    for repeat in range(1,4):
        for key in (stress+controls if repeat==1 else stress):
            pair+=1
            for variant in ('AB' if pair%2 else 'BA'):
                schedule.append(dict(case_id=key,variant=variant,repeat=repeat,phase='primary'))
    plan=dict(control='5986781 + Prompt A + qwen2.5:3b',candidate_family='Qwen2.5-7B-Instruct',quantization='Q4_K_M',
        official_distribution='https://modelscope.cn/models/qwen/Qwen2.5-7B-Instruct-GGUF',candidate_digest='Pin after verified isolated import; no QA before pinning',
        context_count=10,primary_observations=36,stress_repeats=3,control_repeats=1,schedule=schedule,
        quality_gates=dict(T026_expanded='>=2/3 correct',T034_expanded='3/3 correct',D017='3/3 correct',D021='3/3 correct, both restart treatments retained',
            false_refusal_recovery='At least two of D001/D002/D003/D012: primary A false-refusal, B correct; paired confirmation B 3/3 correct and A false-refusal at least 2/3',
            original_controls='D004/D009 primary B fully correct; confirm any decline but retain initial decline as gate failure',
            citation='Primary B whole-frozen-point support ratio >= same-round A; each original control not worse. Report partial-support sensitivity separately.',
            technical='36/36 terminal completion under unchanged <=2 generation attempts; report first-answer protocol rate and all retries separately'),
        retest=dict(trigger='Recovered single-pass false-refusal question, or original-correct control with answer/citation regression',
            affected_contexts_only=True,additional_pairs_per_context=2,order=['AB','BA'],maximum_extra_observations=24,
            primary_metrics_never_overwritten=True),
        cost_gates=dict(candidate_wall_p95_seconds=60,candidate_single_wall_max_seconds=90,
            model_service_process_tree_rss_peak_GiB=6.5,system_available_min_GiB=1,
            emergency_abort_available_below_GiB=.35,emergency_consecutive_half_second_samples=3,
            deployment_preflight_resource_failure='Do not start QA; report deployment unavailable and run independent decomposition fallback'),
        deployment=dict(ollama_version='0.40.16',num_thread=8,num_gpu=0,num_ctx=8192,num_predict=1024,
            temperature=0,seed=42,keep_alive='10m',maximum_loaded_models=1,parallel_requests=1,
            chat_template='Copy exact baseline template, system and stop parameters to isolate answer weights',
            endpoint='127.0.0.1:11434',store='.runtime/phase2/e10-models',model_download_excluded_from_latency=True,
            generation_loading_included_in_latency=True,resource_sample_interval_seconds=.5),
        deployment_probe=dict(model_calls=1,prompt='Generic ready JSON, no evaluation question',excluded_from_quality_denominator=True),
        latency_scope='Route through rendering on frozen retrieval fixtures; no fresh embedding/rerank latency. Reload duration recorded separately; max_loaded_models=1.',
        followup='Only quality and cost pass => fixed 90 A/B. Quality only => assess route separately. No available model or pilot quality failure => standalone question-only decomposition.',
        holdout_used=False,full90_executed=False)
    dump(d/'plan.json',plan)
    dump(d/'context_review.json',dict(cases=[{k:c[k] for k in ('case_id','question','necessary_points','support_per_point','offered_ids','source_trace','source_sha256')} for c in cases],
        review='Reuse frozen E7/E8 source judgments, including equivalent-source D004 reconciliation; Codex source review, not new human/expert review.',
        partial_source_sensitivity={'D017-native':['L01-06','L14-03']}))
    refs=inputs();refs[source.relative_to(ROOT).as_posix()]=record(source)
    dump(out/'inputs.json',dict(cases=cases,schedule=schedule,source_files=refs,plan_sha256=sha(d/'plan.json'),
        review_sha256=sha(d/'context_review.json'),hardware=snapshot(),model_config=config()['llm'],holdout_used=False))
    print(json.dumps(dict(contexts=10,primary_observations=len(schedule),hardware=snapshot()),ensure_ascii=False))
if __name__=='__main__':main()
