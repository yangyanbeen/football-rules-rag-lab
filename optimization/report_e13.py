"""Verify archived normal-entry observations and report the registered E13 gates."""
import argparse,json,socket,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest,canonical
from task13_audit import validate_private

def save(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def audit(run):
    run=run.resolve()
    metrics=read(ROOT/'optimization/reports/E13_special_metrics.json')
    done=read(run/'worker/completed.json');rows=[]
    for name,sha in done['hashes'].items():
        path=run/'worker'/name;assert digest(path.read_bytes())==sha
        row=read(path)
        if row.get('result'):
            r=row['result'];validate_private(r,r['question'],True)
            assert record(ROOT/row['private_trace']['path'])==row['private_trace']
            if 'shared_response_control' in row:
                a=row['shared_response_control'];validate_private(a,a['question'],True)
                assert a['attempts']==r['attempts'] and a['messages']==r['messages']
        rows.append(row)
    browser=read(run/'browser/result.json') if (run/'browser/result.json').exists() else dict(hashes={},observations=0)
    brows=[]
    for name,sha in browser['hashes'].items():
        path=run/'browser'/name;assert digest(path.read_bytes())==sha
        row=read(path)
        if 'trace' in row:
            r=row['trace'];validate_private(r,r['question'],True)
            assert record(ROOT/row['event']['private_trace']['path'])==row['event']['private_trace']
        brows.append(row)
    metadata=read(run/'worker/metadata.json')
    assert all(record(ROOT/p)==r for p,r in metadata['source_files'].items())
    freeze=read(ROOT/'optimization/datasets/freeze_manifest.json')
    for item in freeze['files']:
        path=ROOT/'optimization'/item['path'];assert digest(path.read_bytes())==item['sha256'] and path.stat().st_size==item['bytes']
    by={(r['name'],r['variant']):r for r in rows};pairs=[]
    for name in dict.fromkeys(r['name'] for r in rows):
        if (name,'A') not in by or (name,'B') not in by:continue
        a=by[name,'A'];b=by[name,'B'];ar=a.get('result');br=b.get('result')
        pairs.append(dict(name=name,question=a['question'],A_grade=(a.get('score') or {}).get('grade'),B_grade=(b.get('score') or {}).get('grade'),
            A_ids=ar['selected_ids'] if ar else None,B_ids=br['selected_ids'] if br else None,
            identical_question_and_actual_context=bool(ar and br and ar['question']==br['question'] and ar['messages']==br['messages'] and ar['context']==br['context']),
            A_seconds=a['seconds'],B_seconds=b['seconds'],A_attempts=len(ar['attempts']) if ar else None,B_attempts=len(br['attempts']) if br else None,
            A_raw_selection=a.get('raw_model_selection'),B_raw_selection=b.get('raw_model_selection'),
            recovery=br.get('fact_recovery') if br else None))
    def summary(values,trace_key):
        supplement=[r for r in values if r.get(trace_key) and r[trace_key].get('fact_recovery',{}).get('applied')]
        return dict(observations=len(values),supplements=len(supplement),supplement_names=[r['name'] for r in supplement],
            added_citation_numerator=sum(r['score']['citation_numerator'] for r in supplement),
            added_citation_denominator=sum(r['score']['citation_denominator'] for r in supplement),
            real_answer_model_calls=sum(len(r.get(trace_key,{}).get('attempts',[])) for r in values),
            max_seconds=max([r['seconds'] for r in values] or [0]),
            min_available_GiB=min([r['resources']['available_min_GiB'] for r in values if r['resources']['available_min_GiB'] is not None] or [0]))
    ports={}
    for port in (11434,7867):
        with socket.socket() as client:
            client.settimeout(2);ports[str(port)]=client.connect_ex(('127.0.0.1',port))!=0
    assert all(ports.values()),'Close experiment services before archiving'
    plan=read(ROOT/'optimization/experiments/E13_source_facts/plan.json')
    positive_names={c['name'] for c in plan['pressure_questions'] if not c.get('replay_only')}
    detail=dict(producer_commit=metadata['source_commit'],worker_A=summary([r for r in rows if r['variant']=='A'],'result'),
        worker_B=summary([r for r in rows if r['variant']=='B'],'result'),browser_B=summary(brows,'trace'),pairs=pairs,
        positive_wordings=len(positive_names),positive_correct={v:sum(r['score']['grade']=='correct' for r in rows if r['variant']==v and r['name'] in positive_names) for v in 'AB'},
        datasets_and_holdout_hashes_unchanged=True,holdout_used=False,full90_executed=False,
        source_hashes_unchanged=True,raw_worker_files=done['hashes'],raw_browser_files=browser['hashes'],
        replay=record(ROOT/'optimization/reports/E13_replay.json'),mechanism=record(ROOT/'optimization/reports/E13_mechanism.json'),
        decision='FULL90_ELIGIBLE_NOT_EXECUTED' if metrics['all_gates_passed'] else 'STOP_BEFORE_FULL90',
        test_ports_closed=ports,services_closed=True,
        raw_run_records={p.relative_to(ROOT).as_posix():record(p) for group in ('worker','browser','services') for p in (run/group).iterdir() if p.is_file()},
        default_feature_enabled=False,local_branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip())
    save(ROOT/'optimization/reports/E13_archive_audit.json',detail)
    return metrics,detail,brows

def report(metrics,d,brows):
    s=['# E13：来源绑定的事实补答实验','',
       '2026-11-21（Asia/Shanghai）。运行对照：5986781 + Prompt A + qwen2.5:3b。',
       f"实验执行版本：`{d['producer_commit']}`；分支 `{d['local_branch']}`，仅保留本地。",'',
       '**结论：** '+('专项全部过关，可以进入已登记的90题验收。' if metrics['all_gates_passed'] else
       f"质量专项通过：六个事实问法由同期对照{d['positive_correct']['A']}/6提升为候选{d['positive_correct']['B']}/6，网页7/7通过。新增补答引用支持7/7，无错误补答。资源门禁未过：可用内存最低{min(d['worker_B']['min_available_GiB'],d['browser_B']['min_available_GiB']):.4f}GiB，低于1GiB。停止在90题回归之前，候选默认关闭，不能宣布交付验收通过。"),'',
       '## 实现与使用边界','',
       '只在原有模型流程成功解析出普通 `insufficient_evidence` 后尝试补答。程序要求明确匹配对象和全部属性，且原段已在实际 Prompt 内；校验冻结语料、段正文、记录及原文短引哈希，再调用原有原文渲染和引用校验。原始模型响应及尝试记录不改写，补答不发出额外模型请求。',
       '登记范围只有人工草坪颜色、标准成人5号足球球压（千帕）、成人球门内宽和横梁下沿离地高度四项。题号和评测标签不参与匹配。多属性请求须全部核验；不清楚对象、混合未登记属性、赛事/赛季限定、非登记单位或来源缺失时，保留原流程结果。历史改写或回退的请求不启用补答，避免模型补出的对象被程序当作用户已明确的对象。',
       '这是冻结本地资料的事实路径。语料新增或变更会使绑定失效，须复核登记；它不提供任意事实抽取、版本更新或通用冲突识别。原文出处、许可和“非官方赛季规则、未经专家审校”的说明继续展示。','',
       '启用仅接受可信进程环境 `FOOTBALL_SOURCE_FACTS=1`；缺省或0保持原行为。实验界面使用隔离会话库，未切换默认部署。','',
       '## 无模型回放','',
       '29个固定响应和边界用例全部通过；10项实际 Worker 回答/验证器机制检查通过，其中4种伪造或缺失证明被拒绝。新增真实模型调用为0。扫描原90题归档，仅D001、D002、T001符合来源绑定补答条件。这是固定输出的反事实检查，不是新一轮90题成绩。','',
       '## 同期 Worker A/B','',
       '6个正向问法覆盖3类对象、4项属性，包含原问和独立改写；另有2道原正确对照、5道边界。每个问法A/B各一次，按AB/BA交替。单题一次观测不能证明长期稳定性。','',
       '| 请求 | A评分 | B评分 | B最终段 | 程序补答 | 实际Prompt相同 |',
       '|---|---|---|---|---|---|']
    for p in d['pairs']:
        s.append(f"| {p['name']} | {p['A_grade']} | {p['B_grade']} | {','.join(p['B_ids'] or []) or '—'} | {'是' if (p['recovery'] or {}).get('applied') else '否'} | {'是' if p['identical_question_and_actual_context'] else '否'} |")
    for label,key in [('对照A','worker_A'),('候选B','worker_B')]:
        v=d[key];s+=['',f"{label}：{v['observations']}次请求，实际回答模型调用{v['real_answer_model_calls']}次；补答{v['supplements']}次。新增补答引用支持{v['added_citation_numerator']}/{v['added_citation_denominator']}。"]
    s+=['','补答记录保留同一真实模型响应对应的原拒答作为机制对照；它不是第二次独立模型运行。真实A/B仍分别调用原模型，完整输入一致性在上表逐题核对。边界的“未补答”仅验收这条新路径；原模型可能仍给出不完整或不相关答案，不能据此宣称这些边界问题都已解决。','',
        '## 正常网页入口','',
        '| 请求 | 评分 | 最终段 | 程序补答 | 显示核验 | 秒 |',
        '|---|---|---|---|---|---:|']
    for row in brows:
        t=row.get('trace') or {};s.append(f"| {row['name']} | {(row.get('score') or {}).get('grade','未完成')} | {','.join(t.get('selected_ids',[])) or '—'} | {'是' if t.get('fact_recovery',{}).get('applied') else '否'} | {row.get('visible_answer_verified',False)} | {row['seconds']:.2f} |")
    v=d['browser_B'];s+=['',f"网页是候选的重复入口观测，另列{v['observations']}次，不增加独立题目数。补答{v['supplements']}次，新增引用支持{v['added_citation_numerator']}/{v['added_citation_denominator']}。每次新建会话，经正常页面发送，校验实际UI事件、默认Worker私有轨迹、可见答案值及引用ID。D036另外检查前置门禁零检索、零回答调用。",'',
        '## 预登记门禁和资源','',
        '| 门禁 | 结果 |','|---|---|']
    for k,v in metrics['quality_gates'].items():s.append(f"| {k} | {v} |")
    for k,v in metrics['runtime_gates'].items():s.append(f"| {k} | {v} |")
    b=metrics.get('browser') or {};s += [f"| browser_quality | {b.get('quality_passed',False)} |",f"| browser_runtime | {b.get('runtime_passed',False)} |",'',
        '| 分组 | 观测数 | 最长请求秒 | 可用内存最低GiB |','|---|---:|---:|---:|']
    for label,key in [('Worker A','worker_A'),('Worker B','worker_B'),('网页 B','browser_B')]:
        v=d[key];s.append(f"| {label} | {v['observations']} | {v['max_seconds']:.2f} | {v['min_available_GiB']:.4f} |")
    s+=['','所有请求顺序执行；时延包括默认Worker启动、检索、模型加载/回答及返回，网页还包括页面收发与显示。Ollama为CPU8线程、8192上下文、单模型驻留及单请求；BGE和3B按现有链路切换加载。内存每0.5秒采样，门槛为请求≤60秒、系统可用内存≥1GiB。小样本报告实际耗时与最大值，不推算并发容量或稳定P95。',
        '资源不达标时不通过减少常驻组件、临时提高门槛或只删除失败观测来宣布成功。当前并发结论继续采用E12，未修改队列和进程初始化。','',
        '## 验收决定与留档','',
        '固定90题未重跑，因此本轮不能报告18/18拒答、90/90技术完成或高于51/72的最新整体成绩。51/72、18/18、90/90和72/118引用支持仍是历史基线；专项收益不能与历史分数直接相加。40题留出集未用于调用或评分，全部冻结数据哈希保持一致。',
        '保留窄路径和失败资源观测供下一轮使用，默认关闭，不合并、不推送，也不对外承诺已验证范围的交付SLA。下一步先解决正常入口单请求的内存余量和启动开销，再按同一专项门槛复验；全部通过后才进入固定90题验收。','',
        '可复核资料：`optimization/experiments/E13_source_facts/plan.json`、`optimization/reports/E13_replay.json`、`E13_mechanism.json`、`E13_special_metrics.json`、`E13_archive_audit.json`，以及本轮 `.runtime/phase2/e13-special01/` 的逐次原始结果、正常Worker轨迹和0.5秒资源采样。']
    return '\n'.join(s)+'\n'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--copy',type=Path);a=p.parse_args()
    m,d,b=audit(a.run);text=report(m,d,b);(ROOT/'optimization/reports/E13_source_fact_assessment.md').write_bytes(text.encode())
    if a.copy:a.copy.write_bytes(text.encode())
    print(json.dumps({k:d[k] for k in ('producer_commit','worker_A','worker_B','browser_B','decision','holdout_used')},ensure_ascii=False))
