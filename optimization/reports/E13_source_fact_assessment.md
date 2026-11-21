# E13：来源绑定的事实补答实验

2026-11-21（Asia/Shanghai）。运行对照：5986781 + Prompt A + qwen2.5:3b。
实验执行版本：`a475c77cec92a5900c3032092b26cbaf9a8f89d0`；分支 `optimization/e13-source-bound-facts`，仅保留本地。

**结论：** 质量专项通过：六个事实问法由同期对照2/6提升为候选6/6，网页7/7通过。新增补答引用支持7/7，无错误补答。资源门禁未过：可用内存最低0.8866GiB，低于1GiB。停止在90题回归之前，候选默认关闭，不能宣布交付验收通过。

## 实现与使用边界

只在原有模型流程成功解析出普通 `insufficient_evidence` 后尝试补答。程序要求明确匹配对象和全部属性，且原段已在实际 Prompt 内；校验冻结语料、段正文、记录及原文短引哈希，再调用原有原文渲染和引用校验。原始模型响应及尝试记录不改写，补答不发出额外模型请求。
登记范围只有人工草坪颜色、标准成人5号足球球压（千帕）、成人球门内宽和横梁下沿离地高度四项。题号和评测标签不参与匹配。多属性请求须全部核验；不清楚对象、混合未登记属性、赛事/赛季限定、非登记单位或来源缺失时，保留原流程结果。历史改写或回退的请求不启用补答，避免模型补出的对象被程序当作用户已明确的对象。
这是冻结本地资料的事实路径。语料新增或变更会使绑定失效，须复核登记；它不提供任意事实抽取、版本更新或通用冲突识别。原文出处、许可和“非官方赛季规则、未经专家审校”的说明继续展示。

启用仅接受可信进程环境 `FOOTBALL_SOURCE_FACTS=1`；缺省或0保持原行为。实验界面使用隔离会话库，未切换默认部署。

## 无模型回放

29个固定响应和边界用例全部通过；10项实际 Worker 回答/验证器机制检查通过，其中4种伪造或缺失证明被拒绝。新增真实模型调用为0。扫描原90题归档，仅D001、D002、T001符合来源绑定补答条件。这是固定输出的反事实检查，不是新一轮90题成绩。

## 同期 Worker A/B

6个正向问法覆盖3类对象、4项属性，包含原问和独立改写；另有2道原正确对照、5道边界。每个问法A/B各一次，按AB/BA交替。单题一次观测不能证明长期稳定性。

| 请求 | A评分 | B评分 | B最终段 | 程序补答 | 实际Prompt相同 |
|---|---|---|---|---|---|
| grass_original | false_refusal | correct | L01-01 | 是 | 是 |
| grass_paraphrase | correct | correct | L01-01 | 否 | 是 |
| pressure_original | false_refusal | correct | L02-02 | 是 | 是 |
| pressure_paraphrase | false_refusal | correct | L02-02 | 是 | 是 |
| goal_both_original | false_refusal | correct | L01-03 | 是 | 是 |
| goal_both_paraphrase | correct | correct | L01-03 | 否 | 是 |
| players | correct | correct | L03-01 | 否 | 是 |
| half_time | correct | correct | L07-01 | 否 | 是 |
| material | boundary_observation | boundary_observation | — | 否 | 是 |
| ambiguous | boundary_observation | boundary_observation | — | 否 | 是 |
| version | boundary_observation | boundary_observation | — | 否 | 是 |
| extra_attribute | boundary_observation | boundary_observation | — | 否 | 是 |
| D036_gate | boundary_observation | boundary_observation | — | 否 | 是 |

对照A：13次请求，实际回答模型调用11次；补答0次。新增补答引用支持0/0。

候选B：13次请求，实际回答模型调用11次；补答4次。新增补答引用支持4/4。

补答记录保留同一真实模型响应对应的原拒答作为机制对照；它不是第二次独立模型运行。真实A/B仍分别调用原模型，完整输入一致性在上表逐题核对。边界的“未补答”仅验收这条新路径；原模型可能仍给出不完整或不相关答案，不能据此宣称这些边界问题都已解决。

## 正常网页入口

| 请求 | 评分 | 最终段 | 程序补答 | 显示核验 | 秒 |
|---|---|---|---|---|---:|
| grass_original | correct | L01-01 | 是 | True | 32.80 |
| grass_paraphrase | correct | L01-01 | 否 | True | 32.97 |
| pressure_original | correct | L02-02 | 是 | True | 34.53 |
| pressure_paraphrase | correct | L02-02 | 是 | True | 34.56 |
| goal_both_paraphrase | correct | L01-03 | 否 | True | 35.39 |
| players | correct | L03-01 | 否 | True | 32.67 |
| D036_gate | boundary_observation | — | 否 | True | 11.66 |

网页是候选的重复入口观测，另列7次，不增加独立题目数。补答3次，新增引用支持3/3。每次新建会话，经正常页面发送，校验实际UI事件、默认Worker私有轨迹、可见答案值及引用ID。D036另外检查前置门禁零检索、零回答调用。

## 预登记门禁和资源

| 门禁 | 结果 |
|---|---|
| registered_originals_and_paraphrases | True |
| no_incorrect_supplement | True |
| original_correct_controls | True |
| every_added_citation_supported | True |
| technical_complete | True |
| D036_zero_calls | True |
| all_candidate_requests_at_most_60s | True |
| all_candidate_available_at_least_1GiB | False |
| browser_quality | True |
| browser_runtime | False |

| 分组 | 观测数 | 最长请求秒 | 可用内存最低GiB |
|---|---:|---:|---:|
| Worker A | 13 | 38.20 | 0.8954 |
| Worker B | 13 | 39.89 | 0.8867 |
| 网页 B | 7 | 35.39 | 0.8866 |

所有请求顺序执行；时延包括默认Worker启动、检索、模型加载/回答及返回，网页还包括页面收发与显示。Ollama为CPU8线程、8192上下文、单模型驻留及单请求；BGE和3B按现有链路切换加载。内存每0.5秒采样，门槛为请求≤60秒、系统可用内存≥1GiB。小样本报告实际耗时与最大值，不推算并发容量或稳定P95。
资源不达标时不通过减少常驻组件、临时提高门槛或只删除失败观测来宣布成功。当前并发结论继续采用E12，未修改队列和进程初始化。

## 验收决定与留档

固定90题未重跑，因此本轮不能报告18/18拒答、90/90技术完成或高于51/72的最新整体成绩。51/72、18/18、90/90和72/118引用支持仍是历史基线；专项收益不能与历史分数直接相加。40题留出集未用于调用或评分，全部冻结数据哈希保持一致。
保留窄路径和失败资源观测供下一轮使用，默认关闭，不合并、不推送，也不对外承诺已验证范围的交付SLA。下一步先解决正常入口单请求的内存余量和启动开销，再按同一专项门槛复验；全部通过后才进入固定90题验收。

可复核资料：`optimization/experiments/E13_source_facts/plan.json`、`optimization/reports/E13_replay.json`、`E13_mechanism.json`、`E13_special_metrics.json`、`E13_archive_audit.json`，以及本轮 `.runtime/phase2/e13-special01/` 的逐次原始结果、正常Worker轨迹和0.5秒资源采样。
