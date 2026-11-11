"""Publish metadata-only receipts for actual private browser captures and failures."""
import json
from datetime import datetime, timezone
from eval_dataset import ROOT, digest, load_jsonl, write_json


def main():
    captures=ROOT/'.runtime/rag-b0/ui-captures.jsonl'
    journal=ROOT/'.runtime/rag-b0/ui-events.jsonl'
    values=load_jsonl(captures);events={r['trace_id']:r for r in load_jsonl(journal)}
    output=ROOT/'reports/evidence/rag_b0_ui_manifest.json'
    failures=ROOT/'reports/evidence/rag_b0_failures.json'
    if output.exists() or failures.exists():raise ValueError('Existing receipts must be preserved')
    rows=[]
    for capture in values:
        event=events[capture['trace_id']]
        rows.append({'trace_id':event['trace_id'],'question':event['question'],'status':event['status'],
            'page_url':capture['page_url'],'captured_at':capture['captured_at'],
            'answer_sha256':digest(event['answer'].encode()),'rendered_last_answer_sha256':digest(capture['last_answer_text'].encode()),
            'citations':[{k:c[k] for k in ('chunk_id','source_url','law_number','source_lines','needs_rule_review')} for c in event['citations']],
            'evidence_count':capture['evidence_count'],'config_sha256':event['config_sha256'],
            'timing':event['timing'],'error':event.get('error')})
    write_json(output,{'captured_at':datetime.now(timezone.utc).isoformat(),'kind':'real_browser_submission',
        'raw_captures_sha256':digest(captures.read_bytes()),'private_ui_journal_snapshot_sha256':digest(journal.read_bytes()),
        'raw_public':False,'questions':len(rows),'answered':sum(r['status']=='answered' for r in rows),
        'refused':sum(r['status']=='refused' for r in rows),'rows':rows})
    observations=[
        ('probe-first.json','False refusal despite direct retrieved support; prompt clarified general knowledge vs verified official version.'),
        ('attempt1-smoke.jsonl','Out-of-scope model payload mixed a false flag and asserted statements; validator refused it.'),
        ('attempt2-smoke.jsonl','Mutually exclusive output schema fixed mixed states; one directly supported question was still falsely refused.'),
        ('attempt3-smoke.jsonl','Question-last evidence layout fixed that probe; verbatim generated quotation mismatch was rejected. Final model selects passage IDs; program restores original quotes.'),
        ('import-start.log','Actual Windows native access violation in Chroma/HNSW get_vectors after full UI imports; final UI delegates index/LLM operations to isolated Python workers.'),
        ('isolated-server.err.log','Pinned ChatPage required selector inputs even for a fixed corpus; supplied a read-only BaseIndex/selector contract without another actual vector index.'),
        ('attempt1-ui-events.jsonl','Initial UI attempt included a real cross-paragraph numeric/source mismatch and a truncated generation. Final B0 caps generation context to one whole chunk, limits statement length, rejects numeric facts absent from the cited paragraph, and preserves incomplete raw responses.'),
        ('attempt4-smoke.jsonl','The preceding backend smoke passed 3+1 before the independent UI surfaced additional failures; retained rather than overwritten or used as final UI proof.'),
        ('attempt5-smoke.jsonl','Paragraph numbering inside a short answer was rejected by numeric/source checks. Final source addressing uses one complete chunk.'),
        ('attempt6-smoke.jsonl','Constrained JSON string limits still allowed repeated text and mid-sentence endings despite correct IDs. Final model API uses simple ANSWER:/REFUSE: text; application validates and binds the only supplied evidence, rejecting repetitions and incomplete sentences.'),
    ]
    records=[]
    for name,note in observations:
        path=ROOT/'.runtime/rag-b0'/name
        records.append({'private_path':path.relative_to(ROOT).as_posix(),'sha256':digest(path.read_bytes()),'observation':note})
    write_json(failures,{'status':'preserved_and_fixed_for_delivery','raw_public':False,
        'scope':'Engineering failures from ad hoc smoke/startup; not a formal accuracy evaluation','cases':records})
    print(json.dumps({'ui_rows':len(rows),'answered':sum(r['status']=='answered' for r in rows),'failure_records':len(records)}))


if __name__=='__main__':main()
