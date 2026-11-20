"""Assemble explicit Codex source-reading judgments, keyed to exact E7 outputs.

This is a review ledger, NOT a semantic validator or answering-model prompt.
Every new output requires a new authored entry; there is no default judgment.
"""
import argparse
import json
from pathlib import Path
from score_e7_mapping import ROOT, read, digest, sha

# Each edge flag follows requirement order, then supporting_ids order. A true
# flag means the whole stated requirement is supported, not just a related part.
# Point indices refer to the independently frozen necessary-point list.
JUDGMENTS = {
 '301fc0a2': ([[0]], [True], 'L01-01明确人造场地只能为绿色；单要点问题的复述足以标明所问属性。'),
 '504f1c63': ([[0],[1]], [True,True], 'L01-03分别明确7.32米和2.44米。'),
 'dc8c0c89': ([[0],[1]], [True,True], 'L02-02分别给出5号球68—70厘米和410—450克。'),
 'cae13051': ([[0],[0]], [True], '虽合并一项，但明确同时询问人数上限与必有位置，L03-01完整支持两部分。'),
 'b1ff9589': ([[0],[0]], [True,False,False], 'L08A-02完整支持；L08A-03只含站位违规和未给数值的规定距离，属部分支持；L15-02是界外球2米，主题不符。'),
 'f287cb7d': ([[0],[1]], [True,True], 'L10-01两句直接支持两个要点。'),
 'cb956d9a': ([[],[],[]], [True,False,True], '仅复述位置问题，未显式拆出场内/罚球区外、罚球点后及9.15米。L14-02可完整回答，原文渲染补足未拆要点。第二项误把他段的开球例外提示归到L01-06；第三项虽有原文支持，却没有补齐所需三个条件。'),
 'e53848b4': ([[],[],[]], [False,False,False], '把已排除的主罚者和守门员列为要点，却未列出其他队员所需三个条件。L14-03是执行动作和进入时机，不完整支持三项位置问题。'),
 '86d1d23d': ([[0],[1]], [True,True], 'L16-03明确被踢且明显移动即进入比赛，无须离开罚球区。'),
 '3a48bc41': ([[0],[1]], [True,True,True,False], 'L13-05支持任意球可能越位；L11-03和L15-03支持界外球例外；L16-03只谈球门球例外。'),
 'cab5883e': ([[0],[1]], [False,True,False], '第一项把任意球可能越位反写成不越位，L13-05实际反驳该断言；L15-03支持界外球例外，L16-03不支持界外球。最终原文正确不等于映射文字正确。'),
 '489cbd74': ([[0],[1]], [False,False], 'L06-05讨论VAR和预备官员的发展，不能支持球门线附近的附加助理裁判身份及非强制配备。'),
 'a1909dbf': ([[0],[1]], [True,True], 'L06-06直接支持附加助理裁判及历史批准不等于赛事强制配备。'),
 'f3b5fe82': ([[2],[0,2],[]], [True,False,True,True,True], 'L12-06区分技术性违例与不当行为；L12-15不说明技术性违例，只说明不当行为与比赛中身体犯规的界限。没有显式列出警告或罚令出场；正确原文被选中后仍覆盖该遗漏。'),
 '7689948b': ([[2],[0,1],[]], [False,False,True,False,True], '前两项近义重复。L12-02是手球，L12-15没有技术性违例分类，均不能支持前两项的完整关系；仅L12-06正确支持第二项。错误把L12-15填满三项后，程序最大覆盖选中它，漏掉L12-06。'),
 'b6479cce': ([[2],[0,1,2],[]], [True,False,True,False,True], '前两项重复；L12-15不支持技术性违例与不当行为分类。L12-06正确支持全部关系项，但处罚要点没有显式拆出。'),
 'f6c9b5ee': ([[],[],[0]], [False,False,True], '未拆出重启、决胜目的和不计正常进球数三个要点，只泛问计分区别并新增执行动作。L14-01只支持比较的一侧，L14-03不支持计分比较；执行规则有支持但偏离所问，程序据此选L14-03。'),
 '14eccadc': ([[],[],[0]], [False,False], '仅保留整个比较问题，两个候选均不完整支持比较，且完全没有映射L07-03。覆盖相同按原顺序选L14-03，而不是排在最后的L14-01。'),
 'cb8c43c7': ([[],[],[0]], [False,False], '原上下文缺L14-01；L07-03可支持决胜目的及不计正常进球数，但无法独立支持完整两侧比较。不得把一侧部分支持自报为全覆盖。'),
}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    cases={c['case_id']:c for c in read(a.prepared)['cases']}
    reviews={}
    unknown=[]
    for path in sorted(a.run.glob('*-B-r?.json')):
        t=read(path)
        for attempt in t['observations']['model_attempts']:
            audit=attempt.get('mapping_validation')
            if not audit:continue
            reqs=audit['requirements'];h=digest(reqs);key=t['case_id']+':'+h
            if key in reviews:
                reviews[key]['observed_traces'].append(dict(file=path.name,sha256=sha(path)))
                continue
            short=h[:8]
            if short not in JUDGMENTS:
                unknown.append(dict(key=key,requirements=reqs));continue
            matches,flags,note=JUDGMENTS[short]
            c=cases[t['case_id']]
            flattened=[(i,cid) for i,r in enumerate(reqs) for cid in r['supporting_ids']]
            assert len(flags)==len(flattened) and len(matches)==len(c['necessary_points'])
            edges=[]
            for (i,cid),flag in zip(flattened,flags):
                edges.append(dict(requirement_index=i,chunk_id=cid,supports=flag,
                    partially_supports_frozen_points=[] if flag else [j for j,ids in enumerate(c['support_per_point']) if cid in ids],
                    note=note))
            valid=[bool(indices) for indices in matches]
            if short=='cab5883e':valid[0]=False
            reviews[key]=dict(case_id=t['case_id'],requirements=reqs,necessary_points=c['necessary_points'],
                frozen_point_to_model_requirements=matches,point_decomposition_valid=valid,edge_support=edges,note=note,
                source_trace=c['source_trace'],source_sha256=c['source_sha256'],
                observed_traces=[dict(file=path.name,sha256=sha(path))])
    assert not unknown,json.dumps(unknown,ensure_ascii=False)
    value=dict(reviewer='Codex direct source reading; no new human/expert review',
        timing='Post-inference audit of model mappings, not model feedback or changes to frozen final-answer labels.',
        rubric='Question-form requirements may identify a requested attribute without asserting its value. A generic restatement of a multi-condition question is not explicit decomposition of unmentioned conditions. Wrong polarity is separately invalidated. Each whole-requirement edge is checked independently; compound partial support is recorded separately. Final rendered answer scoring uses original frozen source/point support, not these model claims.',
        prepared_sha256=sha(a.prepared),reviews=reviews)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(dict(unique_mappings=len(reviews),reviewed_B_observations=sum(len(v['observed_traces']) for v in reviews.values())),ensure_ascii=False))


if __name__=='__main__':main()
