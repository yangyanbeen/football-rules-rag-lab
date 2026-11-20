"""Text-only decomposition audit, independent of E9 classifier performance.

Compare archived E7 model decompositions with E8-reviewed neutral questions.
The neutral questions are diagnostic references, not a new model output.
"""
import hashlib
import json
from pathlib import Path
from score_e7_mapping import ROOT,read,sha
from e8_source_audit import NEUTRAL


def main():
    prep=read(ROOT/'.runtime/phase2/e7-prepared-final/prepared.json');by={c['case_id']:c for c in prep['cases']}
    run=ROOT/'.runtime/phase2/e7-pilot';records=[]
    for key in ('T034-expanded','D017-native'):
        c=by[key]
        for repeat in range(1,5):
            path=run/f'{key}-B-r{repeat}.json';t=read(path)
            reqs=t['observations']['model_attempts'][-1]['mapping_validation']['requirements']
            texts=[r['requirement'] for r in reqs]
            if key=='T034-expanded':
                dimensions=['比赛中罚球点球的程序性质','点球决胜的目的','点球决胜罚中次数与本场计分的关联']
                old=[False,False,True]
                constraints=dict(two_procedures_named=True,in_match_scoring_scope_retained=True,
                    unrelated_execution_rules_added=repeat==1)
                note='旧输出复述整个计分比较，确实保留了计分维度，不能说完全没看到问题；但未单列程序性质和决胜目的，首轮还新增执行规则。'
            else:
                dimensions=['相对场地边界及罚球区的区域位置','相对罚球点的前后位置','与罚球点的最小距离']
                old=[False,False,False]
                constraints=dict(explicit_exclusion_text_present=repeat==1,
                    excluded_kicker_added_as_requirement=True,excluded_goalkeeper_added_as_requirement=repeat!=1,
                    exclusion_preserved_consistently=False)
                note='首轮第一项保留排除条件，却又新增主罚者要求；后三轮把主罚者和守门员均作为要求。泛问其他队员位置未单列三个必要维度。'
            records.append(dict(case_id=key,repeat=repeat,original_question=c['question'],old_model_requirements=texts,
                reviewed_neutral_questions=NEUTRAL[key],necessary_dimensions=dimensions,
                old_dimensions_explicit=old,reviewed_dimensions_explicit=[True,True,True],
                old_constraint_review=constraints,
                reviewed_constraints=dict(scope_retained=True,unsupported_answer_values_prefilled=False,
                    excluded_actors_reintroduced=False,
                    exclusion_repeated_in_each_question=all('除主罚者和守门员外' in q for q in NEUTRAL[key]) if key=='D017-native' else None),
                review_note=note,source_trace=path.relative_to(ROOT).as_posix(),source_sha256=sha(path)))
    value=dict(new_model_calls=0,reviewer='Codex text review against frozen required dimensions; not new human/expert review.',
        reviewed_neutral_source='optimization/e8_source_audit.py',reviewed_neutral_source_sha256=sha(ROOT/'optimization/e8_source_audit.py'),
        E8_offline_reference_sha256=sha(ROOT/'.runtime/phase2/e8-offline/metrics.json'),
        comparison='Archived model text versus E8-reviewed neutral restatement. Not a new-versus-old model A/B and not end-to-end verification.',
        dimension_scoring='Explicitly identified dimensions, not answer correctness. A combined restatement can retain a broad target while failing to split distinct subquestions.',
        records=records,
        conclusion='T034 has an independent decomposition target; D017 must preserve excluded actors in every subquestion and avoid reintroducing them. This can be diagnosed without a verifier, but no new decomposition model was run and no end-to-end improvement is claimed.')
    out=ROOT/'.runtime/phase2/e9-scored';out.mkdir(parents=True,exist_ok=True)
    (out/'decomposition_diagnostic.json').write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(dict(text_observations=len(records),model_calls=0,new_decomposition_model_run=False)))
if __name__=='__main__':main()
