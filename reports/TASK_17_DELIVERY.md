# 任务十七交付报告

原计划中任务十六后的编号项只有任务十七。已交付独立 LangGraph 入口、分支和受控重试，以及与普通问答链路的实测对照。 [原任务范围](../docs/DEVELOPMENT_PLAN_AND_REPORT.md) · [流程、命令和对照](../docs/LANGGRAPH_FLOW.md)

| 原交付要求 | 已交付证据 |
| --- | --- |
| 图代码与完整节点 | [LangGraph 实现](../scripts/rag_langgraph.py)、[配置](../config/langgraph_flow.json)、[依赖锁](../config/task17-requirements.lock.txt) |
| 约束重试并记录请求 ID | 两次上限、预算复核、非重试异常停止、UUID 贯穿节点。 [受控分支与重试](task17/controls.json) |
| 正常、资料外与引用失败运行 trace | 普通与图各跑正常、资料外、未核实版本，共 6 次。另实跑一次图内引用故障。正常引用一致，故障返回 failed 且引用为空。 [7 次真实样例](task17/live-comparison.json) |
| 对比复杂度、延迟与可观测性 | 原链三个时间字段，图含 11 个业务节点和 22 条边，支持逐节点计时与失败定位。保留每次请求的读数和运行顺序。 [耗时对照与结论](../docs/LANGGRAPH_FLOW.md) |

7/7 真实案例通过，共完成5次查询 Embedding、200个重排对及5次生成请求。受控实际图测试 15/15，通过了格式重试后成功、预算不足、两次上限、引用异常和请求隔离。两个报告分别保留实际请求与合成故障。原锁定评测和人工记录沿用前序版本。 [真实记录](task17/live-comparison.json) · [受控记录](task17/controls.json)

本机和独立公开副本各通过 18/18 只读复验，证据与生成提交、锁包清单和私有请求哈希关联。保留原入口用于默认问答，图供需要分支和诊断的独立运行。 [本机复验](task17/replay-local.json) · [公开复验](task17/replay-public.json)
