---
en_sha256: 83c8498aa6657a8fd16277cabd50af646ebe3e0efea225341251162fc04a0b14
---
---
stage: growth
version: 1
scorecard:
  market_size_growth: 15
  industry_position: 12
  moat: 13
  revenue_growth_quality: 15
  business_model_ue: 12
  team_governance: 13
  valuation: 10
  exit_certainty: 5
  risk_reward: 5
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
  parity_en: ^\s*(?:(?:x|10)[\.\、]\s*)?sources?(?:,\s*source\s+classes,\s*and\s+(?:fact\s+reference\s+index|disclosures))?\s*[:：]?\s*$
  parity_zh: ^\s*(?:(?:x|10|十)[\.\、]\s*)?(?:来源、来源类别与事实索引|来源与事实索引|来源)\s*[:：]?\s*$
- id: validation_log
  en_title: 'Appendix: Source Treatment And Assumptions'
  zh_title: 附录：来源处理与假设
  numbered: false
---

成长期结构档案（B/C 轮）：九个固定章节，由后期 v2 合并版 IC 结构派生而来
——概况与团队合并，竞争与护城河两章合并，估值/回报/退出合并，因为成长期
公司披露得更少，判断的权重转向增长质量与团队。本阶段评分卡权重：
市场空间与增速 15 | 行业地位 12 | 护城河 13 | 收入增长与质量 15 |
商业模式与单位经济 12 | 团队与治理 13 | 估值 10 | 退出确定性 5 |
风险收益比 5。每个章节都按其声明的编号小节组织；贯穿全篇的数据诚实、
导航与图表规则由共享上下文承载。已钉定的事实在共享事实表要求它出现的
每个章节里逐字写一次，其他地方只指代它、不再重复数字（"2026 年 3 月的
估值标记"、"基准情形"）；专业术语只在执行摘要的 "Terms used"（术语说明）
块里定义一次，此后直接使用。

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
- en: Company profile
  zh: 项目基本概况
- en: The round
  zh: 本轮融资方案
- en: Investment highlights
  zh: 核心投资亮点
- en: Key risks
  zh: 核心风险提示
- en: Recommendation
  zh: 投资结论与建议
```

600-800 词。执行摘要唯一的任务是说清什么最重要。它不含任何表格（收尾
的 "Terms used"（术语说明）是一个 `glossary` 块）——它需要的每一个数字都放在一句
解释该数字的句子里（Deal Snapshot 与 Key Metrics Snapshot 两张表放在
"公司与团队"章节）。各小节内容：

1. 项目基本概况：公司做什么、为谁做、所处行业与地域，以及一句话说明
   它在成长阶梯上的位置（可复制的销售模式是否已被验证）。正文不超过
   80 词。
2. 本轮融资方案：轮次、工具、规模、价格、隐含持股比例——以及这个价格
   已经预设了什么，在同一口气里给出解读。仅用正文。
3. 核心投资亮点：以共享事实表中已钉定的案例总结句开头，用公司名称
   替换 "The case"——一小段话说明哪些维度支撑本案、哪些维度较弱，并
   附各自得分。然后是一个带 `"component": "investment_highlights"` 的
   `bullets` 块，恰好三条，每条对应一个已钉定亮点，按钉定顺序：先是
   已钉定的标题原文（纯文本，不要写星号或 markdown；渲染器会把它加粗），
   再是已钉定的证据句。每个数字在读者
   看到它之前，都先交代它衡量的是什么、来自哪里——一个具名来源，或
   "our own estimate"（我们自己的估算）及其输入。绝不能出现光秃秃的主题标签
   （"Price."、"Market size."），绝不能出现新数字。
4. 核心风险提示：一个带 `"component": "key_risks"` 的 `bullets` 块，
   恰好三条——按钉定顺序列出评分最高的三项已钉定风险，每条格式为
   "<Area label> — <pinned summary verbatim>.
   Impact: <pinned impact verbatim>. (N/10, <likelihood> likelihood)"。
   不得出现新数字，不得改写总结。
5. 投资结论与建议：一个结论提示框——已钉定的投资建议句原文、入场
   条件、合理估值区间、来自已钉定情景的基准情形结果、持有期，以及
   基金占位符原文。若有已钉定的结论档位与评分卡，以
   "{tier} — {total}/100" 开头。已钉定的
   `decision_history_sentence` 在提示框之后作为历史原文陈述。然后，作为
   本章的最后一个块，输出 "Terms used"（术语说明）：一个 `glossary` 块，
   `component: "glossary"`，其 `items` 为本备忘录用到的每个专业术语一项
   （MOIC、IRR、ARR、NRR、CAGR、TAM/SAM/SOM、run-rate、post-money、MOU
   等——6-15 项），每项形如 `{"term": {"en", "zh"}, "definition": {"en",
   "zh"}}`，定义五到十个词。所有这些术语只在这里定义；其他章节不再
   定义它们。

## section: company_team
```yaml
id: company_team
scorecard_dimensions:
- team_governance
en_title: Company & Team
zh_title: 公司与团队
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?company\s*(?:&|and)\s*team\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:公司与团队|公司与创始团队|公司概况与团队)\s*[:：]?\s*$
components:
- board
- key_metrics_snapshot
- deal_terms
floor: {}
pass_affinity:
- adoption_distribution
- team_governance
title_word_aliases:
- company and team
subsections:
- en: Company facts & key metrics
  zh: 公司基本情况与关键指标
- en: Funding history & this round
  zh: 融资历史与本轮方案
- en: Development milestones
  zh: 发展历程
- en: Leadership & board
  zh: 管理团队与董事会
- en: Founder-market fit
  zh: 创始人与赛道匹配
- en: Scale-up readiness
  zh: 规模化准备度
```

1,100-1,400 词。公司的故事与正在推动它规模化的人，放在一起评判——在
成长期，团队本身就是大部分证据。各小节内容：

1. 公司基本情况与关键指标：一张 "Company Facts" key_value 表（成立
   时间 | 总部 | 员工人数及 12 个月变化 | 创始人与 CEO | 主营业务，
   一句话），然后是带 `component: "key_metrics_snapshot"` 的 "Key
   Metrics Snapshot" 表：ARR/收入 | 增长率 | 毛利率 | 净收入留存 |
   烧钱倍数 | 现金跑道 | 上轮/本轮估值及隐含倍数。列：最近两个期间，
   加一列 +3 年，该列仅承载已钉定的基准情形数字。
2. 融资历史与本轮方案：一张 "Funding History" 表（每一轮已披露融资
   ——日期 | 轮次 | 金额 | 投后估值 | 领投方 | 相对上一轮的价格变化），
   然后是带 `component: "deal_terms"` 的 "Deal Snapshot" key_value
   表，恰好以下 10 行：轮次 | 工具 | 融资规模 | 投前估值 | 投后估值 |
   隐含持股比例 | 新股/老股比例 | 资金用途 | 跟投方 | 预计交割时间。
   缺失单元格："Not disclosed — <implication>"。以一段对表格的简短
   解读收尾，该解读以结论开头——这些估值标记支持还是削弱了入场价格
   ——然后给出证明它的数字。
3. 发展历程：2-3 段，讲因果，不讲日期。
4. 管理团队与董事会："Leadership" 表（CEO 及关键高管——职务 | 过往
   履历 | 优势或短板，以结论片段表述；空缺的关键岗位作为一行列出并
   写明后果），然后是带 `component: "board"` 的 "Board of Directors"
   表（成员、所属机构、战略价值），再加一个所有权与治理 key_value 块
   （创始人控制权、期权池、保护性条款）。
5. 创始人与赛道匹配：以一句话答案开头——这些创始人是否可证明地是解决
   这一问题的合适人选——然后给出证明：每位创始人此前建造或运营过什么、
   而这门生意确实需要它（带日期的已核实事实，与自述简历分开），以及
   记录在哪些地方是空白的。在另一学科里的辉煌背景，就如实表述为另一
   学科的背景。以结论收尾：匹配已由过往工作证明、有主张但未证明、
   或不存在。
6. 规模化准备度：这支团队能否运营一家规模是现在 5-10 倍的公司——
   招聘记录、高管梯队、对创始人的依赖，以及创始人缺席一个季度时组织
   会是什么样。以一句话答案开头；结尾重申结论。

本章以其已钉定的评分卡句收尾——针对 团队与治理 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: market_industry
```yaml
id: market_industry
scorecard_dimensions:
- market_size_growth
en_title: Market & Industry Analysis
zh_title: 市场与行业分析
parity_en: ^\s*(?:(?:iii|3)[\.\、]\s*)?market\s*(?:&|and)\s*industry(?:\s+analysis)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iii|3|三)[\.\、]\s*)?(?:市场与行业分析|市场分析|行业分析)\s*[:：]?\s*$
components: []
floor: {}
pass_affinity:
- market_sizing
title_word_aliases:
- market and industry analysis
subsections:
- en: Market definition & value chain
  zh: 赛道定义与产业链位置
- en: Market size
  zh: 市场空间
- en: Growth drivers
  zh: 增长驱动
- en: The ceiling question
  zh: 天花板问题
- en: Policy & regulation
  zh: 政策与监管
```

800-1,000 词。市场能否支撑价格所需要的 5-10 倍。各小节内容：

1. 赛道定义与产业链位置：公司实际竞争的市场、在产业链中的位置、
   上下游各由谁攫取价值。
2. 市场空间：首先是 "Market estimates" 表——调研找到的每一个估算各占
   一行（每家第三方研究机构、公司自己宣讲的 TAM、投行或分析师的测算，
   最后是本备忘录自己的推导），列为：来源 | 统计口径（定义）| 数值 |
   年份 | 如何得出；估算不会因为相互矛盾而被剔除——表格展示的正是
   各自采用的定义。随后是一段解读，以本备忘录采用的区间及该定义为何
   适合这家公司开头，再用平白的话解释分歧所在。然后是 "Market
   Sizing" 表——始终包含 TAM | SAM | SOM 三行，列为：定义 | 当前
   规模 | 退出年规模 | CAGR | 依据/来源（指明各自所依赖的估算行或本
   备忘录自己的输入）；缺失行遵循缺失数据规则，绝不借用数字。然后是
   图表位 `chart_market_size`：一个 `chart` 块（grouped_bar；x =
   TAM / SAM / SOM；一个序列为当前、一个序列为退出年，用实际年份
   标注），仅由表中已披露或可推导的数字构建，后接一句解读。序列未
   披露时不出图：使用图表省略后备句。
3. 增长驱动：每个驱动因素一句主张加一个支撑数据；无支撑的驱动因素
   以具名假设列出。
4. 天花板问题：市场把这家公司封顶在什么位置、哪个假设会移动这个区间，
   以一句话答案开头；最后重申结论。
5. 政策与监管——绝不能悄然省略；若无相关政策，就明说，并说明什么
   可能改变这一点。

本章以其已钉定的评分卡句收尾——针对 市场空间与增速 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: product_business_model
```yaml
id: product_business_model
scorecard_dimensions:
- business_model_ue
en_title: Product, Business Model & Unit Economics
zh_title: 产品、商业模式与单位经济
parity_en: ^\s*(?:(?:iv|4)[\.\、]\s*)?product,?\s*business\s+model\s*(?:&|and)\s*unit\s+economics\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iv|4|四)[\.\、]\s*)?(?:产品、商业模式与单位经济|产品与商业模式|商业模式与单位经济)\s*[:：]?\s*$
components:
- key_operating_metrics
floor: {}
pass_affinity:
- adoption_distribution
title_word_aliases:
- product, business model and unit economics
- product and business model
subsections:
- en: Why customers pay
  zh: 客户为什么付费
- en: Revenue model
  zh: 收入模式
- en: Key operating metrics
  zh: 关键运营指标
- en: Revenue quality
  zh: 收入质量
- en: Demand signals — both ways
  zh: 需求信号的两面
- en: Repeatability
  zh: 销售可复制性
```

1,000-1,300 词。客户为什么付费，以及销售模式是否已经成为一台机器。
各小节内容：

1. 客户为什么付费：买方、问题、替代方案、客户侧的经济账、最有力的
   已披露证明点。
2. 收入模式：一张 "Revenue Model" key_value 表——收入来源 | 定价
   模式 | 合同期限与条款 | 收入确认性质。
3. 关键运营指标：带 `component: "key_operating_metrics"` 的 "Key
   Operating Metrics" 表——恰好以下 8 行：客户数 | 最大客户渗透率 |
   前十大客户收入集中度 | 净收入留存 | 毛留存 | CAC 回收期 |
   LTV/CAC 或 magic number | 人均 ARR。列：数值 | 截至日期 | 基准 |
   解读（结论片段）。
4. 收入质量："Revenue Quality Split" 表（经常性、已承诺、项目制、
   集中型收入各自的占比及所带的风险），然后是收入等式段落：收入 =
   客户数 × 客单价 × 使用量 × 留存——迄今的增长由哪个因子驱动、下一个
   5-10 倍必须由哪个因子驱动，以及交接的证据。
5. 需求信号的两面：把最强的需求信号从两面论证——诚实的牛市解读与
   诚实的熊市解读，然后说明证据偏向哪一边（"The pipeline is valuable
   evidence of demand. It is not revenue."）。
6. 销售可复制性：收入中创始人亲自售出与销售代表售出各占多少、最近
   一批销售代表的爬坡时间，以及对"这一销售模式能否靠资金放大"的
   结论。

本章以其已钉定的评分卡句收尾——针对 商业模式与单位经济 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: competition_moat
```yaml
id: competition_moat
scorecard_dimensions:
- industry_position
- moat
en_title: Competition & Moat
zh_title: 竞争格局与护城河
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?competition\s*(?:&|and)\s*moat\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?(?:竞争格局与护城河|竞争与护城河|竞争格局)\s*[:：]?\s*$
components:
- competitive_analysis
- replacement_coexistence
- moat
floor: {}
pass_affinity:
- competitive_position
title_word_aliases:
- competition and moat
subsections:
- en: Industry map
  zh: 产业地图
- en: Competitor comparison
  zh: 竞争对比
- en: Replacement or coexistence
  zh: 替代还是共存
- en: Moat audit
  zh: 护城河审计
- en: The fast-follower question
  zh: 快速跟随者问题
- en: Number one — now and in five years
  zh: 现在与五年后的第一名
```

900-1,100 词。谁会赢，以及优势能否在公司引起注意之后依然存续。各小节
内容：

1. 产业地图：上游 → 公司 → 下游，利润池现在在哪里、成熟后在哪里。
2. 竞争对比：带 `component: "competitive_analysis"` 的 "Competitive
   Analysis" 表：目标公司排第一，然后是 3-5 家具名竞争对手。列（按
   本阶段的披露程度精简）：产品/服务 | 规模/融资 | 增长 | 标杆客户 |
   核心优势。稀疏行遵循缺失数据规则。然后是图表位
   `chart_competitor_scale`：一个 `chart` 块（建议 bar；x = 表中各
   公司，目标公司在前；y = 所述规模指标），仅由已披露数字构建，后接
   一句关于差距的话。序列未披露时不出图：使用图表省略后备句。
3. 替代还是共存：带 `component: "replacement_coexistence"` 的论述：
   替代还是共存，逐个品类分析，并说明各自对天花板的含义。
4. 护城河审计：带 `component: "moat"` 的 "Moat Audit" 表——始终全部
   8 行：技术 | 数据 | 分销 | 生态 | 转换成本 | 网络效应 | 品牌 |
   规模经济。列：强度（Strong / Moderate / Weak / Too early / None）|
   证据 | 趋势（Widening / Stable / Narrowing）。在这一阶段，
   "Too early" 是诚实的回答；猜测不是。
5. 快速跟随者问题：当这一品类被验证后，什么能阻止一个资金更充足的
   快速跟随者——从审计表的各行中得出答案。
6. 现在与五年后的第一名：今天谁领先、3-5 年后最可能谁领先、为什么。
   以一句话答案开头；结尾重申结论。

本章以其已钉定的评分卡句收尾——每个维度一句，针对 行业地位、护城河 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: financial_analysis
```yaml
id: financial_analysis
scorecard_dimensions:
- revenue_growth_quality
en_title: Financial Analysis
zh_title: 财务分析
parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?financial\s+analysis\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?财务分析\s*[:：]?\s*$
components:
- revenue
- growth_bridge
floor: {}
pass_affinity:
- numbers_integrity
- growth_bridge
title_word_aliases: []
subsections:
- en: Financial history
  zh: 历史业绩
- en: Forecast
  zh: 业绩预测
- en: Growth quality
  zh: 增长质量
- en: Revenue authenticity
  zh: 收入真实性
- en: Healthier or hungrier
  zh: 增长更健康还是更烧钱
```

900-1,200 词。增长是否真实，以及每新增一美元增长的代价是多少。各小节
内容：

1. 历史业绩：带 `component: "revenue"`、标题为 "Revenue Picture" 的
   "Financial History" 表：每一个已披露年度加年初至今——收入 | 增长 |
   毛利率 | 运营费用 | 烧钱 | 现金。缺失年度保留行。
2. 业绩预测："Forecast" 表（未来 3 年，每年一行，"Key assumption"
   列指明每年数字所依赖的假设；未钉定、未披露的单元格遵循缺失数据
   规则）。然后是图表位 `chart_revenue_trajectory`：一个 `chart` 块
   （建议 line；x = 各财年，先历史后预测；一个序列 "Revenue"），仅由
   各表已披露或已钉定的数字构建，后接一句关于走势形态的话，并指明
   实际值在哪里结束、预测从哪里开始。序列未披露时不出图：使用图表
   省略后备句。以带后果测算的预测可信度段落收尾：预测隐含的轨迹，
   对照公司自身的历史以及同等规模下最佳的已披露可比公司。
3. 增长质量：带 `component: "growth_bridge"` 的 "Growth Quality" 表
   ——固定行，本阶段烧钱效率优先：烧钱倍数 | 每烧 1 美元带来的净新增
   ARR | 40 法则 | 内生与并购 | 价格与数量拆分 | 现金转化与应收账款。
   列：数值 | 解读。
4. 收入真实性：补贴、一次性收入、关联方收入、审计状态——已核查与
   无法核查的都要写明。
5. 增长更健康还是更烧钱：新增收入是变得更便宜还是更昂贵，以及这对
   公司还需要多少轮融资意味着什么。以一句话答案开头；结尾重申结论。

本章以其已钉定的评分卡句收尾——针对 收入增长与质量 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: valuation_returns_exit
```yaml
id: valuation_returns_exit
scorecard_dimensions:
- valuation
- exit_certainty
en_title: Valuation, Returns & Exit
zh_title: 估值、回报与退出
parity_en: ^\s*(?:(?:vii|7)[\.\、]\s*)?valuation,?\s*returns?\s*(?:&|and)\s*exit\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vii|7|七)[\.\、]\s*)?(?:估值、回报与退出|估值与回报|估值、回报测算与退出)\s*[:：]?\s*$
components:
- time_base_integrity
- scenario_analysis
floor:
  require_valuation_refs: true
pass_affinity:
- numbers_integrity
- valuation_exit
title_word_aliases:
- valuation, returns and exit
- valuation and returns
role: valuation
subsections:
- en: Comparables
  zh: 可比公司
- en: Valuation methods
  zh: 估值方法
- en: Time-base integrity
  zh: 估值时点核查
- en: What is priced in
  zh: 当前价格已经包含了什么
- en: The case for each end
  zh: 区间两端的论证
- en: Scenario analysis & return decomposition
  zh: 情景分析与回报分解
- en: The exit horizon
  zh: 退出窗口
- en: Milestone timeline
  zh: 里程碑时间线
```

1,100-1,400 词。价格预设了什么、在每一种情形下这笔投资回报多少、钱如何
收回。各小节内容：

1. 可比公司："Comparables" 表——4-6 家已披露的可比公司，采用增长
   调整后的倍数，目标公司列在最前。然后是图表位
   `chart_comps_multiples`：一个 `chart` 块（建议 bar；x = 表中各
   公司，目标公司在前；y = 收入倍数），仅由已披露数字构建，后接一句
   定位入场倍数的话。倍数未披露时不出图：使用图表省略后备句。
2. 估值方法："Valuation Methods" 表——始终 3 个方法行（可比公司法 |
   可比交易法 | DCF / 盈利能力法），每行含 结果或区间 | 依据 | 为何
   可信或不可信；无法运行的方法在其行内说明原因。最后一行：本备忘录
   得出的合理估值区间。
3. 估值时点核查：带 `component: "time_base_integrity"` 的 "Time-Base
   Integrity" 表：涉及的各个估值标记、其日期、新鲜还是过时。
4. 当前价格已经包含了什么：把入场倍数翻译成买方已经在为什么付费，
   展示算式。
5. 区间两端的论证：成对的正方/反方段落，带明确的子标题 "Why this
   merits $X" 与 "Why the cap is $Y"——$X 是合理估值区间的高端（公司
   配得上它的最有力的诚实论证），$Y 是低端（价值止步于此的最有力的
   诚实论证）。
6. 情景分析与回报分解：带 `component: "scenario_analysis"` 的
   "Scenario Analysis" 表：行为 熊市 | 基准 | 牛市，列为 退出年份 |
   退出年收入 | 退出倍数 | 退出估值 | 稀释假设 | 归属本轮的价值 |
   毛回报倍数(MOIC) | 内部收益率(IRR)——每个数值单元格都精确重复已
   钉定的情景数字；未钉定的单元格遵循缺失数据规则。然后是回报分解
   段落（增长贡献的倍数与估值倍数贡献的倍数，写明交叉点），以及图表位
   `chart_return_scenarios`：一个 `chart` 块（bar；x = 熊市 / 基准 /
   牛市；y = 毛回报倍数(MOIC)），由已钉定的 MOIC 构建，附一句解读。
   然后是"必须成立什么"：当共享事实表带有 Python 计算的价格问题行 ——
   在这个价格下收回本金、达到基金门槛和取得 3 倍所需的退出价值与退出年
   收入；保本入场价；各情景相对最新披露收入所隐含的增速；退出推迟一两年
   时的基准情形 IRR；有出资额备案时 BSH 各情景的所得 —— 逐字陈述每一行
   并附其 [C#]，再用一句话说明"所需"与基准情形假设之间的差距意味着什么：
   一个基准情形若已经要求超出公司已证明的水平，那它只是贴着基准标签的
   牛市情形。事实表没有这些行时，一字不写 —— 绝不在此自行计算。
7. 退出窗口——取代后期的退出地图，因为成长期的退出是时间窗口而不是
   日历：合理的退出窗口、届时必须成立的条件（规模、利润率、治理）、
   具名的潜在收购方及各自的约束，以及至少一种非溢价结果的后果测算。
8. 里程碑时间线："Milestone Timeline" 表——未来 12-36 个月内 3-6 个
   带日期的里程碑，每个都写明它推动的指标，以及达成或错过对投资论点
   意味着什么。

本章以其已钉定的评分卡句收尾——每个维度一句，针对 估值、退出确定性 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: investment_risk
```yaml
id: investment_risk
scorecard_dimensions:
- risk_reward
en_title: Investment Risk
zh_title: 风险分析
parity_en: ^\s*(?:(?:viii|8)[\.\、]\s*)?investment\s+risks?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:viii|8|八)[\.\、]\s*)?(?:风险分析|投资风险)\s*[:：]?\s*$
components:
- risk_register
- disconfirming_evidence
floor:
  bullets_or_prose: true
pass_affinity:
- alternative_explanations
- competitive_position
title_word_aliases:
- investment risk
- risk analysis
role: risk
subsections:
- en: The center of gravity
  zh: 风险重心
- en: Risk cards
  zh: 风险卡片
- en: Disconfirming evidence
  zh: 反面证据
- en: Downside scenario & verdict
  zh: 下行情景与风险结论
```

900-1,200 词。各小节内容：

1. 风险重心：一段话，指出哪一个单一风险承载着投资论点。
2. 风险卡片：4-6 张按风险逐一展开的卡片，按评分从高到低排序，严格
   使用已钉定的风险列表与评分。卡片 = 三级标题（已钉定的总结——一个
   带限定动词的完整结论句，绝不是主题标签）+ 带
   `component: "risk_register"` 的 key_value 表。卡片格式见指令中的
   风险卡合约：按合约规定的固定行和顺序填写，其中"为什么重要"写出事实 →
   失败模式 → 经济后果，可量化时给出算式。
3. 反面证据：带 `component: "disconfirming_evidence"` 的论述：反对
   投资建议的最有力事实，每条用一句话权衡。
4. 下行情景与风险结论：把熊市情形叙述为一连串事件，最终落到已钉定的
   熊市数字，然后是收尾的风险/收益结论段落。

本章以其已钉定的评分卡句收尾——针对 风险收益比 的 "This dimension scores N of M."——从共享事实表逐字重复（钉定回显检查（pin-echo gate）会拒绝没有这句话的章节，而重新生成的章节最常丢掉它）。

## section: investment_decision
```yaml
id: investment_decision
en_title: Investment Decision
zh_title: 最终投资决定
parity_en: ^\s*(?:(?:ix|9)[\.\、]\s*)?(?:final\s+)?investment\s+decision\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ix|9|九)[\.\、]\s*)?(?:最终投资决定|投资决定|投资结论)\s*[:：]?\s*$
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
- en: Demonstrated vs unresolved
  zh: 已证明与未解决
- en: Recommendation
  zh: 投资建议
- en: Monitoring & triggers
  zh: 投后监控与触发条件
```

700-900 词。各小节内容：

1. 六个关键问题：带 `component: "evidence_thresholds"`、标题为
   "Evidence Thresholds — The Six Questions" 的 "Six Questions" 表
   ——固定行，每行以 Yes / No / Qualified 作答并附一行依据：市场是否
   大到值得关注？| 公司是否有证据支持地位列前 1-3 名？| 护城河能否在
   被注意到之后存续？| 公司能否从当前再增长 5-10 倍？| 价格是否留有
   风险投资级别的回报？| 我们能否把钱拿回来？每一个 No 或 Qualified
   都配一段"什么会翻转它"的说明。
2. 评分卡："Scorecard" 表——9 个固定维度，采用成长期权重：
   市场空间与增速 15 | 行业地位 12 | 护城河 13 |
   收入增长与质量 15 | 商业模式与单位经济 12 | 团队与治理 13 | 估值 10 |
   退出确定性 5 | 风险收益比 5。列为 得分 | 理由（一行）。已钉定的
   评分卡精确重复；以合计行与门槛句收尾（80 分以上投资 / 70-79 分
   观察 / 70 分以下放弃）。
3. 已证明与未解决：等长的两个列表（各 3-5 条）"What is
   demonstrated" / "What remains unresolved"，每条一句话，带一个数字
   或一个缺口。
4. 投资建议：带 `component: "investment_decision"` 的投资建议提示框：
   已钉定的投资建议句原文、入场条件、已钉定的基准情形结果、持有期、
   退出路径、基金占位符原文。随后是一段带 `component: "disclosures"`
   的一行法律披露。已钉定的 `decision_history_sentence` 作为历史原文
   重述，紧邻提示框（绝不放在提示框内）。
   当共享事实表钉定了 `prior_view_sentence`（BSH 上一份备忘录对本公司
   的结论）时，同样在提示框旁逐字重述，随后用一句话说明此后发生了什么
   变化，或为何维持原判。它是历史而非证据：不得引用上一份备忘录中的
   任何数字。
5. 投后监控与触发条件："Monitoring Indicators" 表（投后监控）：4-6
   行——指标 | 当前值 | 触发阈值 | 应对措施。当结论为观察/放弃时，
   标题改为 "What changes the verdict"。
