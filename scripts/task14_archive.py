"""Deterministic final evidence archive; no model calls, training or benchmark reruns."""
from __future__ import annotations
import argparse,csv,io,json,math,re,subprocess
from functools import lru_cache
from pathlib import Path
from answer_eval_core import ROOT,read,record,digest,canonical,write_new

BASE='5658f30ecaa714e2bdaca3085cc547414f478e36'
SPEC='config/task14_archive.json'
SOURCES=('scripts/task14_archive.py',SPEC)
FOLDER=ROOT/'reports/task14'
FIELDS=('id','tasks','kind','goal','control','main_variable','data_version','test_version','code','model','parameters','hardware','commands','raw_results','metrics','conclusion','limitations','source')


def git(*args,raw=False):
    out=subprocess.check_output(['git',*args],cwd=ROOT)
    return out if raw else out.decode('utf-8').strip()


@lru_cache(maxsize=None)
def baseline(path):return git('show',BASE+':'+path,raw=True)
@lru_cache(maxsize=1)
def baseline_names():return set(git('ls-tree','-r','--name-only',BASE).splitlines())
def base_ref(path):
    b=baseline(path);return {'path':path,'size_bytes':len(b),'sha256':digest(b),'git_commit':BASE}


def pointer(value,path):
    if not isinstance(path,str) or path and not path.startswith('/'):raise ValueError('Invalid JSON pointer')
    if not path:return value
    for key in path[1:].split('/'):
        key=key.replace('~1','/').replace('~0','~')
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value


def resource(path):
    p=(ROOT/path).resolve()
    if not isinstance(path,str) or not p.is_relative_to(ROOT) or '..' in Path(path).parts or path not in baseline_names():raise ValueError('Only baseline public evidence is permitted')
    if p.read_bytes()!=baseline(path):raise ValueError('Frozen evidence changed: '+path)
    if p.suffix=='.jsonl':return [json.loads(s) for s in p.read_text('utf-8').splitlines() if s.strip()]
    if p.suffix=='.json':return read(p)
    raise ValueError('Evidence must be public JSON/JSONL')


def spec():
    v=read(ROOT/SPEC)
    if set(v)!={'version','baseline_commit','groups','claims','unmeasured','policy'} or v['version']!='task14-spec-1.0' or v['baseline_commit']!=BASE:raise ValueError('Unknown archive specification')
    if len({c['id'] for c in v['claims']})!=len(v['claims']):raise ValueError('Duplicate claim ID')
    return v


def value_of(c,values):
    v=pointer(values[c['source']],c['pointer'])
    if c['op']=='length':v=len(v)
    elif c['op']!='value':raise ValueError('Unknown claim operation')
    if type(v) not in (int,float) or not math.isfinite(v) or v<0:raise ValueError('Claim is not a measured numeric value')
    if c['unit']=='ratio' and v>1:raise ValueError('Invalid ratio')
    return v


def normalize(e,row,index):
    tasks=[int(x) for x in re.findall(r'\d+',row['task'])]
    if re.fullmatch(r'\d+-\d+',row['task']):tasks=list(range(tasks[0],tasks[-1]+1))
    def take(keys,fallback):return next((e[k] for k in keys if e.get(k) is not None),fallback)
    result={
        'id':e['id'],'tasks':tasks,'kind':'historical_experiment_or_engineering_record',
        'goal':take(('objective','goal'),row['goal']),
        'control':take(('control','baseline','baseline_commit'),row['control']),
        'main_variable':{'historical_value':take(('main_variable','scope'),row['main_change']),'interpretation':'工程修复包含多个检查点时不视为单因素质量收益；正式对照以原运行配置为准'},
        'data_version':take(('dataset_version','data_version','dataset'),row['data_version']),
        'test_version':take(('evaluation_version','test_version','evaluation'),row['test_version']),
        'code':{'registry_fields':{k:e[k] for k in ('code_commit','code_base_commit','implementation_commit','formal_test_source_commit','delivery_source_commit','source_commit','source_sha256','implementation_sha256','code','code_version_method') if k in e},'summary_evidence':row['code_evidence'],'pre_git_policy':'早期无Git保留原SHA，不补造历史提交'},
        'model':take(('model','models','model_config'),row['model'] or '不适用/原阶段未独立推理'),
        'parameters':take(('parameters',),{'status':'待测','reason':'原登记未独立列出参数；保留原记录并链接对应原始配置，不以新配置补填历史'}),
        'hardware':take(('hardware','environment'),{'status':'待测','reason':'原登记未单独记录硬件；本条不提出硬件性能结论'}),
        'commands':{'historical_record':e.get('commands',row['command']),'read_only_archive_lookup':['python -S -B scripts/task14_archive.py show --experiment '+e['id']],'interpretation':'历史简写保留，不冒充本轮重新执行；正式测量命令/源码/参数由原manifest和下述组别回链'},
        'raw_results':{'legacy_summary_value':row['raw_results'],'registered_artifacts':e.get('artifacts',[]),'history_policy':'旧制品hash属于其当时版本，不要求可变历史报告与当前字节相同；本轮数字只引用当前冻结逐题文件'},
        'metrics':{'historical_summary':row['observed_result'],'registry_result_fields':{k:e[k] for k in ('result','results','metrics','test_metrics','quality','checks') if k in e},'unmeasured_rule':'未实际测量的指标为待测，不将工程检查数当答案质量'},
        'conclusion':take(('decision','delivery_scope'),row['decision']),
        'limitations':e.get('limitations','遵守原记录中的语料/测量范围；仅归档，不主张新质量改善'),
        'source':{'registry':base_ref('data/manifests/experiment_manifest.json'),'pointer':'/experiments/'+str(index),'object_sha256':digest(canonical(e)),'legacy_csv':base_ref('reports/all_experiments_summary.csv')}
    }
    return result


def build(source):
    s=spec()
    if not re.fullmatch('[a-f0-9]{40}',source) or subprocess.run(['git','merge-base','--is-ancestor',source,'HEAD'],cwd=ROOT,capture_output=True).returncode:raise ValueError('Invalid archive producer')
    for p in SOURCES:
        if git('show',source+':'+p,raw=True)!=(ROOT/p).read_bytes():raise ValueError('Commit archive generator/specification first')
    registry=json.loads(baseline('data/manifests/experiment_manifest.json'))
    csvrows=list(csv.DictReader(io.StringIO(baseline('reports/all_experiments_summary.csv').decode('utf-8-sig'))))
    if len(registry['experiments'])!=25 or [e['id'] for e in registry['experiments']]!=[r['experiment_id'] for r in csvrows]:raise ValueError('Historical registry and CSV disagree')
    records=[normalize(e,r,i) for i,(e,r) in enumerate(zip(registry['experiments'],csvrows))]
    for task in (1,2):
        records.insert(task-1,{'id':'LEGACY-TASK-00'+str(task),'tasks':[task],'kind':'pre_git_stage','goal':'语料审计冻结' if task==1 else '固定上游并验证本机应用运行','control':'既有原工程；当时无Git','main_variable':'审计记录' if task==1 else '固定上游/运行环境与界面冒烟','data_version':'原5份中文文档/99知识段；任务2临时应用50段不替代Corpus B0','test_version':'不适用；尚未建立正式检索评测集','code':{'policy':'原文件SHA，无虚构早期Git提交','baseline':base_ref('data/manifests/task1_task2_baseline_lock.json')},'model':'任务1无推理；任务2固定模型见原UPSTREAM_VERSION/KOTAEMON_BASELINE','parameters':{'status':'待测','reason':'以原本机设置文档为依据，不追补虚构历史值'},'hardware':{'status':'待测','reason':'无独立硬件性能测量'},'commands':['python -S -B scripts/task14_archive.py show --experiment LEGACY-TASK-00'+str(task)],'raw_results':[base_ref('docs/PROJECT_AUDIT.md'),base_ref('docs/KOTAEMON_BASELINE.md'),base_ref('reports/TASK_01_02_DELIVERY.md')],'metrics':{'retrieval_quality':'待测','answer_quality':'待测'},'conclusion':'按当时运行基线交付；原回答与引用错误保留','limitations':'非官方规则/非专家审校；冒烟通过不代表正确率','source':{'registry':'早于Git和正式实验登记，按原报告/SHA归档'}})
    groups={};values={}
    for name,g in s['groups'].items():
        for p in g['sources']+g['parameters']:
            if p not in values:values[p]=resource(p)
        manifest=values.get(g['manifest'],{})
        environment=manifest.get('environment',{})
        if name=='answers':environment=values['reports/answer_evaluation/test/environment.json']['retriever']
        groups[name]={**g,'source_records':[record(ROOT/p) for p in g['sources']],
            'parameter_values':{p:values[p] for p in g['parameters']},'parameter_records':[record(ROOT/p) for p in g['parameters']],
            'producer':{'commit':manifest.get('source_commit'),'source_manifest':g['manifest'],'fallback':'无单独提交字段时按原登记/文件hash，不猜测'},
            'hardware':{'value':{k:environment[k] for k in ('python','platform','system','processor','machine','logical_cpus','logical_cpu_count','physical_memory_bytes','packages') if k in environment},'status':'documented' if environment else '待测','scope':'原阶段记录；离线融合只有原通道与融合分别计时，不补造端到端硬件成绩'}}
        if not g['parameters']:groups[name]['parameter_values']={'status':'不适用；数据/标签/抽样记录，无新模型推理'}
        for r in records:
            if r['id']==g['experiment']:
                r.setdefault('evidence_groups',[]).append(name)
                r['parameters']={'historical_record':r['parameters'],'verified_group':name,'config_records':groups[name]['parameter_records']}
                r['hardware']={'historical_record':r['hardware'],'verified_group':name,'hardware':groups[name]['hardware']}
    claims=[]
    for c in s['claims']:
        g=groups[c['group']]
        if c['source'] not in g['sources']+g['parameters']:raise ValueError('Claim source is not in its evidence group')
        claims.append({**c,'status':'measured','value':value_of(c,values),'source_record':record(ROOT/c['source']),
            'lineage':{'experiment':g['experiment'],'raw_results':g['source_records'],'parameters':g['parameter_records'],'hardware_group':c['group'],'producer':g['producer'],'commands':g['commands'],'historical_commands':next(r['commands']['historical_record'] for r in records if r['id']==g['experiment']),'scope':g['scope']}})
    records.append({'id':'TASK-014-FINAL-ARCHIVE','tasks':[14],'kind':'archive_only','goal':'将历史实验与简历数字闭环归档','control':BASE,'main_variable':'规范化档案/证据索引，不改变检索或回答策略','data_version':record(ROOT/'data/manifests/local_data_files.json'),'test_version':'无新增正式test，仅只读复算','code':{'source_commit':source,'sources':[record(ROOT/p) for p in SOURCES]},'model':'不适用：0新Embedding/答案请求','parameters':{'specification':record(ROOT/SPEC),'archive_version':'task14-evidence-1.0'},'hardware':{'status':'不适用','reason':'不报告硬件性能指标'},'commands':['python -S -B scripts/task14_archive.py build','python -S -B scripts/replay_task14.py --report <new.json>'],'raw_results':'reports/task14/archive.json及其逐条来源','metrics':{'new_model_requests':0,'new_formal_test_runs':0,'new_human_judgments':0},'conclusion':'真实记录、负收益和待测均保留；完整交付状态由独立门禁判定','limitations':'不新增或外推质量提升，早期缺失元数据如实标明','source':{'baseline_commit':BASE,'source_commit':source}})
    return {'version':'task14-evidence-1.0','baseline_commit':BASE,'source_commit':source,'generator_sources':[record(ROOT/p) for p in SOURCES],
        'historical_registry_count':25,'records':records,'groups':groups,'claims':claims,
        'unmeasured':[{'name':n,'status':'待测','value':None,'resume_allowed':False} for n in s['unmeasured']],
        'policy':s['policy'],'new_model_requests':0,'new_formal_test_runs':0,'new_human_judgments':0}


def csv_text(v):
    out=io.StringIO(newline='');w=csv.DictWriter(out,fieldnames=FIELDS,lineterminator='\n');w.writeheader()
    for r in v['records']:w.writerow({k:json.dumps(r[k],ensure_ascii=False,sort_keys=True,separators=(',',':')) if not isinstance(r[k],str) else r[k] for k in FIELDS})
    return out.getvalue()


def claim_map(v):return {c['id']:c for c in v['claims']}
def display(c):
    if c['id'].endswith('_mrr'):return format(c['value'],'.6f')
    if c['unit']=='ratio':return format(c['value']*100,'.3f').rstrip('0').rstrip('.')+'%'
    return format(c['value'],'.6f').rstrip('0').rstrip('.') if isinstance(c['value'],float) else str(c['value'])


def resume_text(v):
    c=claim_map(v);n=lambda k:display(c[k])
    lines=['# 足球规则RAG项目：当前可使用的简历版本','',
        '基于开源Kotaemon二次开发。数据是Wikipedia固定快照的AI中文整理，非官方赛季规则、非裁判专家审校；以下是小规模固定领域集的工程与实测事实。','',
        '- 将'+n('documents')+'份中文资料、'+n('chunks')+'个稳定知识段接入可追溯问答系统，实现Dense/BM25混合检索、RRF融合、候选截断重排、结构化证据选择及来源/许可校验。[documents, chunks]',
        '- 构建'+n('dev_questions')+'题开发集、'+n('test_questions')+'题锁定测试和'+n('hard_negatives')+'对难负例；同轮候选深度固定的重排对照中，Top40方案测试Recall@5为'+n('reranker_top40_r5')+'、MRR@10为'+format(c['reranker_top40_mrr']['value'],'.3f')+'，开发先选方案，测试仅报告。[dev_questions, test_questions, hard_negatives, reranker_top40_r5, reranker_top40_mrr]',
        '- 实现结构感知切分与父子块来源区间映射，从原知识段派生'+n('children')+'子块/'+n('parents')+'父块，在'+n('context_budget')+' token预算下比较完整证据覆盖与上下文成本，保留子块召回下降和父块成本增加的结果。[children, parents, context_budget]',
        '- 建立检索逐题评测、回答/引用/条件/拒答评测及'+n('human_samples')+'题真实人工抽样，支持无模型结果复算、故障回执、Git/PR小步版本与文件hash追溯。[human_samples]','',
        '## 面试时必须说明的边界','',
        '- 当前集成采用重排链路；父子块为独立对照实验，并非已全面替换线上链路。',
        '- 同轮无重排控制Recall@5='+n('reranker_no_rerank_r5')+'、MRR@10='+format(c['reranker_no_rerank_mrr']['value'],'.6f')+'。Top40重排本机CPU P50为'+n('reranker_top40_rerank_seconds_P50_ms')+'ms，完整检索链P50为'+n('reranker_top40_total_seconds_P50_ms')+'ms；不可写成120ms或整体提速。[reranker_no_rerank_r5, reranker_no_rerank_mrr, reranker_top40_rerank_seconds_P50_ms, reranker_top40_total_seconds_P50_ms]',
        '- 锁定测试已经用于前序阶段报告，不称完全未见holdout；Recall为命中任一标注支持段，不保证全部证据齐全或答案正确。',
        '- 人审受AI建议辅助且优先抽取错误样本，不是盲审或裁判专家认证。原人工引用'+n('human_citation_correctness_numerator')+'/'+n('human_citation_correctness_denominator')+'，原AI引用正确率'+n('ai_citation_correctness')+'，保留质量缺口，不写总体准确率提升。[human_citation_correctness_numerator, human_citation_correctness_denominator, ai_citation_correctness]',
        '- FAISS调优、语义缓存、LangGraph、QPS和未运行的示例收益均待测。','',
        '## 每个数字怎样追溯','',
        '方括号内是archive.json中的claim ID。使用 `python -S -B scripts/task14_archive.py show --claim <ID>` 查看数值、原文件SHA/JSON pointer、逐题文件、参数、硬件及执行命令；experiments.csv为完整字段汇总，RESULTS_FINAL.md保留全部正负收益。','']
    return '\n'.join(lines)


def results_text(v):
    c=claim_map(v);n=lambda k:display(c[k]);lines=['# 最终结果与取舍','',
        '只归档原实测并只读复算，没有新测试检索/生成。数据、参数、硬件和命令以archive.json各group及其原manifest为准。','',
        '## 历史Top10单路/融合（同一固定集）','',
        '| 方法 | Recall@5 | Recall@10 | MRR@10 |','| --- | --- | --- | --- |']
    for label,key in [('Dense','dense'),('BM25','bm25'),('RRF','hybrid_rrf')]:lines.append('| '+label+' | '+' | '.join(n(key+'_'+m) for m in ('r5','r10','mrr'))+' |')
    lines+=['','RRF相对BM25的MRR下降保留；这里各通道为Top10，不与下一组Top80候选混算提升。','','## 同轮候选深度80的重排控制','','| 方法 | Recall@5 | Recall@10 | MRR@10 |','| --- | --- | --- | --- |']
    for method in ('no_rerank','top20','top40','top80'):lines.append('| '+method+' | '+' | '.join(n('reranker_'+method+'_'+m) for m in ('r5','r10','mrr'))+' |')
    lines+=['','Top40由开发集选择；比无重排控制质量改善，但CPU重排增加成本。完整50题、每题每方法一次，冷启动/预热除外。','','| 候选 | 重排P50/P95 ms | 完整链P50/P95 ms |','| --- | --- | --- |']
    for m in ('top20','top40','top80'):lines.append('| '+m+' | '+n('reranker_'+m+'_rerank_seconds_P50_ms')+' / '+n('reranker_'+m+'_rerank_seconds_P95_ms')+' | '+n('reranker_'+m+'_total_seconds_P50_ms')+' / '+n('reranker_'+m+'_total_seconds_P95_ms')+' |')
    lines+=['','## 结构/父子块（统一精确余弦，无重排）','','| 方法 | Recall@5 | Recall@10 | MRR@10 | 平均上下文token |','| --- | --- | --- | --- | --- |']
    for m in ('base','child','parent_child'):lines.append('| '+m+' | '+' | '.join(n('structure_'+m+'_'+k) for k in ('r5','r10','mrr','context_tokens'))+' |')
    lines+=['','子块Recall@5下降；父子块Recall@10下降且上下文更大。原正式去重/重叠为零，没有冗余下降40%的相对收益。','','## 回答质量（AI正式集与人工样本分开）','','| 指标 | 原AI测试 | 人工抽样 |','| --- | --- | --- |']
    for m in ('answer_point_coverage','citation_correctness','condition_exception_retention'):lines.append('| '+m+' | '+n('ai_'+m)+' | '+n('human_'+m+'_numerator')+'/'+n('human_'+m+'_denominator')+' |')
    lines+=['','原AI正确拒答率'+n('ai_correct_refusal_rate')+'、错误拒答率'+n('ai_false_refusal_rate')+'；人工样本无不可回答题，正确拒答率无分母、不填100%。上述要点/引用/条件自动分数来自同一小模型，不能与人审混算。','','## 未执行/未测项','','| 项目 | 当前值 |','| --- | --- |']
    lines+=['| '+r['name']+' | 待测 |' for r in v['unmeasured']]
    lines+=['','## 全阶段档案','',
        '包含25条原实验/工程记录、2条早于Git的任务1/2记录以及1条本次任务14归档记录。早期参数/硬件未知项明确标待测；不拿后来机器状态补写历史。每条规范化记录含目标、对照、主要变量、数据/测试版本、源码、模型、参数、硬件、命令、原始结果、指标、结论与限制。','']
    return '\n'.join(lines)


def verify_archive(v):
    if v!=build(v['source_commit']):raise ValueError('Archive does not recompute exactly from frozen sources')
    if (FOLDER/'experiments.csv').read_text('utf-8')!=csv_text(v) or (FOLDER/'RESUME_FINAL.md').read_text('utf-8')!=resume_text(v) or (FOLDER/'RESULTS_FINAL.md').read_text('utf-8')!=results_text(v):raise ValueError('Rendered archive outputs differ')
    return True


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('build','verify','show'));p.add_argument('--source-commit');p.add_argument('--claim');p.add_argument('--group');p.add_argument('--experiment');a=p.parse_args()
    if a.action=='build':
        targets=[FOLDER/n for n in ('archive.json','experiments.csv','RESUME_FINAL.md','RESULTS_FINAL.md')]
        if any(t.exists() for t in targets):raise ValueError('Archive outputs must be new; existing frozen outputs are read only')
        v=build(a.source_commit or git('rev-parse','HEAD'));write_new(targets[0],v)
        for target,text in zip(targets[1:],(csv_text(v),resume_text(v),results_text(v))):
            with target.open('x',encoding='utf-8',newline='\n') as f:f.write(text)
        print(json.dumps({'status':'CREATED','records':len(v['records']),'claims':len(v['claims']),'groups':len(v['groups'])}))
    else:
        v=read(FOLDER/'archive.json')
        if a.action=='verify':verify_archive(v);print(json.dumps({'status':'PASS','records':len(v['records']),'claims':len(v['claims'])}))
        else:
            if sum(bool(x) for x in (a.claim,a.group,a.experiment))!=1:raise ValueError('Select exactly one claim, group or experiment')
            value=claim_map(v)[a.claim] if a.claim else v['groups'][a.group] if a.group else next(r for r in v['records'] if r['id']==a.experiment)
            print(json.dumps(value,ensure_ascii=False,indent=2))
