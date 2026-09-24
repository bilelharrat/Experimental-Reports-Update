---
en_sha256: 631ac116a7a4f1af623c13c213ab6f33a099990c8c5a33c949c5d97c8714162b
---
---
stage: early
version: 1
scorecard:
  market_size_growth: 20
  industry_position: 5
  moat: 10
  revenue_growth_quality: 10
  business_model_ue: 10
  team_governance: 25
  valuation: 10
  exit_certainty: 5
  risk_reward: 5
components:
- key_metrics_snapshot
- deal_terms
- board
- revenue
- key_operating_metrics
- scenario_analysis
- risk_register
- disconfirming_evidence
- investment_decision
- evidence_thresholds
- disclosures
- source_index
lint_extra_titles:
- investment decision
- closing view
- key metrics snapshot
- deal snapshot
- scorecard
- sources
- references
pseudo_sections:
- id: sources
  en_title: Sources, Source Classes, and Fact Reference Index
  zh_title: 来源、来源类别与事实索引
  numbered: true
  parity_en: ^\s*(?:(?:viii|8)[\.\、]\s*)?sources?(?:,\s*source\s+classes,\s*and\s+(?:fact\s+reference\s+index|disclosures))?\s*[:：]?\s*$
  parity_zh: ^\s*(?:(?:viii|8|八)[\.\、]\s*)?(?:来源、来源类别与事实索引|来源与事实索引|来源)\s*[:：]?\s*$
- id: validation_log
  en_title: 'Appendix: Source Treatment And Assumptions'
  zh_title: 附录：来源处理与假设
  numbered: false
---

早期结构档案（种子前至 A 轮）：七个固定章节。早期公司几乎没有已披露的
历史，因此这一结构评判的是这笔赌注、创始人与交易机制，而不是假装拥有
后期的证据基础——而且它的数据诚实义务更重而非更轻：未知的就写明未知，
每一次都如此。没有护城河表、没有增长桥、没有可比公司章节：这些主张在
这一阶段无法用证据支撑，取而代之的章节讲的是此时可以知道的东西。本
阶段评分卡权重（维度经重新诠释）：市场空间与增速 20 | 行业地位（切入点）5 |
护城河（潜在壁垒）10 | 收入增长与质量（早期验证）10 | 商业模式与单位经济 10 |
团队与治理 25 | 估值（交易条款）10 | 退出确定性 5 | 风险收益比 5。
每个章节都按其声明的编号小节组织；贯穿全篇的数据诚实、导航与图表规则
由共享上下文承载。已钉定的事实在共享事实表要求它出现的每个章节里逐字
写一次，其他地方只指代它、不再重复数字（"种子轮的估值上限"、"基准
情形"）；专业术语只在执行摘要的 "Terms used"（术语说明）块里定义一次，
此后直接使用。

## section: executive_summary
```yaml
id: executive_summary
en_title: Executive Summary
zh_title: 执行摘要
parity_en: ^\s*(?:(?:i|1)[\.\、]\s*)?executive\s+summary\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:i|1|一)[\.\、]\s*)?(?:执行摘要|核心摘要)\s*[:：]?\s*$
components: []
floor:
  min_real_blocks: 2
pass_affinity: []
title_word_aliases: []
role: exec
subsections:
- en: The bet
  zh: 这笔投资的赌注
- en: The round
  zh: 本轮融资方案
- en: Investment highlights
  zh: 核心投资亮点
- en: Key risks
  zh: 核心风险提示
- en: Recommendation
  zh: 投资结论与建议
```

500-700 词。执行摘要唯一的任务是说清什么最重要。它不含任何表格（收尾
的 "Terms used"（术语说明）是一个 `glossary` 块）——它需要的每一个数字都放在一句
解释该数字的句子里（Key Facts 表放在"创始团队与公司"章节，Deal Terms
表放在"交易条款与回报测算"章节）。各小节内容：

1. 这笔投资的赌注：一小段话，用平白的语言准确说明这笔投资要成功必须
   成为现实的条件——市场出现、这支团队赢下它、入场条款补偿了风险。
   这是早期备忘录应有的诚实口吻：把赌注称为赌注。然后是一句定位句
   （不超过 40 词）：公司做什么、为谁做、今天已有什么（产品已交付 /
   试点 / 原型）。
2. 本轮融资方案：工具（SAFE/可转债/定价轮）、融资规模、估值或估值
   上限，以及条款已经预设了什么——在同一口气里给出解读。仅用正文。
3. 核心投资亮点：以共享事实表中已钉定的案例总结句开头，用公司名称
   替换 "The case"——哪些维度支撑这笔赌注、哪些维度较弱，并附各自
   得分（在这一阶段通常由团队与市场支撑）。然后是一个带
   `"component": "investment_highlights"` 的 `bullets` 块，恰好三条，
   每条对应一个已钉定亮点，按钉定顺序：先是已钉定的标题原文（纯文本，
   不要写星号或 markdown；渲染器会把它加粗），再是已钉定的证据句，每个数字在读者看到它之前都先交代它
   衡量的是什么、来自哪里。绝不能出现光秃秃的主题标签（"Team."、
   "Market."），绝不能出现新数字。
4. 核心风险提示：一个带 `"component": "key_risks"` 的 `bullets` 块，
   恰好三条——按钉定顺序列出评分最高的三项已钉定风险，每条格式为
   "<Area label> — <pinned summary verbatim>.
   Impact: <pinned impact verbatim>. (N/10, <likelihood> likelihood)"。
5. 投资结论与建议：一个结论提示框——已钉定的投资建议句原文、入场
   条款、一行回报所需退出的算式（"a 3x fund return needs a $NNN M
   exit"），以及基金占位符原文。若有已钉定的结论档位与评分卡，以
   "{tier} — {total}/100" 开头。已钉定的
   `decision_history_sentence` 在提示框之后作为历史原文陈述。然后，作为
   本章的最后一个块，输出 "Terms used"（术语说明）：一个 `glossary` 块，
   `component: "glossary"`，其 `items` 为本备忘录用到的每个专业术语一项
   （SAFE、post-money、估值上限、MOIC、IRR、ARR、run-rate 等——6-15 项），
   每项形如 `{"term": {"en", "zh"}, "definition": {"en", "zh"}}`，定义
   五到十个词。所有这些术语只在这里定义；其他章节不再定义它们。

## section: company_team
```yaml
id: company_team
scorecard_dimensions:
- team_governance
en_title: Founders & Company
zh_title: 创始团队与公司
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?founders?\s*(?:&|and)\s*company\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:创始团队与公司|创始人与公司|团队与公司)\s*[:：]?\s*$
components:
- board
- key_metrics_snapshot
floor: {}
pass_affinity:
- team_governance
title_word_aliases:
- founders and company
subsections:
- en: Key facts
  zh: 关键事实
- en: Founders
  zh: 创始团队
- en: What exists today
  zh: 现有进展
- en: Board & governance
  zh: 董事会与治理
- en: Why this team wins — or doesn't
  zh: 团队为什么能赢
```

800-1,000 词。在这一阶段，团队占 100 分中的 25 分；本章决定这些分数是
给还是不给。各小节内容：

1. 关键事实：带 `component: "key_metrics_snapshot"`、标题为 "Key
   Metrics Snapshot" 的 "Key Facts" 表：阶段与轮次 | 融资规模与工具 |
   估值或估值上限 | 收入或牵引力替代指标 | 现金跑道 | 团队规模 |
   成立时间。缺失单元格："Not disclosed — <implication>"。
2. 创始团队："Founders" 表——每位创始人一行：姓名与职务 | 已核实的
   过往记录（带日期的事实，与自述简历分开）| 领域优势（为什么是这个
   人、这个问题）| 投入程度（是否全职？是否已归属？此前是否有退出？）。
3. 现有进展：一段对可证实事项的盘点——产品状态、已交付的代码或硬件、
   正在运行的试点、按职能划分的团队人数——每一项都标注日期。
4. 董事会与治理：带 `component: "board"` 的 "Board of Directors" 表：
   成员与所属机构；没有正式董事会的公司，以 "None — governance rests
   entirely with the founders" 作为该行，并附后果。
5. 团队为什么能赢：把创始人的优势与问题实际需要的能力相权衡；指出
   接下来两个关键招聘必须填补的缺口。以一句话答案开头；结尾重申结论。

本章以其已钉定的评分卡句收尾——针对 团队与治理 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: market_thesis
```yaml
id: market_thesis
scorecard_dimensions:
- market_size_growth
- industry_position
en_title: Market & Thesis
zh_title: 市场与投资逻辑
parity_en: ^\s*(?:(?:iii|3)[\.\、]\s*)?market\s*(?:&|and)\s*thesis\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iii|3|三)[\.\、]\s*)?(?:市场与投资逻辑|市场与论点|市场分析)\s*[:：]?\s*$
components: []
floor: {}
pass_affinity:
- market_sizing
title_word_aliases:
- market and thesis
subsections:
- en: The wedge
  zh: 切入点
- en: Market size
  zh: 市场空间
- en: Why now
  zh: 为什么是现在
- en: The ceiling question
  zh: 天花板问题
```

600-800 词。切入点能否打开一个大到值得关注的市场。各小节内容：

1. 切入点：具体的切入问题、它对首批客户为何紧迫，以及赢下它会打开
   哪个更大的市场。
2. 市场空间：首先是 "Market estimates" 表——找到的每一个估算各占一行
   （第三方研究机构、创始人路演材料中的 TAM 并如此标注、分析师测算，
   最后是本备忘录自己的推导），列为：来源 | 统计口径（定义）| 数值 |
   年份 | 如何得出；不因相互矛盾而剔除任何一项。随后是一段解读，以本
   备忘录采用的区间及理由开头，再用平白的话解释分歧所在。然后是
   "Market Sizing" 表——始终包含 TAM | SAM | SOM 三行，列为：定义 |
   当前规模 | 5-7 年后规模 | 依据/来源（指明各自所依赖的估算行或本
   备忘录自己的输入）。在这一阶段，多数单元格会是估算或缺失——写明
   哪个是哪种；绝不把创始人路演材料中的 TAM 当作独立数据呈现。然后是
   图表位 `chart_market_size`：一个 `chart` 块
   （grouped_bar；x = TAM / SAM / SOM；一个序列为当前、一个序列为
   5-7 年后的时点，用各自年份标注），仅由表中已披露或独立推导的数字
   构建，后接一句解读。当市场规模只是没有独立依据的估算时不出图：
   使用图表省略后备句。
3. 为什么是现在：使这件事在今天可建造、可购买而五年前不行的技术、
   成本或监管变化——附一个数据，或明确列为假设。
4. 天花板问题——在这一阶段权重更高，因为市场赌注是这笔赌注的大部分：
   如果一切顺利，这是一家 5 亿美元的公司还是 200 亿美元的公司，哪个
   假设决定了这一点。结论句放在最后。

本章以其已钉定的评分卡句收尾——每个维度一句，针对 市场空间与增速、行业地位 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: product_traction
```yaml
id: product_traction
scorecard_dimensions:
- moat
- revenue_growth_quality
- business_model_ue
en_title: Product & Early Validation
zh_title: 产品与早期验证
parity_en: ^\s*(?:(?:iv|4)[\.\、]\s*)?product\s*(?:&|and)\s*early\s+validation\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iv|4|四)[\.\、]\s*)?(?:产品与早期验证|产品与验证|早期验证)\s*[:：]?\s*$
components:
- revenue
- key_operating_metrics
floor: {}
pass_affinity:
- adoption_distribution
title_word_aliases:
- product and early validation
subsections:
- en: The product today
  zh: 产品现状
- en: Traction
  zh: 早期验证
- en: Operating metrics
  zh: 运营指标
- en: The strongest signal — both ways
  zh: 最强信号的两面
- en: What compounds
  zh: 什么能积累成壁垒
```

700-900 词。真正被验证了什么，而不是被宣称了什么。各小节内容：

1. 产品现状：产品今天能做什么（不是路线图），以及今天的产品与论点
   所需产品之间的诚实距离。
2. 早期验证：带 `component: "revenue"`、标题为 "Revenue & Traction
   Picture" 的 "Traction" 表——恰好以下 6 行：收入/ARR | 付费客户 |
   试点或意向书 | 使用指标（公司主打的那一个）| 留存或复用 | 销售
   管线。列：数值 | 截至日期 | 解读——而且每个解读单元格都必须说明
   该行是 EVIDENCE 还是 REVENUE（"6 pilots — evidence of interest,
   not revenue"）。
3. 运营指标：带 `component: "key_operating_metrics"` 的 "Key
   Operating Metrics" 表：这一阶段存在的少数几项——烧钱、现金跑道、
   人数、每个试点/单位的成本——数值 | 截至日期 | 解读。尚不可能存在的
   行要如实说明。
4. 最强信号的两面：把最强的验证信号从两面论证：牛市解读、熊市解读，
   以及证据偏向哪一边。
5. 什么能积累成壁垒：诚实地提出护城河潜力问题——如果这件事成功，会
   积累什么（数据、网络、转换成本、品牌）是复制者无法走捷径的？在
   这一阶段，答案是潜力，并要如此标注。

本章以其已钉定的评分卡句收尾——每个维度一句，针对 护城河、收入增长与质量、商业模式与单位经济 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: deal_returns
```yaml
id: deal_returns
scorecard_dimensions:
- valuation
- exit_certainty
en_title: Deal Terms & Required Returns
zh_title: 交易条款与回报测算
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?deal\s+terms\s*(?:&|and)\s*required\s+returns?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?(?:交易条款与回报测算|交易与回报|交易条款)\s*[:：]?\s*$
components:
- deal_terms
- scenario_analysis
floor:
  require_valuation_refs: true
pass_affinity:
- numbers_integrity
- valuation_exit
title_word_aliases:
- deal terms and required returns
- deal terms
role: valuation
subsections:
- en: Deal terms
  zh: 交易条款
- en: Entry vs stage norms
  zh: 估值对标
- en: Required exits
  zh: 回报所需退出
- en: The merely-good outcome
  zh: 一般成功情形
- en: Do the terms pay for the risk
  zh: 条款是否补偿风险
```

800-1,000 词。早期的价格纪律就在这里：工具的机制，以及入场价格已经
要求的结果。各小节内容：

1. 交易条款：带 `component: "deal_terms"` 的 "Deal Terms" 表——恰好
   以下各行：工具（SAFE/可转债/定价轮）| 融资规模 | 估值或估值上限 |
   折扣 | 按比例跟投权 | 知情权 | 董事会席位 | 清算优先权 | 期权池
   调整。此处缺失的条款是一项风险而不是脚注："Not disclosed —
   uncapped exposure to the next round's price"，且重大缺口要在风险
   章节回应。
2. 估值对标：入场估值对照该行业与地域已披露的阶段常态——高于、持平
   还是低于，以及高于常态意味着什么要求。
3. 回报所需退出：带 `component: "scenario_analysis"` 的 "Required
   Exits" 表——行为 3x | 5x | 10x 毛回报倍数(MOIC)，列为 所需退出
   估值 | 稀释假设 | 退出时隐含收入（按所述倍数）| 可能性如何（结论
   片段）。凡有钉定之处，单元格精确重复已钉定的情景数字；回报所需
   退出的算式在行内展示。然后是图表位 `chart_required_exits`：一个
   `chart` 块（建议 bar；x = 3x / 5x / 10x；y = 所需退出估值），由
   同一组数字构建，后接一句解读。
   然后是"必须成立什么"：当共享事实表带有 Python 计算的价格问题行 ——
   在这个价格下收回本金、达到基金门槛和取得 3 倍所需的退出价值与退出年
   收入；保本入场价；各情景相对最新披露收入所隐含的增速；退出推迟一两年
   时的基准情形 IRR；有出资额备案时 BSH 各情景的所得 —— 逐字陈述每一行
   并附其 [C#]，再用一句话说明"所需"与基准情形假设之间的差距意味着什么：
   一个基准情形若已经要求超出公司已证明的水平，那它只是贴着基准标签的
   牛市情形。事实表没有这些行时，一字不写 —— 绝不在此自行计算。
4. 一般成功情形：一个一般成功的结果（最常见的早期"成功"：5,000 万至
   1.5 亿美元的被收购）在扣除其上方的优先层级后，给这张支票带来多少
   回报——以美元和回报倍数(MOIC)计。
5. 条款是否补偿风险：用两三句话，把价格与赌注放在一起衡量。以一句话
   答案开头；结尾重申结论。

本章以其已钉定的评分卡句收尾——每个维度一句，针对 估值、退出确定性 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: risks_milestones
```yaml
id: risks_milestones
scorecard_dimensions:
- risk_reward
en_title: Risks & Milestones
zh_title: 风险与里程碑
parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?risks?\s*(?:&|and)\s*milestones?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?(?:风险与里程碑|风险分析|投资风险)\s*[:：]?\s*$
components:
- risk_register
- disconfirming_evidence
floor:
  bullets_or_prose: true
pass_affinity:
- alternative_explanations
title_word_aliases:
- risks and milestones
- risk analysis
role: risk
subsections:
- en: The center of gravity
  zh: 风险重心
- en: Risk cards
  zh: 风险卡片
- en: Disconfirming evidence
  zh: 反面证据
- en: Milestone map
  zh: 里程碑地图
- en: Risk/reward verdict
  zh: 风险收益结论
```

700-900 词。什么会让这家公司死掉，什么能证明它正在奏效。各小节内容：

1. 风险重心：一段话，指出哪一个单一风险承载着这笔赌注。
2. 风险卡片：4-6 张按风险逐一展开的卡片，按评分从高到低排序，严格
   使用已钉定的风险列表与评分。卡片 = 三级标题（已钉定的总结——一个
   完整的结论句，绝不是主题标签）+ 带 `component: "risk_register"` 的
   key_value 表。卡片格式见指令中的风险卡合约：按合约规定的固定行和顺序
   填写。在这一阶段，"跟踪信号"要写出消除该风险的里程碑——可观察的证明点
   及其预期日期，因为下一轮定价看的正是它。
3. 反面证据：带 `component: "disconfirming_evidence"` 的论述：反对
   这笔赌注的最有力事实，每条用一句话权衡。
4. 里程碑地图："Milestone Map" 表——未来 18-24 个月——里程碑 | 预期
   日期 | 它消除的风险 | 错过意味着什么。这是本轮融资的花钱计划，当作
   证据来读。
5. 风险收益结论：收尾的风险/收益结论段落。

本章以其已钉定的评分卡句收尾——针对 风险收益比 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: investment_decision
```yaml
id: investment_decision
en_title: Investment Decision
zh_title: 投资决定
parity_en: ^\s*(?:(?:vii|7)[\.\、]\s*)?(?:final\s+)?investment\s+decision\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vii|7|七)[\.\、]\s*)?(?:投资决定|最终投资决定|投资结论)\s*[:：]?\s*$
components:
- investment_decision
- evidence_thresholds
- disclosures
floor:
  min_real_blocks: 2
pass_affinity: []
title_word_aliases:
- final investment decision
- investment decision
subsections:
- en: The six questions
  zh: 六个关键问题
- en: Scorecard
  zh: 评分卡
- en: Demonstrated vs still a bet
  zh: 已证明与仍是赌注
- en: Recommendation
  zh: 投资建议
- en: Monitoring & triggers
  zh: 投后监控与触发条件
```

500-700 词。各小节内容：

1. 六个关键问题：带 `component: "evidence_thresholds"`、标题为
   "Evidence Thresholds — The Six Questions" 的 "Six Questions" 表
   ——早期版六问，每行以 Yes / No / Qualified 作答并附一行依据：
   切入点是否打开一个值得关注的市场？| 这支团队是否就是相信的理由？|
   是否有真实的早期验证，而不只是兴趣？| 如果成功，优势能否积累？|
   条款是否补偿风险？| 一个能够返还整只基金的退出是否合理存在？每
   一个 No 或 Qualified 都配一段"什么会翻转它"的说明。
2. 评分卡："Scorecard" 表——9 个固定维度，采用早期权重与重新诠释：
   市场空间与增速 20 | 行业地位（切入点）5 | 护城河（潜在壁垒）10 |
   收入增长与质量（早期验证）10 | 商业模式与单位经济 10 | 团队与治理 25 |
   估值（交易条款）10 | 退出确定性 5 | 风险收益比 5。列为 得分 | 理由
   （一行）。已钉定的评分卡精确重复；以合计行与门槛句收尾（80 分
   以上投资 / 70-79 分观察 / 70 分以下放弃）。
3. 已证明与仍是赌注：等长的两个列表（各 3-4 条）"What is
   demonstrated" / "What remains a bet"——早期备忘录对未解决事项的
   诚实表述方式。
4. 投资建议：带 `component: "investment_decision"` 的投资建议提示框：
   已钉定的投资建议句原文、入场条款、回报所需退出那一行，以及基金
   占位符原文。随后是一段带 `component: "disclosures"` 的一行法律
   披露。已钉定的 `decision_history_sentence` 作为历史原文重述。
   当共享事实表钉定了 `prior_view_sentence`（BSH 上一份备忘录对本公司
   的结论）时，同样在提示框旁逐字重述，随后用一句话说明此后发生了什么
   变化，或为何维持原判。它是历史而非证据：不得引用上一份备忘录中的
   任何数字。
5. 投后监控与触发条件："Monitoring Indicators" 表（投后监控）：3-5
   行——指标 | 当前值 | 触发阈值 | 应对措施——取自里程碑地图。当结论为
   观察/放弃时，标题改为 "What changes the verdict"。
