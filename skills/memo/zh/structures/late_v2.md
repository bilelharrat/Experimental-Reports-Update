---
en_sha256: 8a90cd15f4b0e5d06db6da0143b8c338e6950d016cac05227590cd3e3122b050
---
---
stage: late
version: 2
scorecard:
  market_size_growth: 15
  industry_position: 15
  moat: 15
  revenue_growth_quality: 15
  business_model_ue: 10
  team_governance: 10
  valuation: 10
  exit_certainty: 5
  risk_reward: 5
lint_extra_titles:
- investment decision
- investment decision / closing view
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
  parity_en: ^\s*(?:(?:xiii|13)[\.\、]\s*)?sources?(?:,\s*source\s+classes,\s*and\s+(?:fact\s+reference\s+index|disclosures))?\s*[:：]?\s*$
  parity_zh: ^\s*(?:(?:xiii|13|十三)[\.\、]\s*)?(?:来源、来源类别与事实索引|来源与事实索引|来源)\s*[:：]?\s*$
- id: validation_log
  en_title: 'Appendix: Source Treatment And Assumptions'
  zh_title: 附录：来源处理与假设
  numbered: false
---

后期结构模板 v2 —— 由 docs/Report-Structure.md 合并而成的 IC 结构（V1
研究框架 + 评分卡，V2 PE IC 备忘录），以"解释性、结论先行"的文风写作。
十二个固定章节；每次运行都渲染相同的子章节、相同的表格、相同的图表和
相同的具名段落，缺失数据要明确写明缺失（全局的数据诚实、导航与图表
规则随共享上下文一同下发）。每个章节都按其声明的编号子章节组织 ——
读者从标题得知一段文字讲的是什么，而不是靠段落自己解释自己。

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

700-900 词。这一章节是 IC 成员在其他什么都不读时也会读的那份备忘录，
它唯一的任务是说清什么最重要。本章节不含任何表格 —— 它需要的每个数字
都放在一句解释该数字的句子里（Deal Snapshot 与 Key Metrics Snapshot
两张表放在 Company Overview 章节）。各子章节内容：

1. Company profile（项目基本概况）：一句大白话说明公司做什么、为谁做；
   一句说明行业与地域；一句将其定位在后期阶段阶梯上（PMF → Scale-up →
   Category leader → Pre-IPO → Public candidate）。正文不超过 80 词。
2. The round（本轮融资方案）：本轮提供的是什么 —— 轮次、工具、规模、
   价格、隐含持股比例 —— 以及这个价格已经预设了什么。在同一句话里解读
   入场倍数（"...priced at ~NNx, which already includes X of the
   success case"）。仅用正文；每个数字在出现处即被解读。
3. Investment highlights（核心投资亮点）：以共享事实表中已钉定的案例
   概述句开篇，用公司名替换 "The case" —— 一小段话说明哪些维度支撑
   本案、哪些维度薄弱，并附各自分数（"Anthropic's case rests on market
   size and growth (14/15), industry position (13/15) and revenue
   growth and quality (12/15); the weak points are business model and
   unit economics (5/10) and valuation (6/10)."），之后可选地加一句
   说明这一格局意味着什么。然后是一个 `bullets` 块，带 `"component":
   "investment_highlights"`，且恰好三项，每项对应一条已钉定的亮点，
   按钉定顺序排列。每项以已钉定的标题原文开头（纯文本，不要写星号或
   markdown；渲染器会把它加粗，读者在第一个句号之前就得到判断），随后
   是已钉定的证据句。带数字的
   证据句要在读者看到数字之前先说明该数字衡量什么、来自哪里 —— 某个
   具名来源，或"我们自己的估算"并附其输入项；绝不能只写 "a
   $450-675B market" 却不说是谁、用什么方法测算的。任何亮点都不得
   建立在未说明推导过程的衍生数字之上。这里没有任何新内容：标题与
   证据都来自共享事实表，逐字重复。
4. Key risks（核心风险提示）：一个 `bullets` 块，带 `"component":
   "key_risks"`，恰好三项 —— 评分最高的三条已钉定风险，按钉定顺序。
   每项写作 "<Area label> — <pinned summary verbatim>. Impact: <pinned
   impact verbatim>. (N/10, <likelihood> likelihood)"，例如
   "Valuation & exit — The entry price already assumes the 2028 plan
   is delivered. Impact: the base case returns 0.9x, a loss even if
   the plan lands. (9/10, High likelihood)"。领域标签取共享事实表归档
   该风险所用的标签。不加新数字、不改写概述、不做算术链 —— 风险章节的
   卡片会完整解释每条风险。
5. Recommendation（投资建议）：一个结论提示框 —— 逐字按共享事实表钉定的
   投资建议句陈述，然后是入场估值、合理估值区间、来自已钉定情景的基准
   情形结果（回报倍数(MOIC) 与内部收益率(IRR)）、持有期，以及基金
   占位符（"Proposed amount: [TO BE DETERMINED BY IC]"、
   "Allocation: [TO BE DETERMINED BY IC]"）。当共享事实表带有结论等级
   和评分卡总分时，提示框以 "{tier} — {total}/100" 开头。当共享事实表
   钉定了 `decision_history_sentence` 时，在提示框之后逐字陈述它，
   作为事实性历史 —— 是 BSH 此前的决定，绝不是本备忘录自己的结论。

## section: company_overview
```yaml
id: company_overview
en_title: Company Overview & Stage
zh_title: 公司概况与发展阶段
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?company\s+overview(?:\s*(?:&|and)\s*stage)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:公司概况与发展阶段|公司概览|公司概况|项目简介)\s*[:：]?\s*$
components:
- key_metrics_snapshot
- deal_terms
floor: {}
pass_affinity:
- adoption_distribution
title_word_aliases:
- company overview and stage
- company overview
subsections:
- en: Company facts & key metrics
  zh: 公司基本情况与关键指标
- en: Funding history & this round
  zh: 融资历史与本轮方案
- en: Development milestones
  zh: 发展历程
- en: Proven and unproven
  zh: 已验证与未验证
```

900-1,200 词。公司是什么、如何走到今天，以及 —— 本章节的要点 ——
关于它的哪些说法已被证明、哪些仍是押注。各子章节内容：

1. Company facts & key metrics（公司基本情况与关键指标）：一张
   "Company Facts" key_value 表（Founded | Headquarters | Headcount |
   Founders & CEO | Ownership snapshot | What it sells，各一行），然后是
   带 `component: "key_metrics_snapshot"` 的 "Key Metrics Snapshot"
   表：7 行 —— Revenue/ARR | Growth rate | Gross margin | Burn or FCF |
   Cash runway | Last/current valuation | Implied multiple —— 列为最近
   两个实际年度/期间，外加一列 +3y，该列单元格只能填写已钉定基准情景
   所陈述的数字（否则写 "Not modeled — no pinned basis"）。用一小段话
   把两张表合起来解读：这些数字描述的是一家什么样的公司。
2. Funding history & this round（融资历史与本轮方案）：一张 "Funding
   History" 表（每一轮已披露的融资 —— Date | Round | Amount |
   Post-money | Lead investors | Price change vs prior round；未披露的
   轮次保留其行），然后是带 `component: "deal_terms"` 的 "Deal
   Snapshot" key_value 表，恰好这 10 行：Round | Instrument | Raise
   size | Pre-money | Post-money | Implied stake | Primary / secondary
   split | Use of proceeds | Co-investors | Expected close。缺失单元格
   遵循缺失数据规则（"Not disclosed — <implication>"）。以一段对表格
   的简短解读收尾，开头用一句大白话给出结论 —— 历轮估值是支撑还是
   削弱入场价格，这对本交易是利好还是利空 —— 然后给出证明它的两三个
   数字。只是复述轮次和价格而不说它们意味着什么的段落，不符合文风
   要求。
3. Development milestones（发展历程）：2-3 个短段落，把公司的发展讲成
   因果关系（"X worked, so Y followed"），而不是日期清单。
4. Proven and unproven（已验证与未验证）：说明公司在后期阶段阶梯
   （PMF → Scale-up → Category leader → Pre-IPO → Public candidate）上的
   位置，呼应 `stage` 钉定项，然后列出证据已证明的内容和仍停留在断言
   层面的内容。每项一句话，附其支撑数据或缺失数据。以一句结论收尾：
   本轮定价所对应的阶段，是否与证据支持的阶段相符。

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
- market & industry
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

900-1,100 词。市场能否撑起估值，以及什么可能封顶。各子章节内容：

1. Market definition & value chain（赛道定义与产业链位置）：公司实际
   参与竞争的是哪个市场（而非它营销时用的最大标签），它在产业链中处于
   什么位置，其上游和下游分别由谁攫取价值。
2. Market size（市场空间）：首先是 "Market estimates" 表 —— 调研找到的
   每个估算各占一行，只要存在就绝不少于三行：各家咨询机构（Gartner、
   IDC、Stratpace、Technavio、MarketsandMarkets、Grand View……）、公司
   自己宣传的 TAM、银行或分析师的测算，以及最后一行本备忘录自己的
   推导；列为 Source | What it counts (definition) | Value | Year | How
   it was built。任何估算都不因与其他估算不一致而被剔除 —— 一个 $23B
   的"基础模型支出"数字和一个 $30T 的"劳动力替代"说法可以在不同定义
   下同时成立，表格要展示各自采用的定义。随后是一段解读，开头说明
   本备忘录采用的区间以及为什么该定义对这家公司是正确的，然后用平实
   的语言解释各估算的分歧（各自计入了什么别人没计入的）。然后是
   "Market Sizing" 表 —— 始终包含 TAM | SAM | SOM 三行，列为
   Definition | Size today | Size at exit year | CAGR | Basis/source，
   其中 Basis/source 要指明它所依据的估算行，或说明本备忘录自己的
   输入项与系数。没有已披露或可推导数字的行遵循缺失数据规则；绝不用
   相邻更大市场的数字顶替。然后是图表槽位 `chart_market_size`：一个
   `chart` 块（grouped_bar；x = TAM / SAM / SOM；一个序列为当前、一个
   序列为退出年份，用实际年份标注），只能用表格中已披露或可推导的
   数字构建，后接一句解读。当序列未披露时，不出图：改写图表省略的
   兜底句。
3. Growth drivers（增长驱动）：每个宣称的驱动因素各给一句主张和一个
   支撑数据。没有支撑数据的驱动因素要点明为假设。
4. The ceiling question（天花板问题）：论证这个市场把公司的企业价值
   封顶在更接近 $20B、$100B 还是 $500B，并说明是哪个假设让它在这些
   区间之间移动。开头给出一句话答案；结尾重申结论。
5. Policy & regulation（政策与监管）—— 绝不能悄悄省略：点名约束或补贴
   这门生意的监管制度（数据、出口、行业专项、采购）。若均不适用，写出
   这句话 "No regulatory regime materially constrains this business
   today"，并说明这为什么可能改变。

本章节以其已钉定的评分卡句收尾 —— 针对 市场空间与增速 的 "This dimension scores N of M." —— 逐字重复共享事实表中的内容（缺少它时，钉定回显门禁会拒绝本章节，而重新生成的章节最常丢掉这句话）。

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
- business model and unit economics
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
```

1,100-1,400 词。客户为什么付费，收入机器如何运转，以及投入一美元是否
产出多于一美元。各子章节内容：

1. Why customers pay（客户为什么付费）：买方、问题、他们否则会采用的
   替代方案，以及从客户角度看的经济账 —— 附已披露的最强证明点。
2. Revenue model（收入模式）：一张 "Revenue Model" key_value 表 ——
   Revenue streams | Pricing model | Contract length & terms | Revenue
   recognition character (recurring / committed / usage / project)。
3. Key operating metrics（关键运营指标）：带 `component:
   "key_operating_metrics"` 的 "Key Operating Metrics" 表 —— 恰好这
   8 行：Customer count | Largest-customer penetration | Top-10 revenue
   concentration | Net revenue retention | Gross retention | CAC
   payback | LTV/CAC or magic number | ARR per employee。列为：Value |
   As of | Benchmark | Reading。Reading 单元格是一个结论片段（"healthy
   for stage"、"below the bar because ..."），绝不是数字的复述。
4. Revenue quality（收入质量）："Revenue Quality Split" 表（行为经常性、
   已承诺、项目制与集中收入，附各自占比及所携带的风险），然后是收入
   等式段落：逐项走一遍 收入 = 客户数 × 客单价 × 使用量 × 留存 ——
   迄今的增长由哪个因子驱动，下一阶段必须由哪个因子驱动，以及有什么
   证据支持这一交接。
5. Demand signals — both ways（需求信号的两面）：最强的需求信号（管道、
   在手订单、等候名单 —— 公司主打哪个就用哪个）正反两面论证：诚实的
   看多解读和诚实的看空解读，然后说明证据倾向于哪种解读。要达到的文风
   是 "The pipeline is valuable evidence of demand. It is not
   revenue."。以在手订单/已承诺收入的陈述收尾：已披露的订单、预付款和
   背景调查；未披露时用缺失数据句。

本章节以其已钉定的评分卡句收尾 —— 针对 商业模式与单位经济 的 "This dimension scores N of M." —— 逐字重复共享事实表中的内容（缺少它时，钉定回显门禁会拒绝本章节，而重新生成的章节最常丢掉这句话）。

## section: competitive_landscape
```yaml
id: competitive_landscape
scorecard_dimensions:
- industry_position
en_title: Competitive Landscape
zh_title: 竞争格局
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?competitive\s+landscape\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?竞争格局\s*[:：]?\s*$
components:
- competitive_analysis
- replacement_coexistence
floor: {}
pass_affinity:
- competitive_position
title_word_aliases: []
subsections:
- en: Industry map
  zh: 产业地图
- en: Competitor comparison
  zh: 竞争对比
- en: Replacement or coexistence
  zh: 替代还是共存
- en: Number one — now and in five years
  zh: 现在与五年后的第一名
```

900-1,200 词。谁赢得这个市场，依据什么证据。各子章节内容：

1. Industry map（产业地图）：上游供应商 → 公司 → 下游渠道/客户，以及
   在这条链上利润池今天在哪里、市场成熟后又在哪里。
2. Competitor comparison（竞争对比）：带 `component:
   "competitive_analysis"` 的 "Competitive Analysis" 表 —— 目标公司排
   第一，然后是 3-6 家具名竞争对手。列为：Offering | Revenue/scale |
   Growth | Gross margin | Flagship customers | Last valuation | Core
   advantage。未披露的竞争对手单元格遵循缺失数据规则 —— 稀疏的竞争
   对手行本身就是市场不透明的证据。然后是图表槽位
   `chart_competitor_scale`：一个 `chart` 块（bar；x = 表中的公司，
   目标公司在前；y = 收入或所述的规模指标），只能用表格中已披露的数字
   构建，后接一句说明差距意味着什么。当序列未披露时，不出图：写图表
   省略的兜底句。
3. Replacement or coexistence（替代还是共存）：带 `component:
   "replacement_coexistence"` 的论述：公司是替代现有技术栈还是与之
   共存，逐品类回答 —— 以及每种答案对增长天花板意味着什么。
4. Number one — now and in five years（现在与五年后的第一名）：三个明确
   的回答 —— 今天谁领先（附数据）、3-5 年后最可能谁领先，以及为什么
   市场结构决定了这一点。若公司不是预期的领先者，说明在这个价格上
   跟随领先者值多少。

本章节以其已钉定的评分卡句收尾 —— 针对 行业地位 的 "This dimension scores N of M." —— 逐字重复共享事实表中的内容（缺少它时，钉定回显门禁会拒绝本章节，而重新生成的章节最常丢掉这句话）。

## section: moat
```yaml
id: moat
scorecard_dimensions:
- moat
en_title: Moat & Defensibility
zh_title: 护城河
parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?moat\s*(?:(?:&|and)\s*defensibility)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?(?:护城河|护城河与壁垒)\s*[:：]?\s*$
components:
- moat
floor: {}
pass_affinity:
- competitive_position
title_word_aliases:
- moat and defensibility
- moat
subsections:
- en: Moat audit
  zh: 护城河审计
- en: The $5B question
  zh: 50亿美元问题
- en: Widening or narrowing
  zh: 变宽还是变窄
```

700-900 词。优势能否在成功之后存续 —— 因为到了 $5B+ 的规模，每个在位者
和资金充足的模仿者都会到来。各子章节内容：

1. Moat audit（护城河审计）：带 `component: "moat"` 的 "Moat Audit"
   表 —— 始终包含全部 8 个固定行：Technology | Data | Distribution |
   Ecosystem | Switching cost | Network effect | Brand | Scale
   economics。列为：Strength (Strong / Moderate / Weak / None) |
   Evidence | Trajectory (Widening / Stable / Narrowing)。没有证据的
   维度写 "None — no evidence"，绝不留空，也绝不猜测。
2. The $5B question（50亿美元问题）：假设公司成功达到 $5B+ 的结果 ——
   是什么阻止那时显而易见的竞争对手夺走利润？从审计表的各行作答，
   而不是用形容词。
3. Widening or narrowing（变宽还是变窄）：综合权衡 Trajectory 列，明确
   讨论底层技术基础的商品化，并以一句话收尾：护城河在变宽/稳定/变窄，
   以及这对退出倍数假设意味着什么。

本章节以其已钉定的评分卡句收尾 —— 针对 护城河 的 "This dimension scores N of M." —— 逐字重复共享事实表中的内容（缺少它时，钉定回显门禁会拒绝本章节，而重新生成的章节最常丢掉这句话）。

## section: financial_analysis
```yaml
id: financial_analysis
scorecard_dimensions:
- revenue_growth_quality
en_title: Financial Analysis
zh_title: 财务分析
parity_en: ^\s*(?:(?:vii|7)[\.\、]\s*)?financial\s+analysis\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vii|7|七)[\.\、]\s*)?财务分析\s*[:：]?\s*$
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

1,000-1,300 词。报告的增长是否真实，预测是否值得相信。各子章节内容：

1. Financial history（历史业绩）：带 `component: "revenue"` 的
   "Financial History" 表，标题为 "Revenue Picture"：至少 3 个财年，
   外加已披露的年初至今数据 —— Revenue | Growth | Gross margin | Opex |
   EBITDA/net | Burn | Cash。缺失的年份保留其行。
2. Forecast（业绩预测）："Forecast" 表（+3 至 +5 年，每年一行，附
   "Key assumption" 列，指明该年数字最依赖的那一个假设；没有已披露或
   已钉定依据的单元格遵循缺失数据规则）。然后是图表槽位
   `chart_revenue_trajectory`：一个 `chart` 块（建议 line；x = 各财年，
   先历史后预测；一个序列 "Revenue"），只能用表格中已披露或已钉定的
   数字构建，后接一句关于形态的话（加速、减速、历史平坦时的曲棍球杆），
   并点明实际值在哪里结束、预测从哪里开始。当序列未披露时，不出图：
   写图表省略的兜底句。以预测可信度段落收尾：把预测隐含的轨迹与公司
   自身历史以及已披露同行在相同规模时的轨迹作比较；对差距做后果算术
   （"the forecast asks for NNx in N years; the best disclosed
   comparable did MMx"）。
3. Growth quality（增长质量）：带 `component: "growth_bridge"` 的
   "Growth Quality" 表：固定行 —— Rule of 40 | Organic vs acquired
   growth | Pricing vs volume split | Incremental gross profit vs
   incremental opex | Burn multiple | Cash conversion & receivables。
   列为：Value | Reading。
4. Revenue authenticity（收入真实性）：补贴、一次性项目、关联方或渠道
   压货收入、审计状态。说明核查了什么、什么无法核查。
5. Healthier or hungrier（增长更健康还是更烧钱）：每一美元的增量收入是
   变得更便宜还是更昂贵，以及这对融资风险意味着什么。开头给出一句话
   答案；结尾重申结论。

本章节以其已钉定的评分卡句收尾 —— 针对 收入增长与质量 的 "This dimension scores N of M." —— 逐字重复共享事实表中的内容（缺少它时，钉定回显门禁会拒绝本章节，而重新生成的章节最常丢掉这句话）。

## section: team_governance
```yaml
id: team_governance
scorecard_dimensions:
- team_governance
en_title: Team & Governance
zh_title: 团队与治理
parity_en: ^\s*(?:(?:viii|8)[\.\、]\s*)?team\s*(?:&|and)\s*governance\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:viii|8|八)[\.\、]\s*)?(?:团队与治理|管理层与治理|团队与管理层)\s*[:：]?\s*$
components:
- board
floor: {}
pass_affinity:
- team_governance
title_word_aliases:
- team and governance
subsections:
- en: Leadership
  zh: 管理团队
- en: Board & ownership
  zh: 董事会与股权治理
- en: Founder-market fit
  zh: 创始人与赛道匹配
- en: Founder dependence
  zh: 创始人依赖
- en: Public-company readiness
  zh: 上市公司准备度
```

700-950 词。这个团队能否把公司经营到价格所预设的水平，以及若不能，
股东能否纠偏。各子章节内容：

1. Leadership（管理团队）："Leadership" 表 —— CEO 及 3-6 名关键高管 ——
   Role | Prior record (one line of facts) | Strength or gap (a verdict
   fragment)。空缺的关键席位（尤其是 Pre-IPO 阶段的 CFO）单独成行：
   "Vacant — <consequence>"。
2. Board & ownership（董事会与股权治理）：带 `component: "board"` 的
   "Board of Directors" 表（成员、所属机构与战略价值），然后是一个
   "Ownership & Governance" key_value 块 —— Founder control (votes vs
   economics) | ESOP size | Investor roster | Protective provisions |
   Public-company readiness（该单元格是一个结论：Ready / 12-18 months
   of work / Not close）。
3. Founder-market fit（创始人与赛道匹配）：开头给出一句话答案 —— 这些
   创始人是否可证明是解决这个问题的合适人选 —— 然后给出证明。对每位
   重要的创始人：他们此前建立或经营过什么、且正是这门生意实际需要的
   （附日期的已核实事实，与自述简历分开），他们的履历中哪些对应下一
   阶段最难的工作，以及履历在哪些方面沉默。在另一学科享有盛誉的背景
   要如实说明就是那样。以结论句收尾：匹配已由过往工作证明、匹配仅为
   断言尚未证明，或匹配不存在。
4. Founder dependence（创始人依赖）：若创始人离开或未能随规模成长，
   什么会出问题，以及有什么证据表明组织能够脱离他们运转。
5. Public-company readiness（上市公司准备度）：审计历史、财务报告节奏、
   缺位的高管、关联方敞口 —— 每项都以事实加后果的方式陈述，而不是
   清单。

本章节以其已钉定的评分卡句收尾 —— 针对 团队与治理 的 "This dimension scores N of M." —— 逐字重复共享事实表中的内容（缺少它时，钉定回显门禁会拒绝本章节，而重新生成的章节最常丢掉这句话）。

## section: valuation
```yaml
id: valuation
scorecard_dimensions:
- valuation
en_title: Valuation Analysis
zh_title: 估值分析
parity_en: ^\s*(?:(?:ix|9)[\.\、]\s*)?valuation(?:\s+analysis)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ix|9|九)[\.\、]\s*)?(?:估值分析|估值)\s*[:：]?\s*$
components:
- time_base_integrity
floor:
  require_valuation_refs: true
pass_affinity:
- numbers_integrity
- valuation_exit
title_word_aliases:
- valuation analysis
- valuation
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
```

900-1,100 词。价格已经预设了什么，以及基于证据公司值多少。各子章节
内容：

1. Comparables（可比公司）："Comparables" 表 —— 4-8 家已披露的可比
   公司，附增长调整后倍数，目标公司列在第一行以示突出。列为：Company |
   Revenue | Growth | Multiple | Growth-adjusted multiple | Note。然后
   是图表槽位 `chart_comps_multiples`：一个 `chart` 块（建议 bar；x =
   表中的公司，目标公司在前；y = 收入倍数），只能用表格中已披露的数字
   构建，后接一句把目标公司的入场倍数放在这组公司中定位。当倍数未
   披露时，不出图：写图表省略的兜底句。
2. Valuation methods（估值方法）："Valuation Methods" 表 —— 始终包含
   这 3 个方法行：Comparable companies | Precedent transactions | DCF /
   earnings power。列为：Result or range | Basis | Why trusted or not。
   无法运行的方法在其行内说明原因（"No positive FCF within the
   forecast — DCF not computable"），绝不消失。末行："Fair value
   range"，陈述本备忘录得出的合理估值区间。
3. Time-base integrity（估值时点核查）：带 `component:
   "time_base_integrity"` 的 "Time-Base Integrity" 表：在用的各个估值
   标记（上一轮定价、本轮、任何二级交易）、各自的日期，以及每个标记是
   新鲜还是陈旧。
4. What is priced in（当前价格已经包含了什么）：把入场倍数换算为买方
   已经在为之付费的增长和利润率，展示算术过程。
5. The case for each end（区间两端的论证）：成对的正方/反方段落，带
   明确的子标题 "Why this merits $X" 和 "Why the cap is $Y" —— $X 是
   合理估值区间的高端（公司配得上它的最强诚实论证），$Y 是低端（价值
   止步于此的最强诚实论证）—— 各自从上面的表格出发论证。以关于本轮
   动态的正反两面段落收尾：超额认购、内部人支持或陈旧标记 —— 既作为
   验证解读，也作为逆向选择风险解读，然后说明证据倾向于哪种解读。

本章节以其已钉定的评分卡句收尾 —— 针对 估值 的 "This dimension scores N of M." —— 逐字重复共享事实表中的内容（缺少它时，钉定回显门禁会拒绝本章节，而重新生成的章节最常丢掉这句话）。

## section: returns_exit
```yaml
id: returns_exit
scorecard_dimensions:
- exit_certainty
en_title: Return & Exit Analysis
zh_title: 回报测算与退出分析
parity_en: ^\s*(?:(?:x|10)[\.\、]\s*)?returns?\s*(?:&|and)\s*exit(?:\s+analysis)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:x|10|十)[\.\、]\s*)?(?:回报测算与退出分析|回报与退出分析|退出分析)\s*[:：]?\s*$
components:
- scenario_analysis
floor:
  require_valuation_refs: true
pass_affinity:
- numbers_integrity
- growth_bridge
- valuation_exit
title_word_aliases:
- return and exit analysis
- return analysis
- exit analysis
role: valuation
subsections:
- en: Scenario analysis
  zh: 情景分析
- en: Return decomposition
  zh: 回报分解
- en: Exit map
  zh: 退出路径
- en: Catalyst timeline
  zh: 催化剂时间线
- en: Growth or multiple
  zh: 增长还是倍数
```

1,000-1,200 词。这笔投资在每种情形下回报多少，以及钱实际如何回来。
各子章节内容：

1. Scenario analysis（情景分析）：带 `component: "scenario_analysis"`
   的 "Scenario Analysis" 表：行为 bear | base | bull，列为 Exit year |
   Exit-year revenue | Exit multiple | Exit valuation | Dilution
   assumption | Value to this round | Gross MOIC | IRR。每个数字单元格
   都精确重复共享事实表中已钉定的情景数字；钉定项未陈述的单元格遵循
   缺失数据规则。此处不得编造任何新的情景数字。然后是图表槽位
   `chart_return_scenarios`：一个 `chart` 块（建议 bar；x = Bear / Base /
   Bull；y = 以纯数字表示的毛回报倍数(MOIC)），只能用已钉定的 MOIC
   构建，后接其一句话解读。
2. Return decomposition（回报分解）：基准回报中有多少来自收入增长、
   多少来自倍数变化（"NNx from growth × 0.MMx from multiple
   compression = base MOIC"），用一张小表或正文中的算术展示。说明
   交叉点：在什么退出倍数下回报归零。然后是图表槽位
   `chart_return_decomposition`：一个 `chart` 块（建议 bar；x = Growth
   factor / Multiple factor / Base MOIC；y = 这三个因子），来自同一组
   数字，附其一句话解读。当无法从已钉定数字计算分解时，不出图：写
   图表省略的兜底句。
3. Exit map（退出路径）："Exit Map" 表 —— 未来 4 个日历年 × 三条路径
   （IPO / M&A / secondary），每个单元格为 Readiness + Likelihood。
   随后每条路径一段：对照治理章节的结论评估 IPO 准备度；M&A 要点名
   可信的收购方及各自面临的反垄断或战略约束；该公司在二级市场的深度。
4. Catalyst timeline（催化剂时间线）："Catalyst Timeline" 表 —— 未来
   12-36 个月内 3-6 个有日期的催化剂，各附其推动的指标及方向。
5. Growth or multiple（增长还是倍数）：回报更依赖哪一个，以及结果对
   单纯的倍数压缩暴露有多大。至少取一个非溢价结果（熊市情形，或退出
   倍数持平），展示本轮资金在后续稀释之前会怎样，以美元和回报倍数
   (MOIC) 计。开头给出一句话答案；结尾重申结论。

本章节以其已钉定的评分卡句收尾 —— 针对 退出确定性 的 "This dimension scores N of M." —— 逐字重复共享事实表中的内容（缺少它时，钉定回显门禁会拒绝本章节，而重新生成的章节最常丢掉这句话）。

## section: investment_risk
```yaml
id: investment_risk
scorecard_dimensions:
- risk_reward
en_title: Investment Risk
zh_title: 风险分析
parity_en: ^\s*(?:(?:xi|11)[\.\、]\s*)?investment\s+risks?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:xi|11|十一)[\.\、]\s*)?(?:风险分析|投资风险)\s*[:：]?\s*$
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

1,000-1,300 词。真正会扼杀回报的风险，要论证 —— 不是罗列。各子章节
内容：

1. The center of gravity（风险重心）：一段话点明风险画像的重心（哪一个
   单一风险承载着论点）。
2. Risk cards（风险卡片）：4-6 张逐风险卡片，按风险评分从高到低排序，
   严格使用共享事实表钉定的风险清单和评分。每张卡片是一个三级标题加
   一张带 `component: "risk_register"` 的 key_value 表。标题是已钉定
   的概述 —— 一个带有限定动词的完整结论句（"The entry price already
   assumes success — ordinary execution earns nothing"），绝不是
   "Entry Price" 这样的主题标签。卡片行：风险类型（Risk Type）|
   为什么重要（Why it matters：事实 → 失败模式 → 经济后果，可量化时附
   算术）| 跟踪信号（What we watch：可观察的领先指标）| 缓释措施
   （Mitigation：真实的机制 —— 公司行动、交易结构或仓位控制；不存在时
   写："No structural mitigation exists. <consequence>"）| 可能性
   （Likelihood）| 风险评分（Risk Rating）N/10。
3. Disconfirming evidence（反面证据）：带 `component:
   "disconfirming_evidence"` 的论述：与本备忘录投资建议相悖的最强
   事实，公允地陈述，每条附一句话说明它应得多大权重。
4. Downside scenario & verdict（下行情景与风险结论）：把熊市情形叙述为
   一连串事件（哪个风险先触发、它引发什么），以已钉定的熊市数字收尾。
   然后用一小段话把已评分的风险与回报分析加以权衡，以一句结论句结束。

本章节以其已钉定的评分卡句收尾 —— 针对 风险收益比 的 "This dimension scores N of M." —— 逐字重复共享事实表中的内容（缺少它时，钉定回显门禁会拒绝本章节，而重新生成的章节最常丢掉这句话）。

## section: investment_decision
```yaml
id: investment_decision
en_title: Investment Decision
zh_title: 最终投资决定
parity_en: ^\s*(?:(?:xii|12)[\.\、]\s*)?(?:final\s+)?investment\s+decision\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:xii|12|十二)[\.\、]\s*)?(?:最终投资决定|投资决定|投资结论)\s*[:：]?\s*$
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

700-900 词。做出决定的章节。各子章节内容：

1. The six questions（六个关键问题）：带 `component:
   "evidence_thresholds"` 的 "Six Questions" 表，标题为 "Evidence
   Thresholds — The Six Questions" —— 始终包含这些固定行，每行以 Yes /
   No / Qualified 作答并附一行依据：Is the market big enough to
   matter? | Is the company top-1-3 with evidence? | Does the moat
   survive success? | Is the growth real and healthy? | Does the price
   leave a return? | Can we get our money out? 每个 No 或 Qualified 的
   回答都要有一段跟进，指明什么证据会将其翻转。
2. Scorecard（评分卡）："Scorecard" 表 —— 9 个固定维度及其权重 ——
   市场空间与增速 15 | 行业地位 15 | 护城河 15 |
   收入增长与质量 15 | 商业模式与单位经济 10 | 团队与治理 10 | 估值 10 |
   退出确定性 5 | 风险收益比 5 —— 列为 Score | Why (one line)。当共享
   事实表钉定了评分卡时，精确重复其分数和理由行，并陈述已钉定的总分；
   否则在此根据各归属章节的结论为每个维度打分。以总分行和门槛句收尾
   表格：80+ = investable，70-79 = watch list，below 70 = pass。
3. Demonstrated vs unresolved（已证明与未解决）：两份长度相等的对应
   清单（各 3-5 项）—— "What is demonstrated" 和 "What remains
   unresolved" —— 每项一句话，附其数字或缺口。
4. Recommendation（投资建议）：带 `component: "investment_decision"`
   的投资建议提示框：精确重复已钉定的投资建议句，然后是入场、已钉定
   的基准情形结果、持有期、退出路径，以及逐字的基金占位符："Proposed
   amount: [TO BE DETERMINED BY IC]"、"Allocation: [TO BE DETERMINED
   BY IC]"、"Strategy: [重仓 / 跟投 / 卡位 — IC to select]"。随后是一段
   带 `component: "disclosures"` 的一行法律披露：本备忘录不构成证券
   出售要约；条款以最终认购文件为准。当共享事实表钉定了
   `decision_history_sentence` 时，在此作为历史逐字重述，与投资建议
   提示框相邻（绝不放在其内部）。
5. Monitoring & triggers（投后监控与触发条件）："Monitoring
   Indicators" 表（投后监控）：4-6 行 —— Indicator | Current value |
   Trigger threshold | Response if triggered。当结论为观望/放弃时，
   将此表标题改为 "What changes the verdict"，并把触发条件写成重新
   进入的条件。
