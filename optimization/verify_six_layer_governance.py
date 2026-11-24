"""Adversarial diagnostic/plan controls; no new retrieval or model inference."""
import copy,json,sys,unittest
from pathlib import Path
from six_layer_core import ROOT,canonical,digest,diagnose,check_plan,retrieval_metrics,read,runtime_parameter_consistency
from rag_diagnostics import verify_trace,TraceError,checked_review


def fixture(channel=None,fused=None,ranked=None,prompt=None,selected=None,status='answered'):
    channel=['A','N'] if channel is None else channel
    fused=channel if fused is None else fused
    ranked=fused[:10] if ranked is None else ranked
    prompt=ranked[:5] if prompt is None else prompt
    selected=prompt[:1] if selected is None else selected
    rows=lambda values:[dict(chunk_id=c,rank=i) for i,c in enumerate(values,1)]
    return dict(seconds=20,resources=dict(available_min_GiB=2),result=dict(question='test',error=None,status=status,
        retrieval=dict(channels=dict(dense=rows(channel),bm25=[]),before=rows(fused),results=rows(ranked),reranker=dict(results=[]),query='test'),
        retrieved_ids=ranked,offered_ids=prompt,selected_ids=selected,context=[],messages=[],attempts=[],timing=dict(total_seconds=15)))


LABEL=dict(question_id='X',answerable=True,expected_chunk_ids=['A'])
WRONG=dict(grade='incorrect',point_mask=[False],supported_citation_ids=[])
CORRECT=dict(grade='correct',point_mask=[True],supported_citation_ids=['A'])


class Attribution(unittest.TestCase):
    def codes(self,value):return {f['code'] for f in value['findings']}
    def test_data_absent_precedes_candidate_failure(self):
        value=diagnose(fixture(['N']),LABEL,WRONG,known_ids={'N'})
        self.assertEqual(value['primary_layer'],'data')
    def test_candidate_missing(self):
        value=diagnose(fixture(['N']),LABEL,WRONG)
        self.assertIn('annotated_candidate_missing',self.codes(value));self.assertEqual(value['primary_layer'],'retrieval')
    def test_fusion_to_rerank_window(self):
        names=['N'+str(i) for i in range(40)]+['A']
        value=diagnose(fixture(names),LABEL,WRONG)
        self.assertIn('rerank_candidate_window',self.codes(value));self.assertEqual(value['primary_layer'],'rerank')
    def test_rerank_output_cutoff(self):
        value=diagnose(fixture(['A','N'],ranked=['N']),LABEL,WRONG)
        self.assertIn('rerank_output_cutoff',self.codes(value))
    def test_rank8_not_examined_is_context(self):
        names=['N'+str(i) for i in range(7)]+['A']
        value=diagnose(fixture(names),LABEL,WRONG)
        self.assertIn('packing_window_loss',self.codes(value));self.assertEqual(value['primary_layer'],'context')
    def test_examined_but_not_packed_is_budget(self):
        value=diagnose(fixture(['A','N'],prompt=['N']),LABEL,WRONG)
        self.assertIn('packing_budget_loss',self.codes(value))
    def test_false_refusal_with_full_evidence(self):
        value=diagnose(fixture(selected=[],status='refused'),LABEL,dict(WRONG,grade='false_refusal'))
        self.assertIn('false_refusal_with_evidence',self.codes(value))
    def test_correct_equivalent_evidence_overrides_missing_gold(self):
        value=diagnose(fixture(['B']),LABEL,dict(CORRECT,supported_citation_ids=['B']))
        self.assertIsNone(value['primary_layer']);self.assertFalse(value['findings'])
    def test_correct_answer_can_still_fail_citations(self):
        value=diagnose(fixture(selected=['A','N']),LABEL,CORRECT)
        self.assertEqual(value['unsupported_citation_ids'],['N']);self.assertEqual(value['grade'],'correct')
        self.assertEqual(value['primary_layer'],'generation')
    def test_no_review_never_fabricates_citation_accuracy(self):
        value=diagnose(fixture(['N']),LABEL)
        self.assertIsNone(value['unsupported_citation_ids']);self.assertEqual(value['semantic_review'],'pending')
        self.assertIsNone(value['primary_layer']);self.assertEqual(value['findings'][0]['severity'],'hypothesis')
    def test_operational_failure_is_not_false_refusal(self):
        t=fixture(selected=[],status='refused');t['result']['error']='TimeoutError'
        value=diagnose(t,LABEL,dict(WRONG,grade='runtime_error'))
        self.assertEqual(value['primary_layer'],'engineering');self.assertNotIn('false_refusal_with_evidence',self.codes(value))
        self.assertIsNone(value['unsupported_citation_ids'])
    def test_missing_result_keeps_stable_engineering_schema(self):
        value=diagnose(dict(result=None,error='worker crashed',seconds=4),LABEL,dict(WRONG,grade='runtime_error'))
        self.assertEqual(value['primary_layer'],'engineering');self.assertEqual(value['performance']['wall_seconds'],4)
        self.assertIn('missing_result',self.codes(value))
    def test_schema_repair_is_not_semantic_failure(self):
        t=fixture();t['result']['attempts']=[dict(error='bad JSON'),dict(error=None)]
        value=diagnose(t,LABEL,CORRECT)
        self.assertIn('schema_repair',self.codes(value));self.assertIsNone(value['primary_layer'])
    def test_rerank_truncation_observation_not_prompt_loss(self):
        t=fixture();t['result']['retrieval']['reranker']['results']=[dict(chunk_id='A',original_tokens=600,used_tokens=512,truncated_tokens=88)]
        value=diagnose(t,LABEL,CORRECT)
        self.assertIn('pair_input_truncated',self.codes(value));self.assertIsNone(value['primary_layer'])
    def test_missing_memory_does_not_pass_as_zero_usage(self):
        t=fixture();t.pop('resources');value=diagnose(t,LABEL,CORRECT)
        self.assertFalse(value['performance']['resource_observed']);self.assertIsNone(value['performance']['minimum_available_GiB'])
    def test_instant_stage_minimum_can_fail_resource_gate(self):
        t=fixture();t['resources']['stage_events']=[dict(stage='test',monotonic=1,memory=dict(available=.8*2**30))]
        value=diagnose(t,LABEL,CORRECT)
        self.assertIn('memory_below_limit',self.codes(value));self.assertEqual(value['primary_layer'],'engineering')
    def test_original_question_is_hash_bound_and_not_invented(self):
        t=fixture();t['result']['query_resolution']=dict(original_question_sha256=digest('它呢'.encode()),history_turns=1,outcome='rewritten')
        value=diagnose(t,original_question='它呢');self.assertTrue(value['query']['original_text_available'])
        self.assertIsNone(value['performance']['total_model_calls'])
        self.assertIn('original_question_hash_mismatch',self.codes(diagnose(t,original_question='other')))
        self.assertFalse(diagnose(t)['query']['original_text_available'])
    def test_correct_refusal_excluded_from_retrieval_denominator(self):
        q=dict(question_id='R',answerable=False,expected_chunk_ids=[])
        c=diagnose(fixture([],selected=[],status='refused'),q,dict(grade='correct_refusal',point_mask=[],supported_citation_ids=[]))
        a=diagnose(fixture(),LABEL,CORRECT)
        self.assertEqual(retrieval_metrics([a,c],'reranked',10)['questions'],1)
    def test_union_keeps_bm25_only_evidence_beyond_dense80(self):
        t=fixture(['N'+str(i) for i in range(80)],fused=['A'],ranked=['A'],prompt=['A'],selected=['A'])
        t['result']['retrieval']['channels']['bm25']=[dict(chunk_id='A',rank=1)]
        c=diagnose(t,LABEL,CORRECT)
        self.assertEqual(retrieval_metrics([c],'union',160)['annotated_any_hit']['value'],1)


class Plans(unittest.TestCase):
    def setUp(self):
        self.base=dict(files={'config/a.json':{'sha256':'a'}},intended_environment={'FOOTBALL_LOW_MEMORY':'1'})
        self.plan=dict(baseline_snapshot_sha256=digest(canonical(self.base)),layer='generation',
            variable=dict(name='selection_instruction',before='A',after='B'),hypothesis='One explicit selection instruction may reduce over-selection.',
            development_dataset='dev40',metrics=['citation_support'],thresholds={'special':{'independent_questions':4,'paired_repeats':2,'pass_conditions':['source supports points']},'resources':{'max_wall_seconds':60,'min_available_GiB':1}},
            stop_conditions=['original correct case regresses'],allowed_files=['optimization/experiments/E16/candidate_prompt.txt'],unseen_datasets=[],merge=False)
    def test_valid_protocol_is_not_experiment_execution(self):
        r=check_plan(self.plan,self.base,copy.deepcopy(self.base));self.assertTrue(r['valid']);self.assertEqual(r['new_model_calls'],0)
    def test_exposed_holdout_cannot_be_unseen(self):
        self.plan['unseen_datasets']=['exposed40'];self.assertFalse(check_plan(self.plan,self.base)['valid'])
    def test_regression_set_cannot_be_declared_development(self):
        self.plan['development_dataset']='regression50';self.assertFalse(check_plan(self.plan,self.base)['valid'])
    def test_two_variables_are_rejected(self):
        self.plan['variables']=['a','b'];self.assertFalse(check_plan(self.plan,self.base)['valid'])
    def test_undeclared_model_configuration_change_is_rejected(self):
        current=copy.deepcopy(self.base);current['files']['config/dense_index.json']={'sha256':'changed'}
        self.assertFalse(check_plan(self.plan,self.base,current)['valid'])
    def test_untracked_new_code_is_detected(self):
        current=copy.deepcopy(self.base);current['untracked_source_observations']={'scripts/new.py':{'sha256':'x'}}
        self.assertFalse(check_plan(self.plan,self.base,current)['valid'])
    def test_frozen_label_edits_not_allowed_even_if_declared(self):
        self.plan['allowed_files']=['optimization/datasets/dev_40.json'];self.assertFalse(check_plan(self.plan,self.base)['valid'])
    def test_snapshot_identity_tampering_is_rejected(self):
        self.plan['baseline_snapshot_sha256']='wrong';self.assertFalse(check_plan(self.plan,self.base)['valid'])
    def test_special_sample_counts_must_be_declared(self):
        self.plan['thresholds']['special']=None;self.assertFalse(check_plan(self.plan,self.base)['valid'])
    def test_memory_gate_cannot_be_lowered_to_pass(self):
        self.plan['thresholds']['resources']['min_available_GiB']=.5;self.assertFalse(check_plan(self.plan,self.base)['valid'])
    def test_active_code_and_config_drift_is_rejected(self):
        r=read(ROOT/'config/reranker_experiment.json');a=read(ROOT/'config/answer_evaluation.json')
        self.assertTrue(runtime_parameter_consistency(r,a)['verified'])
        r['channel_top_k']=10
        with self.assertRaises(ValueError):runtime_parameter_consistency(r,a)


class SourceReviews(unittest.TestCase):
    def setUp(self):
        self.label=dict(question_id='X',question='test',answerable=True,expected_answer_points=['point'],required_conditions=['scope'])
        self.result=dict(selected_ids=['B'],status='answered')
        self.review=dict(question_id='X',question_sha256=digest(b'test'),trace_sha256='hash',grade='correct',
            point_mask=[True],condition_mask=[True],supported_citation_ids=['B'],reviewer='AI source audit',note='Equivalent paragraph explicitly supports point and scope.')
    def test_review_allows_supported_equivalent_ids(self):
        self.assertEqual(checked_review(self.review,self.label,self.result,'hash')['grade'],'correct')
    def test_review_cannot_move_to_different_trace(self):
        with self.assertRaises(ValueError):checked_review(self.review,self.label,self.result,'different')
    def test_missing_scope_cannot_be_full_correct(self):
        self.review['condition_mask']=[False]
        with self.assertRaises(ValueError):checked_review(self.review,self.label,self.result,'hash')
    def test_review_cannot_credit_unselected_paragraph(self):
        self.review['supported_citation_ids']=['A']
        with self.assertRaises(ValueError):checked_review(self.review,self.label,self.result,'hash')


@unittest.skipUnless((ROOT/'.runtime/phase2/e15-lowmemory90-01/worker/D001-B.json').exists(),'Private archive absent')
class RealTraceIntegrity(unittest.TestCase):
    def setUp(self):self.t=read(ROOT/'.runtime/phase2/e15-lowmemory90-01/worker/D001-B.json')
    def test_body_tampering_rejected_before_scoring(self):
        self.t['result']['context'][0]['content_zh']='fabricated'
        with self.assertRaises(TraceError) as c:verify_trace(self.t,set())
        self.assertEqual(c.exception.layer,'data')
    def test_prompt_tampering_rejected(self):
        self.t['result']['messages'][0]['content']='different prompt'
        with self.assertRaises(TraceError) as c:verify_trace(self.t,set())
        self.assertEqual(c.exception.layer,'context')
    def test_unoffered_citation_rejected(self):
        self.t['result']['selected_ids']=['UNKNOWN']
        with self.assertRaises(TraceError) as c:verify_trace(self.t,set())
        self.assertEqual(c.exception.layer,'generation')


if __name__=='__main__':unittest.main(verbosity=2)
