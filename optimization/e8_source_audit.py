"""Authored E8 diagnostic source audit. Never import these labels into inference.

All original E7 requirements are retained verbatim for relation-only replay.
Every profile rates every offered paragraph, including previously unmapped ones.
These are Codex readings of the supplied corpus, not new human/expert judgments.
"""
DIRECT='direct_support'
PARTIAL='partial_support'
REFUTE='refutation'
UNRELATED='unrelated'

NEUTRAL={
 'T026-expanded':[
    '只说发生技术性违例时，能否直接认定发生了身体犯规？',
    '资料在术语分类上怎样区分技术性违例与不当行为？',
    '不当行为可能受到哪些纪律处罚？'],
 'T034-expanded':[
    '比赛中判罚的罚球点球是什么性质的程序？',
    '点球决胜用于决定什么比赛结果？',
    '点球决胜罚中次数与本场正常进球数如何关联？'],
 'D017-native':[
    '点球执行前，除主罚者和守门员外，其他队员相对场地边界及罚球区的位置有什么要求？',
    '点球执行前，除主罚者和守门员外，其他队员相对罚球点的前后位置有什么要求？',
    '点球执行前，除主罚者和守门员外，其他队员与罚球点的最小距离如何规定？'],
 'D021-native':[
    '直接接到任意球时，越位待遇如何，是否存在不因直接接球而判越位的例外？',
    '直接接到界外球时，越位待遇如何？'],
}

QUOTES={
 'tech':'某些行为按技术性违例处理，例如违反重启程序；另一些则属于不当行为，应给予警告或罚令出场。',
 'not_all':'并非所有违反《足球竞赛规则》的行为都属于“犯规”。',
 'misconduct':'发生在比赛外状态下的违例可以构成不当行为，但不属于比赛进行中的身体犯规。',
 'sanction':'如果裁判专门停止比赛以警告或罚下一名队员，且同时发生犯规',
 'physical':'多数这类犯规涉及双方身体接触。',
 'physical_sanction':'草率行为构成应处罚的犯规；鲁莽行为还可能受到黄牌警告；使用过分力量则可能导致红牌罚令出场。',
 'restart':'罚球点球是一种重启方式，由一名队员面对仅由对方守门员防守的球门射门。',
 'shootout':'点球决胜的目的则是确定哪支球队晋级或夺冠，其罚中次数不作为本场比赛正常进球数的一部分。',
 'execution':'球在执行前必须静止，且必须向前踢。',
 'entry':'球被踢并移动后进入比赛，此时其他队员才可以进入罚球区和罚球弧区域。',
 'others':'其他队员必须留在场内、罚球区外、罚球点后方，并距罚球点至少9.15米。',
 'arc_distance':'罚球弧用于辅助标示这一距离。',
 'kicker':'无论犯规发生在罚球区内的哪个位置，球都放到罚球点上。主罚队员必须向裁判明确。',
 'keeper':'守门员在球被踢前可以移动，但应面对主罚者，处于两根门柱之间的球门线上，并且不能触摸门柱、横梁或球网。',
 'arc':'执行罚球点球时，罚球区与罚球弧共同划定了其他队员不得提前进入的范围；在球进入比赛之前，这一限制适用于主罚队员和守方守门员以外的队员。',
 'point':'罚球点位于球门正中央前方12码处，原文换算为约10.97米。罚球点球从这一位置执行。',
 'approx':'罚球区外的弧线称为罚球弧，原文给出的半径为以罚球点为中心的10码，约9.14米。',
 'free_offside':'任意球踢出后，进攻队员可能构成越位犯规。这一点与直接接球门球、角球或界外球时的越位例外不同。',
 'exceptions':'直接接到球门球、角球或界外球，不构成越位犯规。',
 'throw':'队员直接接到界外球，不会因此被判越位犯规。',
}


def rating(label, quote_keys=(), note=''):
    return dict(label=label,quotes=[QUOTES[k] for k in quote_keys],note=note)


def d(*quotes,note=''):return rating(DIRECT,quotes,note)
def p(*quotes,note=''):return rating(PARTIAL,quotes,note)
def r(*quotes,note=''):return rating(REFUTE,quotes,note)
def u(note='该段不提供所问对象/关系的依据'):return rating(UNRELATED,(),note)

# Explicit five-column source judgments, in the frozen offered order.
PROFILES={
 'technical_misconduct':[
    d('tech'),p('misconduct',note='仅说明不当行为与身体犯规的界限，未说明技术性违例类别。'),u(),u(),u()],
 'misconduct_physical':[
    d('not_all','tech'),d('misconduct'),u(),p('physical','physical_sanction',note='描述身体犯规及出牌，未完整区分不当行为。'),u()],
 'technical_physical':[
    d('not_all','tech'),p('misconduct',note='并未讨论技术性违例，不能用不当行为替代该类别。'),u(),p('physical',note='仅解释身体犯规，未说明技术性违例关系。'),u()],
 'sanctions':[
    d('tech'),d('sanction'),u(),p('physical_sanction',note='仅描述身体犯规的不同程度及出牌，不完整覆盖不当行为类别。'),u()],
 'scoring_comparison':[
    u(),p('shootout',note='只支持点球决胜一侧，未说明比赛中罚球点球的性质。'),u(),u(),p('restart',note='只支持比赛中罚球点球一侧，未说明点球决胜计分。')],
 'execution_rules':[
    u(),u(),d('execution','entry'),u(),p('restart',note='仅给出性质及放球点，不完整给出执行动作和限制。')],
 'penalty_nature':[
    u(),u(),p('entry',note='有执行后进入比赛的描述，但未明确说明程序性质。'),u(),d('restart')],
 'shootout_purpose':[
    u(),d('shootout'),u(),u(),u()],
 'shootout_scoring':[
    u(),d('shootout'),u(),u(),u()],
 'all_other_positions':[
    d('others'),u(),p('entry',note='只有不得提前进入罚球区/弧，没有场地边界、前后和完整距离条件。'),p('arc','approx',note='只有部分区域边界和约值，缺场内及罚球点后条件。'),u()],
 'kicker_document_exception':[
    u(),u('该段提示的是开球主罚者位置例外，不是点球主罚者。'),u(),u(),u()],
 'arc_boundary':[
    d('others','arc_distance'),u(),d('entry'),d('arc'),u()],
 'kicker_position':[
    d('kicker'),u(),p('execution',note='给出踢球动作，未给出放球点位置。'),p('point',note='说明球的执行点，未完整说明题称主罚者位置条件。'),u()],
 'keeper_position':[
    d('keeper'),u(),u(),u(),u()],
 'field_area_position':[
    d('others'),u(),p('entry',note='缺留在场内条件。'),p('arc',note='缺留在场内条件。'),u()],
 'relative_position':[
    d('others'),u(),u(),u(),u()],
 'minimum_distance':[
    d('others'),u(),p('entry',note='只提进入罚球弧的时机，没有最小距离。'),p('approx','arc',note='10码约9.14米为几何描述，未直接给出完整最小距离规定；与L14-02的9.15米须保留差异。'),u()],
 'free_treatment':[
    d('free_offside'),u(),u('本段列出三种重启的例外，未直接说明任意球待遇。'),u(),u()],
 'free_negative':[
    r('free_offside',note='“可能构成”直接反驳“任意球不构成越位”这一无条件否定。'),u(),u('不能仅以未列出任意球替代直接反驳证据。'),u(),u()],
 'throw_treatment':[
    d('free_offside'),u(),d('exceptions'),d('throw'),u('L16-03只说明球门球，不说明界外球。')],
}

ALIASES={
 '区分技术性违例与不当行为':'technical_misconduct',
 '技术性违例与不当行为的区别':'technical_misconduct',
 '不当行为与身体犯规的区别':'misconduct_physical',
 '不当行为与身体犯规的关系':'misconduct_physical',
 '技术性违例与身体犯规的关系':'technical_physical',
 '罚球点球与点球决胜在本场计分上有何区别？':'scoring_comparison',
 '罚球点球的执行规则是什么？':'execution_rules',
 '点球执行前，除主罚者和守门员外的队员要满足哪些位置条件？':'all_other_positions',
 '点球执行前，主罚者的位置例外见第二份文档。':'kicker_document_exception',
 '点球执行前，罚球区与罚球弧共同划定了其他队员不得提前进入的范围。':'arc_boundary',
 '点球执行前，主罚者的位置条件。':'kicker_position',
 '点球执行前，守门员的位置条件。':'keeper_position',
 '点球执行前，其他队员的位置条件。':'all_other_positions',
 '直接接任意球的越位待遇':'free_treatment',
 '直接接界外球的越位待遇':'throw_treatment',
 '直接接任意球不构成越位犯规。':'free_negative',
 '直接接界外球不构成越位犯规。':'throw_treatment',
}
NEW_PROFILES={
 'T026-expanded':['technical_physical','technical_misconduct','sanctions'],
 'T034-expanded':['penalty_nature','shootout_purpose','shootout_scoring'],
 'D017-native':['field_area_position','relative_position','minimum_distance'],
 'D021-native':['free_treatment','throw_treatment'],
}
