"""Verify and deliver the E6 fixed-context pilot without promoting its candidate."""
import argparse,csv,hashlib,io,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import canonical,config,parse_selection,record
from citation_catalog_guard import safe_render
def read(p):return json.loads(p.read_text('utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    private=ROOT/'.runtime/phase2';run=private/'e6-pilot';prepared=read(private/'e6-prepared-final/prepared.json');meta=read(run/'metadata.json');done=read(run/'completed.json')
    m=read(private/'e6-scored/E6_selection_metrics.json');assert m['decision']=='STOP_E6_CANDIDATE' and len(m['cases'])==76
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())};cfg=config()
    sources={v['case_id']:v for v in prepared['cases']};cases={};parses=renders=0
    assert sha(private/'e6-prepared-final/prepared.json')==meta['prepared_sha256']
    assert sha(ROOT/'optimization/e6_selection.py')==meta['pilot_script']['sha256']
    for name,h in done['hashes'].items():
        path=run/name;assert sha(path)==h;t=read(path);r=t['result'];c=sources[t['case_id']];ats=t['observations']['model_attempts']
        assert ats[0]['messages'][1:]==c['messages'][1:] and ats[0]['schema']==c['schema'] and len(canonical(ats[0]['messages']))<=6200
        assert len(ats)==r['chat_calls']==len(r['selection_audits'])<=2
        assert r['embedding_queries']==t['actual_new_embedding_calls']==t['actual_new_reranker_calls']==0
        for item,audit in zip(ats,r['selection_audits']):
            assert item['response']==audit['response']
            assert parse_selection(item['response']['message']['content'],r['offered_ids'],cfg)==audit['normalized_selection'];parses+=1
        assert safe_render(r['selected_ids'],corpus)==(r['answer'],r['citations']);renders+=1
        cases[(t['case_id'],t['repeat'],t['variant'])]=t
    for case,repeat,variant in cases:
        a1=cases[(case,repeat,'A')]['observations']['model_attempts'][0];b1=cases[(case,repeat,'B')]['observations']['model_attempts'][0]
        assert a1['messages'][1:]==b1['messages'][1:] and a1['schema']==b1['schema']
    assert len(cases)==done['records']==76
    gates=read(run/'D036_zero_call.json');assert len(gates)==2
    assert all(v['result']['status']=='refused' and v['result']['chat_calls']==v['result']['embedding_queries']==0 for v in gates)
    for name,ref in prepared['source_files'].items():assert record(ROOT/name)==ref
    for v in 'AB':assert sha(ROOT/f'optimization/experiments/E6_evidence_selection/prompt_{v}.txt')==meta['prompt_hashes'][v]
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    assert m['addendum_sensitivity']['point_masks_changed']==0
    receipt=dict(decision='STOP_E6_CANDIDATE',control_commit=meta['control_commit'],actual_run_commit=meta['source_commit'],
       total_contexts=11,distinct_questions=9,actual_invocations=76,paired_comparisons=38,
       identical_question_body_order_schema_pairs=38,parses_verified=parses,full_source_renders_verified=renders,
       correctly_selected_support_but_render_lost=0,D036_answer_calls={'A':0,'B':0},
       production_runtime_and_prompt_unchanged=True,candidate_promoted=False,full90_new_runs=0,holdout_used=False,new_human_reviews=0,
       model=meta['model'],annotation_sha256=prepared['review_sha256'],prompt_sha256=meta['prompt_hashes'],
       scoring_sources={n:record(ROOT/n) for n in ['optimization/score_e6_selection.py','optimization/experiments/E6_evidence_selection/review_addendum.json']},
       scope='Repeated fixed-context actual model selection test, not a new full90 or fresh retrieval benchmark')
    m['verification']=receipt
    (a.out/'E6_selection_metrics.json').write_bytes((json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode())
    shutil.copyfile(private/'e6-scored/E6_selection_calls.csv',a.out/'E6_selection_calls.csv')
    shutil.copyfile(ROOT/'optimization/experiments/E6_evidence_selection/point_evidence_review.md',a.out/'E6_point_evidence_review.md')
    shutil.copyfile(private/'e6-prepared-final/prepared.json',a.out/'E6_fixed_contexts.json')
    for v in 'AB':shutil.copyfile(ROOT/f'optimization/experiments/E6_evidence_selection/prompt_{v}.txt',a.out/f'E6_prompt_{v}.txt')
    report(a.out,m)
    files=['E6_selection_report.md','E6_selection_metrics.json','E6_selection_calls.csv','E6_point_evidence_review.md','E6_fixed_contexts.json','E6_prompt_A.txt','E6_prompt_B.txt']
    receipt['artifacts']={n:sha(a.out/n) for n in files}
    (a.out/'E6_selection_receipt.json').write_bytes((json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({k:receipt[k] for k in ('decision','actual_invocations','paired_comparisons','parses_verified','full_source_renders_verified','production_runtime_and_prompt_unchanged','full90_new_runs')}))
def report(out,m):
    v=m['verification'];g=m['groups'];agg=m['full_evidence_aggregate']
    lines=['# E6：固定上下文、只改证据选择指令 A/B','',
      '**结论：STOP_E6_CANDIDATE。B有局部覆盖收益，但没有减少充分证据下的误拒答，也未通过T026扩充上下文压力门槛；不进入新的完整90题，不替换生产Prompt A。**','',
      '## 首先回答两个问题','',
      '1. 证据已在Prompt时，误拒答能否减少？本轮未观察到减少。D001有明确绿色原文，A/B均2/2误拒答；完整证据样本每组34次调用，误拒答均2次。样本中的误拒答只由一个代表问题产生，不能据此推断所有误拒类型。',
      '2. T026增加干扰段后，能否重新选中真正支持答案的段？本候选不能。现行上下文A为4/4 partial（001），B为4/4 correct（111），B四次均选到L12-06；但扩充版A/B均4/4 incorrect（000），均漏选仍在首位的L12-06，B没有恢复抗干扰能力。','',
      '## 基线、唯一变量与预先核验','',
      f"运行基线：`{v['control_commit']}`。实际实验提交：`{v['actual_run_commit']}`。scripts/config与5986781逐字相同；候选只存放在optimization实验目录，未替换config中的Prompt A。",'',
      '先逐项阅读6道开发题和3道压力/边界题实际Prompt中的原文，建立11份上下文的必要要点、逐要点支持段、是否充分三项表，再写候选指令。开发题：D001（证据充分误拒）、D019（错选）、D021（部分覆盖），D004/D009/D017为原本正确对照；压力：T026两份、T014一份、T034两份归档上下文。原文核验由Codex完成，没有新增人工或裁判专家复核。',
      'D021的L13-05本身同时说明任意球可能越位和界外球越位例外，允许这一单段等价支持；评分不要求重现既有gold ID列表。T026的L12-15只覆盖处罚要点，不能代替L12-06的概念定义；T014只提到附加助理裁判的替补关系不足以识别所问岗位。',
      'A保持Prompt A。B只替换选证指令块：按问题要点选择足够的最少直接支持段，同段可支持多项，同主题/重复支持不入选，部分覆盖沿用既有回答范围。两个系统指令分别1400/1399 UTF-8字节；其余政策段不变，正文、问题、顺序、Schema及模型设置在每一对中完全一致。最多3个ID、2次回答调用和6200字节预算不变。逐题要点标注从未送入模型。','',
      '## 重复对照与范围','',
      '预登记76次真实Qwen调用：9个不同问题、11份上下文。三道压力题的各上下文及三个原正确对照各4轮，其余三个开发错题各2轮；每轮AB/BA交替，共38对。温度0/seed42，现有固定本机Qwen2.5:3b配置；单独预热排除。冻结检索/重排结果，只重跑真实模型选段及图的解析、来源、渲染流程，不把这段延迟当成完整实时检索链路性能。', '',
      '|上下文|A评分分布|B评分分布|A要点掩码（每次）|B要点掩码（每次）|','|---|---|---|---|---|']
    for key in g:
        a,b=g[key]['A'],g[key]['B'];lines.append(f"|{key}|{json.dumps(a['grades'],ensure_ascii=False)}|{json.dumps(b['grades'],ensure_ascii=False)}|{','.join(a['masks'])}|{','.join(b['masks'])}|")
    lines+=['','T014的A在相同输入下1次正确、3次错误；B本次4次均正确。这是重复观测的分布，不能用一次恢复或4次样本推断未来稳定正确。',
      'T034-native仅能直接覆盖后两个要点。两组4次均拒答，已提供要点覆盖均为0/8；这说明也未利用可答部分，但它不作为“上下文完整”的误拒答样本。T034-expanded两组均4/4完整正确，B没有修复A本来就能回答的这份上下文。','',
      '## 汇总指标：仅完整证据样本，非90题成绩','',
      '每组38次调用中，排除T034-native的4次边界调用，以下分母是34次重复调用、82个要点出现次数。相同题目的重复不可当作独立测试题。','',
      '|指标|A|B|','|---|---:|---:|']
    for label,key in [('要点覆盖','covered_points'),('引用支持','citation_support')]:
        def fmt(arm):x=agg[arm][key];return f"{x['numerator']}/{x['denominator']}（{x['value']*100:.2f}%）"
        lines.append(f"|{label}|{fmt('A')}|{fmt('B')}|")
    lines += [f"|完整正确观测数|{agg['A']['grades'].get('correct',0)}/34|{agg['B']['grades'].get('correct',0)}/34|",
      f"|充分证据下误拒答|{agg['A']['false_refusals']}/34|{agg['B']['false_refusals']}/34|",
      f"|总选段数|{agg['A']['selected_count']}|{agg['B']['selected_count']}|",'',
      '覆盖和引用支持改善来自T026-native、D019、T014等局部恢复；最少证据的行为没有可靠实现。D004从A每次1段变成B每次3段，覆盖没有增加；D009的B每次3段而A多数只用1段，两个原正确题的引用比例均下降。不能用总体覆盖改善掩盖冗余和关键压力失败。', '',
      '引用审核保留了一项等价段补记：最初要点表漏列D004的L12-10对必须保留守门员的支持，旧source_reviews.tsv已明确计入它。原预登记表未覆盖或改写，补记文件独立保存并对两组一致应用。它没有改变76次调用中任何一项要点掩码，只让B的4次D004引用支持各增加1。若严格使用原表，B引用为42/88而非46/88，仍高于A的30/74；候选仍因T026-expanded失败而停止，决策不依赖补记。', '',
      '## T026：每次首答与真正遗漏位置','',
      '|上下文/组|四次实际选段（均相同）|支持要点|','|---|---|---|',
      '|现行/A|L12-01,L12-02,L12-15|仅不当行为处罚（001）|',
      '|现行/B|L12-01,L12-06,L12-15|三个要点完整（111），但L12-01冗余|',
      '|扩充/A|L12-01,L12-02,L12-03|无（000）|',
      '|扩充/B|L12-01,L12-02,L12-03|无（000）|','',
      '扩充版的L12-06、L12-15均完整保留，顺序未变。这里不是支持段被装配挤掉；候选指令仍反复漏选核心定义段。4次样本说明本轮压力门槛没有通过，不是对所有运行环境的因果定论。', '',
      '## 渲染、Schema与拒答门禁核验','',
      f"已核验{v['paired_comparisons']}对正文/问题/顺序/Schema相同；{v['parses_verified']}次实际响应与normalized_selection绑定；{v['full_source_renders_verified']}次最终输出与原段safe_render逐字一致。未发现正确支持段已经选中、却因渲染丢失要点的例子。当前证据指向漏选/错选，不支持先改回答渲染。",
      'D036两组均由原业务门禁拒答，检索和回答模型调用均0。新40题留出集仅核对封存哈希，未用于调用、计分或调参。语料、索引、正式90题及标签、Schema、生产Prompt和代码均未修改。','',
      '## 门槛、停止与下一步','', '|预登记门槛|结果|','|---|---|']
    for k,ok in m['pilot_gates'].items():lines.append(f"|{k}|{'PASS' if ok else 'FAIL'}|")
    lines+=['','因T026扩充版恢复门槛失败，本轮未进入90题同期A/B。不能把本次34次观测的比例当作51/72或18/18的新成绩；历史D036版51/72、18/18、90/90只是已有封存基线，不是本轮重新测得。也不能直接将本次引用比例与历史全量62.39%/61.02%比较，样本与权重不同。',
      'B仅作为失败候选归档；运行基线继续保持D036版＋Prompt A，分支本地保留、未合并/推送。下一轮可以固定这两份T026上下文，独立设计显式“要点→证据”映射对照，检查核心段被漏选、重复段被多选和证据充分却拒答；不在当前实验叠加新Schema或新节点。','',
      '## 复算与证据','',
      '先原文支持表后Prompt候选的提交与哈希在manifest/prepared/metadata中；每次原始首答、全部尝试、实际消息、Schema和来源绑定在.runtime/phase2/e6-pilot。calls.csv逐次列出评分、要点掩码、引用支持/不支持ID、首答和trace哈希；fixed_contexts.json含完整归档正文，两个Prompt文本单独交付。','',
      '```powershell',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/e6_selection.py prepare --out <新的准备目录>',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/e6_selection.py pilot --prepared <准备目录>/prepared.json --out <新的运行目录>',
      '.runtime/task17/venv/Scripts/python.exe -B optimization/score_e6_selection.py --run <运行目录> --prepared <准备目录>/prepared.json --out <新的计分目录>',
      '```','',
      '模型服务须为本机封存版本；运行目录必须新建，不覆盖原始记录。核验和计分不调用模型，报告不声称新增人审或盲测。']
    (out/'E6_selection_report.md').write_bytes(('\n'.join(lines)+'\n').encode())
if __name__=='__main__':main()
