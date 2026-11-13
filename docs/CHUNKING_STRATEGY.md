# 结构感知切分与父子检索实验

## 1. 范围和结论

本轮按原执行任务11比较原99段、102子块和18父块。原5份文档/Corpus B0/旧结果不变。配置见[structure_parent_child.json](../config/structure_parent_child.json)，完整机器结果见[chunking_comparison.json](../reports/chunking_comparison.json)。开发选择parent_child；测试保留子块负收益与父块预算漏证据，不直接替换现有UI或任务十最佳重排配置。

## 2. Tokenizer和切分

使用BAAI/bge-reranker-base的XLM-R tokenizer资产，revision `2cfc18c9415c912f9d8155881c133215df768a70`，tokenizers0.22.1，tokenizer.json SHA256 `9eb652ac4e40cc093272bbbe0f55d521cf67570060227109b5cdc20945a4489e`；无特殊token、无padding、无截断。此计数不等同于Ollama内部token统计。正文阈值256，只对超长原单元做完整自然段贪心分组，空白保留在精确原字符区间内，无重叠、无改写。

4个原段超长；L01-02/L01-05/L01-07拆为6个子块，其他96个保持全文。L14-04点球表296 tokens作为明确原子例外保留，表头/行/后续条件不拆。若不可分自然段超过阈值，同样保留并标oversize_atomic，不能为满足长度指标截断条件。实际数据最大子块296 tokens，不声称所有块均不超过256。

父块按document_id和前两层section_path分组，保留逐成员三级标题、原顺序、完整正文及每个原来源引用；规则8两个主题保留两个父块，共18组。新ID由原ID/序号/正文哈希或父标题路径哈希确定；稳定映射及区间见[structure_parent_child.json](../data/manifests/structure_parent_child.json)。同输入/代码/Tokenizer可逐字节重建。原ID不改写。

| 层级 | 数量 | 字符均值/中位数/P95 | 正文token均值/中位数/P95 | 最大正文token |
| --- | --- | --- | --- | --- |
| base | 99 | 208.09/203.00/320.90 | 148.76/141.00/226.10 | 342 |
| child | 102 | 201.97/197.00/309.00 | 144.41/140.00/219.90 | 296 |
| parent | 18 | 1242.61/994.00/2396.80 | 879.06/703.00/1781.90 | 2603 |

完整分布包含正文及序列化上下文两套计数、最大/最小值，见[chunking_structure](../reports/chunking_structure.json)。字符数不等于token数；148.76→144.41是小幅长度变化，不能写成180→96或40%冗余收益。

## 3. 检索与上下文装配

两组均使用原BGE-M3固定GGUF摘要、CPU8、1024维、原Embedding选项及固定jieba准确模式title_body/BM25 k1=1.5/b=.75；Dense80+BM2580，RRF k60，取前10个种子，不重排。精确余弦numpy float32用于本轮两组控制，原向量只读复用，原Chroma索引不动；不能把与历史不同后端或重排策略的差异算作切分收益。

原99条向量不重新编码；96个未改变子块复用相同向量，只给6个变化文本子块重新Embedding。索引构建实际2批共6条，参数与哈希见[structure_index_manifest](../data/manifests/structure_index_manifest.json)。父块只作上下文，不建父向量索引。

每题真实Embedding一次，给原段/子块两份独立索引查询；parent_child复用子块种子，按首次命中父ID去重。它是上下文扩展，不是第三路独立检索。最终上下文以4096加性token预算依次装配，计入各序列化块标题和末尾双换行；超预算整块跳过并保留skipped_ids，不截断正文，也不越过种子Top10补召回。预算是此固定tokenizer的索引实验预算，不宣称是答案模型完整prompt窗口。

## 4. 原标签与评分

原标签指向完整原段，没有子片段的相关性标签。主评分要求返回上下文的原字符区间并集覆盖一整个标注段才认定命中，MRR为首次完整覆盖的深度倒数。相邻两子块必须一起覆盖完整原段；只来自同一原ID的一个片段不自动算正确证据。父块则按实际包含的完整成员映射，不把父ID直接伪造成原ID。

主指标用相同4096预算；同时保存不受预算限制的上下文指标及未扩展child控制。TopK是返回上下文块的名次，父块可包含多个原段，因此必须连同上下文tokens解释。原标签保留其小型自建快照/翻译校核限制，无分级标签nDCG=null；不调用答案LLM、不计算拒答准确率。

开发40题（32可回答）和测试50题（40可回答）；不可回答题进入上下文成本统计，不进入质量分母。开发按MRR/Recall降序、平均context tokens升序选方案，选中parent_child；正式源码 `025eb965163566d2ad20087cfdf66fc91ee8c6f6` 在开发证据/46项验证提交后冻结。独立test_usage仅STARTED/COMPLETED一轮，已使用的原锁集不称全新holdout，测试后未修改参数/标签或重跑。

| 方法（4096预算） | Recall@5 | Recall@10 | MRR@10 | 完整支持覆盖@5 | 平均上下文tokens（50题） |
| --- | --- | --- | --- | --- | --- |
| base | 97.500% | 100.000% | 0.936458 | 97.500% | 1954.06 |
| child | 95.000% | 97.500% | 0.923958 | 93.750% | 1915.68 |
| parent_child | 97.500% | 97.500% | 0.945833 | 97.500% | 3648.80 |

无预算父块Recall@5/10均100%、MRR=.952083；它带回更多文字，不能替代上表预算内结果。父块预算后Recall@10从原段100%降为97.5%；MRR较原段高.009375。开发选择保持原样，测试仅报告。

## 5. 重复、冗余与错误

层内重复正文哈希的多余条数/总数定义为精确重复率，base/child/parent均0。父子天然包含关系不计为层内重复错误。上下文冗余率定义为重复原文字符位置/总原文字符位置，按区间合并复算，不把正常标题计作正文重复。三个正式方案去重后均0，相对原段没有冗余下降。

影子诊断保留“每个种子都展开父块而不去重”的重复量：测试平均46.9864%，去重后0；这是与朴素父块展开比较，不是相对Corpus B0降低46.99%。同时父块实际平均上下文3648.80 tokens，原段1954.06、子块1915.68；减少重复不等于总token更少。

- D001：原段/子块缺完整L01-01，父块通过同标题上下文补回，开发例证。
- T002：L01-02被拆后缺少完整原支持段，子块Top10失败；不以仅命中一片段掩盖损失。
- T030：子块命中另一支持段而保持any-hit=1，但L01-05不完整，完整支持覆盖@5/10只有50%，错误表仍列出。
- T003：原段第8名完整命中L01-01，父块无预算可覆盖，4096预算跳过其父块后失败。预算是已冻结策略，不根据本题临时放宽。逐题context_per_question可回链所有跳过项；测试父块共跳过92个上下文块（含不可回答题）。

所有不完整案例保存在dev/test/error_analysis.json；不是答案错误率。99段的字节重组、条件/例外标记计数、标题/规则和点球表机械检查全部通过，见[structure_preservation](../reports/structure_preservation.json)。这些不是专家翻译复核。

## 6. 文件和复现

本机交付 `data/processed/rag_chunks_parent_child.jsonl`（120行=102child+18parent），其SHA和大小在公开映射derived_corpus；全文不上传。独立向量/词项索引在data/indexes/structure_pc_b0，仅公开其manifest。公共总文件清单维护公开文件及原61条本地文件元数据；新JSONL/私有索引由新映射/索引manifest单独核验。

```powershell
# 已有原语料和模型时，在新版本路径构建；已存在输出会拒绝覆盖
.venv/Scripts/python.exe -B scripts/structure_aware_chunking.py
.venv/Scripts/python.exe -B scripts/structure_retrieval_live.py build
# 当前交付只重放，不重复正式test
.venv/Scripts/python.exe -B scripts/run_structure_comparison.py replay --run-dir reports/retrieval/structure_pc_b0/test
.venv/Scripts/python.exe -B scripts/verify_structure_contract.py --dev-dir reports/retrieval/structure_pc_b0/dev --report reports/rechecks/task11-new-contract.json
.venv/Scripts/python.exe -B scripts/verify_structure_delivery.py --complete --report reports/rechecks/task11-new-delivery.json
# 系统Python -S -B + --public-only可无模型/全文/第三方包复算交付门禁
```

保留Git历史用于绑定生产源码。公开重放可证明RRF、区间覆盖、质量/冗余计算与原记录一致，不能从元数据重新计算私有模型向量或真实tokenizer输出；完整本机门禁另外重新构建tokenizer切分并逐字节对照。复验输出用新文件，历史回执不覆盖。

## 7. 交付和去留

原标准要求的代码/独立JSONL/映射/分布/同锁集三组对照/错误/文档齐备，46/46专项、18/18公开初验、完整门禁31/31及最终公开19/19分别归档。开发与测试共96次查询Embedding（含6次非评测预热），另1次实际冒烟；建索引另6条输入/2次请求，合计99次Embedding请求、103条输入；答案LLM为0。公开重放为0新模型请求。

本轮保留原默认RAG和任务十重排结果；parent_child是开发选中实验方案，其测试覆盖/成本权衡如实保留，不据测试重新选参数。后续任务12进行回答、引用、条件与拒答的真实评测；本轮不提前填写答案正确率或生产性能收益。

## 8. 本机完整父块查询入口

`query_parent_child.py` 会实际从独立JSONL读取完整父块并校验正文哈希、逐成员来源、父ID去重和4096预算；正文只写入忽略的.runtime/task11目录。示例：

```powershell
.venv/Scripts/python.exe -B scripts/query_parent_child.py --question "请查找点球罚则的完整表格及条件。" --private-output .runtime/task11/next-context.json --receipt reports/rechecks/task11-next-context.json
```

本轮actual-parent-context.json以已保存的真实非评测查询种子实际读取父正文，5/5检查通过；本次装配0次新Embedding、0答案请求，不能再算一次模型检索或新质量样本。其private_output只公开文件哈希，不公开正文。
