"""Archive the stopped refill experiment, with invocation and dataset denominators separate."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import canonical,config,parse_selection,record
from citation_catalog_guard import safe_render
def read(p):return json.loads(p.read_text('utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    private=ROOT/'.runtime/phase2';pilot=private/'e5-second-pilot';audit=read(private/'e5-second-offline90/audit.json')
    metrics=read(private/'e5-second-scored/E5_second_refill_metrics.json');meta=read(pilot/'metadata.json');complete=read(pilot/'completed.json')
    assert metrics['decision']=='STOP_PACKING_EXPERIMENT' and len(metrics['cases'])==complete['records']==36
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())};cfg=config()
    for name,h in complete['hashes'].items():
        path=pilot/name;assert sha(path)==h;t=read(path);r=t['result']
        assert safe_render(r['selected_ids'],corpus)==(r['answer'],r['citations'])
        for attempt,norm in zip(t['observations']['model_attempts'],r['selection_audits']):
            assert parse_selection(attempt['response']['message']['content'],r['offered_ids'],cfg)==norm['normalized_selection']
    producer=meta['source_commit']
    assert hashlib.sha256(subprocess.check_output(['git','show',producer+':optimization/e5_second_candidate.py'],cwd=ROOT)).hexdigest()==meta['pilot_script']['sha256']
    for name,ref in audit['source_files'].items():
        if name=='scripts/answer_eval_engine.py':
            assert hashlib.sha256(subprocess.check_output(['git','show',producer+':'+name],cwd=ROOT)).hexdigest()==ref['sha256']
        else:assert record(ROOT/name)==ref
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    gates=read(pilot/'D036_zero_call.json');assert len(gates)==2 and all(g['result']['chat_calls']==0 and g['result']['embedding_queries']==0 and g['result']['status']=='refused' for g in gates)
    restored=subprocess.check_output(['git','rev-parse','96adf45'],cwd=ROOT,text=True).strip()
    receipt=dict(decision='STOP_PACKING_EXPERIMENT',candidate_commit=producer,control_commit=audit['control_commit'],
       control_formal_run_producer=audit['sealed_formal_producer'],runtime_86_and_598_identical=True,
       restoration_commit=restored,runtime_identical_to_D036_control=True,
       offline_cases=90,changed_prompt_cases=len(audit['changed_ids']),pilot_distinct_questions=6,pilot_invocations=36,
       model_calls_excluding_warmup=sum(v['model_calls'] for v in metrics['aggregate'].values()),
       full90_new_runs=0,full90_gate_status='NOT_RUN_PILOT_FAILED',holdout_used=False,new_human_reviews=0,
       packing_tests=read(private/'e5-second-offline90/audit.json')['packing_tests'],parser32=read(private/'e5-second-parser32.json')['status'],business84=read(private/'e5-second-business84.json')['status'],
       quote_and_parse_verified=36,D036_zero_answer_calls_in_both_arms=True,
       merge_or_push=False,reason='T026 candidate 4/4 incorrect vs control 4/4 partial; pilot citation 14/50 below same-period control 13/42')
    receipt['scoring_sources']={n:record(ROOT/n) for n in ['optimization/score_e5_second_candidate.py','optimization/experiments/D036_business_gate/source_reviews.tsv','optimization/baseline/e8b0fd6/quality_labels.json']}
    metrics['provenance']=receipt
    (a.out/'E5_second_refill_metrics.json').write_bytes((json.dumps(metrics,ensure_ascii=False,indent=2)+'\n').encode())
    shutil.copyfile(private/'e5-second-scored/E5_second_refill_calls.csv',a.out/'E5_second_refill_calls.csv')
    shutil.copyfile(private/'e5-second-offline90/contexts90.csv',a.out/'E5_second_refill_contexts90.csv')
    shutil.copyfile(private/'e5-second-offline90/audit.json',a.out/'E5_second_refill_prompt_diff90.json')
    # Exact messages and responses stay in the immutable private archive.
    report(a.out,metrics,audit)
    names=['E5_second_refill_report.md','E5_second_refill_metrics.json','E5_second_refill_calls.csv','E5_second_refill_contexts90.csv','E5_second_refill_prompt_diff90.json']
    receipt['artifacts']={n:sha(a.out/n) for n in names}
    (a.out/'E5_second_refill_receipt.json').write_bytes((json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({k:receipt[k] for k in ('decision','pilot_invocations','full90_new_runs','runtime_identical_to_D036_control','restoration_commit')}))
def report(out,m,aud):
    p=m['provenance'];groups=m['groups'];by={v['question_id']:v for v in aud['rows']}
    lines=['# E5第二候选：保留原上下文、用剩余预算补充','',
           '**结论：STOP_PACKING_EXPERIMENT。候选未通过T026专项，未进入新的完整90题回归；运行代码和配置已恢复为D036修复后的5986781。分支仅保留本地。**','',
           '## 版本、变量和执行范围','',
           f"对照：`{p['control_commit']}`；D036最终封存90题实际生产者：`{p['control_formal_run_producer']}`。Git与封存metadata.source_files核验表明86a01e9与5986781的scripts/config字节相同；5986781增加的是报告、评分和校验材料。",'',
           f"本轮候选/实际调用提交：`{p['candidate_commit']}`；恢复提交：`{p['restoration_commit']}`。候选仅修改answer_eval_engine.pack：原先装入的段和顺序保留，在Top10中依原顺序跳过已选ID和超预算段，最多5段，完整JSON消息不超过6200 UTF-8字节。",'',
           'Prompt A、模型、采样配置、Top10候选、RRF/重排、语料、索引、来源验证、两次回答调用上限及评测标签未调整。推理不读取题号、gold ID或参考要点。没有执行此前R+C−D装配设计，也没有叠加选证机制修改。',
           '本轮离线读取冻结的真实90题候选；小样本通过真实编译图的装配/来源/解析/渲染流程调用实际Qwen，但双臂的检索和重排均回放同一封存结果，不是新跑完整检索链路，不将其耗时报告成线上端到端延迟。','',
           '## 离线90题影响面','',
           f"共有{len(aud['changed_ids'])}题Prompt变化：`{','.join(aud['changed_ids'])}`；其余77题不变，包含4道前置拒答。全部保留旧段与相对顺序、无重复装入，段数和字节预算通过。90题逐段顺序/字节见CSV，完整Prompt对照见JSON。",'',
           '在86道实际到达装配的冻结输入上，此策略产生的Prompt与历史E5-A的Top10顺序扫描逐字一致。原因是两种写法都不会让之前放不下的完整段在剩余预算更少时变得能放下；原结果作为前缀也未防止新增干扰。这是D036基线上的受控复验，不应称为一个已经证明有不同效果的装配算法。','',
           '|题号|对照段顺序|候选段顺序|新增|挤出/原段换序|字节|','|---|---|---|---|---|---|']
    for q in ('T034','T026','T014'):
        v=by[q];lines.append(f"|{q}|{','.join(v['control_ids'])}|{','.join(v['candidate_ids'])}|{','.join(v['added_ids']) or '无'}|均无|{v['control_bytes']}→{v['candidate_bytes']}|")
    lines+=['','T034补入L14-01，第8名，确实没有被之前候选占满预算。T026的L12-06、L12-15在两臂Prompt中均完整保留；只有新增L12-03。T014两臂Prompt完全相同。','',
            '## 同期交替调用与逐次结果','',
            '调用计划在推理前登记：T034/T026/T014各4组对照，每题每轮AB/BA交替；D013/T002/T013各2组，共6个不同问题、36次图调用（18次/臂）。一次独立预热排除。所有首答及后续响应、实际消息和规范化选择均原样保留；没有挑选较好的重复结果。', '',
            '|题号|轮次|对照评分/要点|候选评分/要点|同Prompt？|','|---|---:|---|---|---|']
    for q in ('T034','T026','T014','D013','T002','T013'):
        for repeat in range(1,5 if q in ('T034','T026','T014') else 3):
            c=next(v for v in m['cases'] if v['question_id']==q and v['variant']=='control' and v['repeat']==repeat)
            n=next(v for v in m['cases'] if v['question_id']==q and v['variant']=='candidate' and v['repeat']==repeat)
            bits=lambda v:''.join(str(int(b)) for b in v['point_mask'])
            lines.append(f"|{q}|{repeat}|{c['grade']} / {bits(c)}|{n['grade']} / {bits(n)}|{'是' if c['messages_sha256']==n['messages_sha256'] else '否'}|")
    lines+=['', 'T034：候选4/4完整正确，对照4/4误拒答。T026：对照4/4为partial（001），候选4/4为incorrect（000），没有一次守住原有partial。T014：对照1次正确、3次错误，候选4次错误；因输入逐字相同，这些差异不能归因为新增上下文。三个补充对照题两臂均2/2完整正确。', '',
            '## 原始选段与逐条引用审核','',
            '下列原始JSON均来自本轮首次实际模型响应；每次记录另见calls.csv。评分优先沿用冻结A0的逐字相同输出审核，其次沿用同题同来源组合的既有Codex原文审核；不以精确gold ID相等替代语义判断。没有新增人工/专家评分。','']
    for q in ('T034','T026','T014'):
        lines += ['### '+q,'']
        for variant in ('control','candidate'):
            vals=sorted([v for v in m['cases'] if v['question_id']==q and v['variant']==variant],key=lambda x:x['repeat'])
            for first in dict.fromkeys(v['first_raw'] for v in vals):
                found=[v for v in vals if v['first_raw']==first];one=found[0]
                lines += [f"{variant}，轮次{','.join(str(v['repeat']) for v in found)}；直接支持引用：{','.join(one['supported_citation_ids']) or '无'}。",'```json',first,'```','']
    lines+=['T034的L14-01、L07-03支持三个必要要点；额外选择L14-03未直接支持分类/计分区别。T026对照选择L12-15仅覆盖“不当行为可警告或罚令出场”；候选选择L12-01、L12-02、L12-03均未支持所问的技术违例/身体犯规/不当行为区分。核心L12-06在两臂都存在，却都被漏选。',
            'T014正确组合由L06-06说明附加助理裁判及非强制配备，另外两段未支持该岗位条件；错误组合把L06-06换成L06-05，剩下的是预备/第四官员及VAR资料，不能回答所问岗位。','',
            '## 小样本引用、运行与全量门禁状态','', '|项目|同期对照|候选|','|---|---:|---:|']
    for label,key in [('引用支持（分子/分母）','citation_support'),('实际回答模型调用','model_calls'),('输入Token','input_tokens'),('输出Token','output_tokens')]:
        def fmt(v):
            x=m['aggregate'][v][key]
            return f"{x['numerator']}/{x['denominator']}（{100*x['value']:.2f}%）" if isinstance(x,dict) else str(x)
        lines.append(f"|{label}|{fmt('control')}|{fmt('candidate')}|")
    lines+=['', '技术完成36/36，均首答接受，无新增小样本误拒答；D036两臂均在检索/回答前结束，真实回答模型新增调用0次。装配专项6/6、既有解析专项32/32和D036双入口专项84/84通过。这些通过不能抵消T026退化。',
            '小样本引用支持率候选14/50=28.00%，低于同期对照13/42=30.95%。分母是6道有意挑选的难题和重复调用，不能当成原90题的全量引用支持率。',
            '本轮没有运行新的全量90题，因此不宣称已验证18/18、51/72、90/90或全量引用不退化。历史参照单列：A1/E4全量73/117=62.39%；D036修复后封存全量72/118=61.02%，低1.38个百分点（未四舍五入差）。这些历史数字没有因本轮6题实验更新。', '',
            '## 决策与后续边界','',
            '按事先条件停止上下文装配实验、恢复D036修复版，不追加完整90题、不继续调Top-K/Embedding/Chunk Size，也不以小样本总体正确数增加掩盖T026退化。四次重复是在本机固定设置下的观测，不等于证明任何机器/问法上都必然出错；T014同输入波动说明仍须对生成决策噪声保持区分。',
            '下一轮应固定完整上下文做证据选择对照：T026固定含L12-06/L12-15的同一份Prompt，T034固定含L14-01/L07-03的同一份Prompt，T014固定当前同一份Prompt。仅改变一种选证机制，另测漏选、错选和误拒答；不得继续同时改装配，也不把这份后续建议算成本轮已实施功能。','',
            '## 复现与封存','',
            '候选已回滚。要重跑，需在具有同样本机数据/模型的99ef600隔离检出中执行audit/pilot，使用新的输出目录；当前恢复后的入口会明确拒绝将原装配误标为候选。实际推理代码按metadata.pilot_script及99ef600的Git源码哈希核验，后续只给复现入口增加了回滚保护。',
            '```powershell',
            '.runtime/task17/venv/Scripts/python.exe -B optimization/e5_second_candidate.py audit --out <新的审计目录>',
            '.runtime/task17/venv/Scripts/python.exe -B optimization/e5_second_candidate.py pilot --audit <新的审计目录>/audit.json --out <新的运行目录>',
            '.runtime/task17/venv/Scripts/python.exe -B optimization/score_e5_second_candidate.py --run <运行目录> --out <新的计分目录>',
            '```','',
            '原始归档：.runtime/phase2/e5-second-offline90 与 e5-second-pilot。36份模型调用轨迹SHA256、两臂实际Prompt、first raw response及引用原文绑定已复核。新40题留出集仅核对封存哈希，未参与模型调用/评分；原语料、索引、Prompt与标签未改，历史E5-A失败记录保留。']
    (out/'E5_second_refill_report.md').write_bytes(('\n'.join(lines)+'\n').encode())
if __name__=='__main__':main()
