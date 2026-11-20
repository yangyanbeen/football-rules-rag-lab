"""Offline sensitivity: isolate optional non-direct quote failures from coverage.

The live candidate required quotations for partial/refutation too, a stronger
contract than the user's minimum direct-support quote requirement. This replay
does not alter that run, its costs, prompts, raw responses, or formal scores.
Non-direct labels never enter coverage; invalid quotations remain flagged.
"""
import argparse
import json
from pathlib import Path
from score_e7_mapping import ROOT,read,sha
from e7_evidence_map import parse_mapping,unique_object
from e8_pair_verifier import LABELS,parse_verdict


def project(content,body):
    value=json.loads(content,object_pairs_hook=unique_object)
    if not isinstance(value,dict) or set(value)!={'relation','quotes','reason'}:
        raise ValueError('Invalid response object')
    if value['relation'] not in LABELS:raise ValueError('Unknown relation')
    if value['relation']=='direct_support':
        return parse_verdict(content,body)
    # Read only the non-direct decision, retaining its original quote failure.
    # No source assertion from such a decision is admitted into selection.
    error=None
    try:parse_verdict(content,body)
    except (ValueError,TypeError) as exc:error=str(exc)
    return dict(**value,quote_protocol_error=error,enters_coverage=False,
                semantic_support_verified_by_program=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);prep=read(a.prepared);pairs=[]
    for planned in prep['pairs']:
        path=a.run/(planned['pair_id']+'.json');t=read(path);chosen=None;used=None
        for ix,at in enumerate(t['attempts'],1):
            if not at.get('response'):continue
            try:chosen=project(at['response']['message']['content'],t['paragraph']['content_zh']);used=ix;break
            except (ValueError,TypeError,KeyError):continue
        pairs.append(dict(pair_id=t['pair_id'],case_id=t['case_id'],repeat=t['repeat'],requirement_index=t['requirement_index'],
            chunk_id=t['paragraph']['chunk_id'],projection=chosen,used_archived_attempt=used,trace_sha256=sha(path)))
    source={c['case_id']:c for c in read(ROOT/'.runtime/phase2/e7-prepared-final/prepared.json')['cases']};cases=[]
    for c in prep['cases']:
        rs=[v for v in pairs if v['case_id']==c['case_id'] and v['repeat']==c['repeat']]
        if any(v['projection'] is None for v in rs):
            cases.append(dict(case_id=c['case_id'],repeat=c['repeat'],grade='projection_failed'));continue
        requirements=[dict(requirement=req['requirement'],supporting_ids=[v['chunk_id'] for v in rs
            if v['requirement_index']==i and v['projection']['relation']=='direct_support']) for i,req in enumerate(c['requirements'])]
        selection,audit=parse_mapping(json.dumps({'requirements':requirements},ensure_ascii=False),c['offered_ids'],3)
        mask=[bool(set(selection['chunk_ids'])&set(v)) for v in source[c['case_id']]['support_per_point']]
        cases.append(dict(case_id=c['case_id'],repeat=c['repeat'],requirements=requirements,selected_ids=selection['chunk_ids'],
            point_mask=mask,grade='false_refusal' if not selection['chunk_ids'] else 'correct' if all(mask) else 'partial' if any(mask) else 'incorrect'))
    value=dict(kind='Diagnostic coverage projection of archived responses only; not a new live candidate or a replacement score',
        new_model_calls=0,original_live_costs_unchanged=True,non_direct_bad_quotes_not_validated=True,
        direct_quotes_still_required=True,pairs=pairs,cases=cases,
        caveat='Removing non-direct quote failures can expose empty coverage, but cannot manufacture a direct support label or establish how a new prompt/run would behave.')
    (a.out/'quote_protocol_projection.json').write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(dict(new_model_calls=0,grades=[v['grade'] for v in cases],direct_relations=sum(v['projection'] is not None and v['projection']['relation']=='direct_support' for v in pairs),
        non_direct_quote_errors=sum(bool((v['projection'] or {}).get('quote_protocol_error')) for v in pairs)),ensure_ascii=False))

if __name__=='__main__':main()
