# 任务十三交付报告：整合、复现与打包

日期：2026-11-14。原技术设计、原任务十三工作项和通过条件逐字节保留；任务范围见[冻结说明](../docs/TASK_13_SCOPE.md)。本报告对应分支feat/task-13-integrated-delivery，运行包生产提交`d1c2a630f4ac6f1051743b3b3888f8c27abba7d6`，基线`10897adeee92841c22b1f83992b4ee6c5abdae70`。最终合并与标签由Git历史记录，不在此自引用提交SHA。

**任务十三按原标准验收完成：本机完整39/39、干净公开副本完整33/33，task13_fully_accepted=true。功能、实测、清单与复现材料齐备。**

## 逐项对照原交付标准

| 原要求 | 实际交付与证据 |
| --- | --- |
| 干净或明确记录的本地环境启动 | 新Python3.10.22隔离环境，260项hash锁定依赖+2个固定上游本地包，实际262项；environment-final、requirements-provenance、preflight。模型/上游/缓存复用本机已核验资源，未宣称全新联网机器一次安装成功 |
| 导入既有JSONL并重建索引 | 完整61文件校验、99段导入；真正无data/processed的公开worktree复制61份文件并以Python -S验证。新Dense99×1024和BM25 title_body索引实际创建，原索引不覆盖；clean-corpus-import、index-rebuild |
| 启动可问答、引用可追溯 | 新7866 Kotaemon页面实际接通Dense/BM25→RRF60→BGE Top40→固定Qwen完整证据选择；独立进程、来源/行号/署名/许可和编号校核面板；backend-demo-first、ui-demo |
| 正常、条件/例外、资料外拒答、引用校验 | 下表5类样例，后端5/5与真实浏览器输入/点击5/5；不是人工语义判分或总体准确率 |
| 数据、代码、模型、报告版本对应 | delivery_manifest固定代码/config/docs与10份完成回执，源提交与每文件SHA绑定；全局project_file_manifest补齐最终树，experiment_manifest新增第24项，前23项保持 |
| README、安装/重建/评测说明与配置 | README当前入口、TASK_13_REPRODUCTION完整命令、task13_app/task13_demo配置、独立启动器和标准库门禁；历史dev/test只读重放 |
| 来源、许可与已知限制 | TASK_13_LICENSES及下文；仅发布元数据/代码，规则全文、模型、完整回答/DOM/数据库仍在本机 |
| Docker可按资源决定 | 本轮Windows本机复现已实测，未提供或宣称Docker及跨平台验证；符合原可选范围 |

## 真实端到端演示

| 类别 | 输入要点 | 后端 | 浏览器 | 实际行为 |
| --- | --- | --- | --- | --- |
| 正常回答 | 球门宽、高 | PASS | PASS | 选择L01-03，完整证据包含7.32m/2.44m |
| 条件/例外 | 处于越位位置必然犯规吗 | PASS | PASS | 选择L11-01及补充段，保留本身不必然、参与实际比赛条件 |
| 资料外拒答 | 今晚比分和下一粒进球时间 | PASS | PASS | 资料不足，拒绝给出虚构比分预测 |
| 引用核对 | 普通场上队员能否戴手套 | PASS | PASS | 选择L04-05，显示原段、来源URL/行号、署名/许可 |
| 版本边界 | 2026/27官方有效性 | PASS | PASS | 未验证赛季，确定性拒答，无检索/生成推理 |

浏览器证据是实际页面输入/点击后的DOM、工作进程原始请求/响应与UI日志逐条回链；没有用后端结果替代页面操作。页面完整文字与原始响应只保留.runtime/task13，公开回执只提供SHA和脱敏来源元数据。对话历史不作为事实资料。页面地址[127.0.0.1:7866](http://127.0.0.1:7866/)，启动命令见[复现文档](../docs/TASK_13_REPRODUCTION.md)。

## 环境、索引、证据与版本

- 固定Kotaemon上游9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9，不修改上游源码。新环境.runtime/task13/venv-final，新数据库.runtime/task13/kotaemon；原.venv不改。
- 语料为既有Corpus B0，99段，SHA `05dcd08126b5c71031ebe025f1a4ed1b73e00f71007b60ac0a3e0814f386a0b3`；原五份中文资料、61文件清单保持，不重抓/重译/二次切分。
- 新索引data/indexes/task13/dense-v1和data/indexes/bm25/task13-title-body-v1；实际索引清单SHA见index-rebuild与delivery_manifest。前序旧索引保持。
- Qwen2.5:3b digest357c53fb…c9e4b；BGE-M3 digest79076464…6bab；reranker revision2cfc18c…68a70，ONNX文件hash固定。上下文6200 UTF8字节、最多5完整证据、选择最多3条、最多2次结构化尝试。请求计数来自实际响应，不由估计token数代替。
- 采用任务10开发集选定Top40及任务12固定摘录策略。任务11父子块是另一个对照实验且有预算/召回负收益，未悄悄替换本集成方案；原实验与完整入口保留。
- 运行包manifest为固定源代码/config/docs和完成回执的清单，排除最后交付文字/完整门禁/递归全局索引；最终公开文件由全局manifest覆盖。生产提交与最终合并提交职责不同。

## 测试、失败和缺陷处理

| 验证 | 已实际结果 | 范围 |
| --- | --- | --- |
| 后端实际模型样例 | 5/5 | 正常/条件/资料外/引用/版本 |
| 实际浏览器样例 | 5/5 | DOM答案与原始响应一致，来源/许可链接可核对 |
| 私有合同与篡改防护 | 45/45 | 输入/路径/config/来源/提示词/实际生成/计数/时钟/HTML转义 |
| 无语料/模型公开副本 | 28/28 + 21/21 | Python -S公开对抗复算、原公开输入/config合同，两个测试套件分列不相加冒充质量样本 |
| 任务12原完整验收 | 26/26 | 在本轮登记第24项前实际执行；旧门禁的23项登记数是其历史范围，新阶段使用verify_task13_delivery |

首次新环境的依赖安装成功，但editable源码包构建因系统TEMP访问失败；失败目录和environment.json保留。安装器改为项目内TEMP/TMP后，用另一个全新目录完成安装；environment-final记录真实成功。工具保存浏览器快照时的目录权限不兼容改为读取DOM后写入项目私有目录，未改变产品回答。

本轮真实新增33次Embedding请求、107个输入（重建25批99输入，8个查询输入），8次答案模型尝试、320个重排pair；resource-accounting由实际批次/私有回执统计。0次正式测试重跑，0条新增人工判断。预检查、只读复算与门禁不调用推理。时间见各样例timing与worker_wall_seconds，包含加载的完整工作进程开销另列，不伪造120ms、吞吐或生产SLA。

## 质量、许可与使用限制

现有资料为Wikipedia固定快照的AI中文整理，不是IFAB官方赛季规则；历史修订正文未独立取回核验，也没有裁判专家审校。页面区分本地编目号与官方条号，未验证的official_law_number为null。来源/署名/CC BY-SA许可随证据展示，公开仓库没有规则全文或模型权重。

原任务12人工样本引用9/20、要点21/27、条件21/27完整保留，AI正式50题引用22/71、要点40/100等低分也保留。本轮5类功能样例不证明全量答案改善；仍有冗长摘录、无关段、错误拒答及规则核验不足。没有新的专家准确率、QPS/并发、语义缓存/HNSW调优收益。Qwen2.5-3B-Instruct采用Qwen Research许可，不能笼统写成全部模型Apache2；详见[许可清单](../docs/TASK_13_LICENSES.md)。

## Git、工作流和回滚

只在yangyanbeen/football-rules-rag-lab的新分支按小提交开发，再PR合并与新标签v0.13.0-integrated-delivery。旧23标签、23实验对象及原项目/其他仓库保留；旧报告和原正式测试账本不覆盖。任务14日志、汇总CSV、简历证据随本阶段追加，未伪造完成后续独立工作。

回滚使用独立checkout检出旧tag，不删除正式账本或覆盖已有索引；新环境/索引/DB目录互相隔离。最终远端PR/合并/tag与原仓库保全结果由发布核对记录证明。

## 最终验收记录

本机完整门禁实际39/39通过（task13/delivery-first.json），真正无.runtime/.models/data/processed/data/indexes的Git worktree以Python -S完整33/33通过（task13/delivery-clean-public.json），均task13_fully_accepted=true。最终本机门禁另写task13/delivery-final.json，不覆盖前次记录。GitHub通过同名功能分支PR合并、新标签v0.13.0-integrated-delivery发布；实际提交/合并SHA与PR可在仓库Git历史核对，发布后再只读比较远端文件、旧标签与其他原有仓库。历史中间失败/通过记录保持原字节。
