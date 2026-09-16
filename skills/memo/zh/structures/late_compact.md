---
en_sha256: c466f89f7abbb8c4d42060a6655d23b55bc901108ba5179bffe83e3746ee9ae3
---
---
stage: late_compact
version: 1
risk_format: bullets
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
components:
- key_metrics_snapshot
- deal_terms
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

后期（late-stage）精简版结构 —— 即短版备忘录，以最紧凑的合伙人备忘录
风格为范本：七个章节，全文约 2,600-3,200 词，几乎所有内容都以结论先行
的要点表述（"An IP position that is hard to overstate. 120+ patents,
90+ issued, zero rejections."，即"一个难以高估的 IP 地位。120 余项专利，
90 余项已授权，零驳回。"），只保留读者真正需要的两张表（Deal Snapshot
交易速览、Key Metrics Snapshot 关键指标速览）、评分卡，以及至多两张
图表。证据纪律与完整版报告完全一致：同一份共享事实表、同一份评分卡、
同一套数据诚实规则 —— 信息更少，但绝不允许信息更差。凡是保留进本备忘录
的数字，都必须是决策所依赖的数字；细节留在完整版报告里，而不在这里。
已钉定事实是底线：精简只删评论，绝不删已钉定的事实。每一项已钉定的
关键指标（含其精确数值）、每一个情景数字、合理估值区间、入场条款、
每条风险摘要（逐字原文并附评分），以及各归属章节的评分卡句（"This
dimension scores N of M."）都必须出现在本备忘录中 —— 否则钉定回显
（pin-echo）关卡会拒收整个报告包，无论文笔多么优雅。章节字数预算是
上限，不是目标：每个章节的 `budget_words`（见其 yaml）是该章节全部
英文文本（含表格单元格）的硬性最大值，超出预算的章节会被确定性关卡
拒收。超出预算的章节须删减评论 —— 每个论点一条要点、每个判断一个
分句 —— 直到符合为止。拿不准时就删；深度内容由完整版报告承载。每个
章节都按其声明的编号子节组织；全局适用的数据诚实、导航与图表规则由
共享上下文承载。默认使用要点而非段落：仅当论证确实需要连续的句子时
才使用散文段落。

## section: executive_summary
```yaml
id: executive_summary
budget_words: 600
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

1000-1200 词。不得使用表格。各子节内容：

1. 项目基本概况：话说明公司做什么、为谁做；一句说明
   行业/地域；一句说明其在后期融资阶梯上的位置。不超过 120 词。
2. 本轮融资方案：轮次、工具、规模、价格、隐含持股比例，以及这个价格
   已经预设了什么 —— 入场倍数须在同一口气中给出解读。3-4 句。
3. 核心投资亮点：
  开头：用已钉定的案例名称替换 “The case”，一句话总结该公司的总体亮点概括（不超过 20 字）。不得在此处加入任何风险或估值判断。
  bullets 块：输出字段 "component":"investment_highlights"。该块包含 2–4 条要点，按已钉定顺序排列（默认 3 条；若证据不足可输出 2 条；若第 4 条证据强度足够可输出 4 条）。
  每条要点格式（严格）：
  第一行：已钉定的标题逐字原文（纯文本，不加 Markdown）。
  第二行：证据句（1–2 句纯文本），先说明该数字/事实衡量的是什么，再说明来源（例如“公司披露”、“Menlo Ventures 買方調查”、“our own estimate: input = X”），并列出该证据的输入项（例如“输入：最近一个月乘以 12 的 run‑rate”）。
  禁止在证据句中加入任何新的数字或主观判断（例如“估值过高”或“风险高”）。
  禁止项：不得出现裸露主题标签（如单独写 “Price.”）；不得在亮点中写出风险、估值敏感性或投资建议；不得新增数字或未在事实表中出现的文字。
  风格：简洁、面向投资人、可直接放入执行摘要。
  缺失处理：若共享事实表缺少必需字段，返回错误："missing_input: <field_name>"。

   ---示例开始---
    示例 A（标准 3 条）  
    Anthropic — 前沿模型驱动的商业化能力  
    "component":"investment_highlights"

    全球最稀缺的前沿模型型领导者之一，收入增长已经验证技术领先可以转化为商业价值
    证据：衡量公司规模化商业化能力；来源公司披露；输入：公司口径的 run‑rate 从 2025‑12 的约 $9B 升至 2026‑07 的 $65B（最近一个月乘以 12）。

    Claude Code 成为杀手级应用，率先抓住 Coding → Agent 的巨大市场
    证据：衡量在开发者/企业工作流中的渗透与付费强度；来源公司披露；输入：Claude Code run‑rate 超 $2.5B（公司口径），以及公司披露的年付费 $1M+ 客户数在 2026‑02 至 2026‑04 期间翻倍。

    企业级渠道与云集成已实现商业化分发
    证据：衡量渠道与生态接入能力；来源公开合作公告與公司披露；输入：Claude 通过 AWS Bedrock、Google Vertex AI 与 Microsoft Foundry 销售，且 Microsoft Foundry 于 2026‑06‑29 实现 GA。

    示例 B（证据不足只输出 2 条）  
    Company X — 技术与早期客户验证  
    "component":"investment_highlights"

    技术领先并已实现早期商业化
    证据：衡量技术向收入转化的初步证据；来源公司披露；输入：公司披露的 run‑rate 与若干大客户合同（见事实表）。

    开发者工具已获得高付费客户渗透
    证据：衡量付费客户集中度；来源公司披露；输入：公司披露的年付费 $1M+ 客户数与开发者产品 run‑rate。
   ---示例结束---

4. 核心风险提示：一个 `bullets` 块，`"component": "key_risks"`，恰好
   三项 —— 评分最高的三至五已钉定风险，按钉定顺序排列，每条格式为
   "<Area label> — <pinned summary verbatim>. Impact:
   <pinned impact verbatim>. (N/10, <likelihood> likelihood)"。
5. 投资结论与建议：一个结论标注框（callout）—— 已钉定的投资建议句
   逐字原文、入场条件、合理估值区间、基准情形的回报倍数(MOIC)·内部
   收益率(IRR)、持有期，以及基金占位符逐字原文。若已钉定结论层级和
   评分卡，则以 "{tier} — {total}/100" 开头。已钉定的
   `decision_history_sentence` 在标注框之后作为历史记录逐字陈述。

## section: company_team
```yaml
id: company_team
budget_words: 750
scorecard_dimensions:
- team_governance
en_title: Company, Team & Deal
zh_title: 公司、团队与交易
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?company,?\s*team\s*(?:&|and)\s*deal\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:公司、团队与交易|公司与团队|公司与交易)\s*[:：]?\s*$
components:
- key_metrics_snapshot
- deal_terms
floor: {}
pass_affinity:
- deployment_behavior
- team_governance
title_word_aliases:
- company, team and deal
- company and team
subsections:
- en: Company & key metrics
  zh: 公司概况与关键指标
- en: The deal
  zh: 交易条款
- en: Team & founder-market fit
  zh: 团队与创始人匹配
```

400-550 词。各子节内容：

1. 公司概况与关键指标：3-4 条结论先行的要点（成立时间/总部/卖什么/
   如何走到今天 —— 各一行），然后是 "Key Metrics Snapshot" 表，
   `component: "key_metrics_snapshot"`：7 行 —— Revenue/ARR |
   Growth rate | Gross margin | Burn or FCF | Cash runway |
   Last/current valuation | Implied multiple（收入/ARR | 增长率 |
   毛利率 | 烧钱或自由现金流 | 现金跑道 | 上轮/当前估值 | 隐含倍数）
   —— 列为 Value | Reading（数值 | 解读；Reading 单元格是一个结论
   片段）。缺失单元格写 "Not disclosed — <implication>"。当共享事实表
   载有这七项之外的关键指标时，须为每项已钉定指标增加一行，填入其
   精确的钉定数值 —— 每一个已钉定的数字都必须在本备忘录的某处出现。
2. 交易条款："Deal Snapshot" key_value 表，`component: "deal_terms"`，
   恰好以下 10 行：Round | Instrument | Raise size | Pre-money |
   Post-money | Implied stake | Primary / secondary split | Use of
   proceeds | Co-investors | Expected close（轮次 | 工具 | 融资规模 |
   投前估值 | 投后估值 | 隐含持股 | 新股/老股比例 | 资金用途 | 联合
   投资方 | 预计交割时间）。然后是一句以结论开头的解读句：各方估值
   标记是支撑还是削弱了这个入场价格。
3. 团队与创始人匹配：每位关键人物一条要点，采用合伙人备忘录风格 ——
   "Name — Role. What they built or ran before that THIS business
   requires, verified with dates."（"姓名 —— 职务。此前建立或运营过
   什么、且正是这项业务所需要的，附经核实的日期。"）—— 然后是一句
   答案先行的结论句，评价创始人与市场的匹配度（已由过往工作证明 /
   有主张但未证明 / 缺失），再一句评价治理（如果创始人判断错误，谁能
   纠偏）。章节结尾给出其已钉定的评分卡句："This dimension scores
   N of M." 对应 团队与治理。

## section: thesis_market
```yaml
id: thesis_market
budget_words: 650
scorecard_dimensions:
- market_size_growth
- industry_position
- moat
en_title: Thesis, Market & Competition
zh_title: 投资逻辑、市场与竞争
parity_en: ^\s*(?:(?:iii|3)[\.\、]\s*)?thesis,?\s*market\s*(?:&|and)\s*competition\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iii|3|三)[\.\、]\s*)?(?:投资逻辑、市场与竞争|市场与竞争|投资逻辑)\s*[:：]?\s*$
components: []
floor: {}
pass_affinity:
- market_sizing
- replacement_coexistence
- competitive_rights
title_word_aliases:
- thesis, market and competition
- market and competition
subsections:
- en: Why this matters now
  zh: 为什么是现在
- en: Market & ceiling
  zh: 市场空间与天花板
- en: Competition & moat
  zh: 竞争与护城河
```

450-550 词。各子节内容：

1. 为什么是现在：用 2-3 条结论先行的要点陈述投资逻辑 —— 这打开了
   什么市场、为什么时机是现在、为什么是这家公司 —— 每条附其最硬的
   数字。
2. 市场空间与天花板：首先，调研找到的每一个外部估计各占一条要点
   （研究机构或公司、统计口径、数值、年份 —— 只要存在，绝不少于三个；
   绝不因与其他估计相悖而剔除），然后 TAM/SAM/SOM 各占一条要点
   （规模、年份，以及所依据的外部估计或我们自己的输入 —— 或缺失
   数据的说明句），开头先给出本备忘录采用的区间及为什么该口径适合
   这家公司，然后答案先行地回答天花板问题：这个市场对公司的封顶更
   接近 $20B、$100B 还是 $500B，以及能移动它的那一个假设。一句话说明
   政策/监管环境（或 "No regulatory regime materially constrains
   this business today"）。
3. 竞争与护城河：今天谁领先、3-5 年后最可能谁领先（附数据点）；真实
   存在的 2-3 个护城河来源，各附证据，并点名缺失的护城河；一句答案
   先行的结论：护城河正在拓宽 / 稳定 / 收窄，以及这对退出倍数意味着
   什么。章节结尾给出其三句已钉定的评分卡句 —— "This dimension
   scores N of M." 分别对应 市场空间与增速、行业地位 和 护城河。

## section: business_financials
```yaml
id: business_financials
budget_words: 600
scorecard_dimensions:
- business_model_ue
- revenue_growth_quality
en_title: Business & Financials
zh_title: 业务与财务
parity_en: ^\s*(?:(?:iv|4)[\.\、]\s*)?business\s*(?:&|and)\s*financials\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iv|4|四)[\.\、]\s*)?(?:业务与财务|商业模式与财务|财务分析)\s*[:：]?\s*$
components: []
floor: {}
pass_affinity:
- arithmetic_denominators
- growth_bridge
- gtm_operating_burden
title_word_aliases:
- business and financials
subsections:
- en: How it makes money
  zh: 商业模式
- en: The numbers
  zh: 关键财务
- en: Healthier or hungrier
  zh: 增长更健康还是更烧钱
```

400-500 词。各子节内容：

1. 商业模式：谁付费、为什么付费、按什么定价，以及已披露的最强证明点
   —— 2-3 条结论先行的要点。对最强的需求信号写一句两面兼顾的话
   （"The pipeline is valuable evidence of demand. It is not
   revenue."，即"管线是需求的宝贵证据，但它不是收入。"）。
2. 关键财务：收入轨迹（真正重要的 2-3 个数字，各附解读）、已披露的
   留存/单位经济、烧钱与现金跑道 —— 结论先行的要点，缺失数据明确
   说明缺失。当序列数据已披露时，此处允许一个图表槽位
   `chart_revenue_trajectory`（建议折线图）；否则不放图表，精简版也
   不需要替代说明行 —— 由要点承接这一空缺。
3. 增长更健康还是更烧钱：以一句话的答案开头；用两句话给出证明它的
   算术；以重申结论收尾。章节结尾给出其两句已钉定的评分卡句 ——
   "This dimension scores N of M." 分别对应 商业模式与单位经济 和
   收入增长与质量。

## section: valuation_returns
```yaml
id: valuation_returns
budget_words: 750
scorecard_dimensions:
- valuation
- exit_certainty
en_title: Valuation, Returns & Exit
zh_title: 估值、回报与退出
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?valuation,?\s*returns?\s*(?:&|and)\s*exit\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?(?:估值、回报与退出|估值与回报|估值分析)\s*[:：]?\s*$
components: []
floor:
  require_valuation_refs: true
pass_affinity:
- time_base
- arithmetic_denominators
- valuation_comps
- exit_paths
title_word_aliases:
- valuation, returns and exit
- valuation and returns
role: valuation
subsections:
- en: What the price assumes
  zh: 价格已经包含了什么
- en: Fair value & scenarios
  zh: 公允价值与情景
- en: Exit paths
  zh: 退出路径
```

450-550 词。各子节内容：

1. 价格已经包含了什么：入场倍数对照真正重要的 2-3 个可比公司（各一条
   要点，标的公司在先），然后是买方已在为什么付费的算术。答案先行：
   价格高于、等于还是低于证据所能支撑的水平。
2. 公允价值与情景：已钉定的合理估值区间逐字原文及其依据；然后熊市 |
   基准 | 牛市情形各一条要点，精确载明每一个已钉定的情景数字 —— 退出
   年份、退出年收入、退出倍数、退出价值、毛回报倍数(MOIC)、内部收益率
   (IRR)（钉定关卡逐一核对每个数字）。图表槽位 `chart_return_scenarios`
   （建议柱状图；x = Bear / Base / Bull；y = gross MOIC），基于已钉定的
   回报倍数(MOIC)绘制，附解读说明和一句话图注。
3. 退出路径：现实可行的路径，附具名的潜在收购方或 IPO 窗口、各自的
   约束条件，以及一个非溢价结果的后果算术。答案先行：钱究竟怎么回来，
   确定性有多高。章节结尾给出其两句已钉定的评分卡句 —— "This
   dimension scores N of M." 分别对应 估值 和 退出确定性。

## section: risks
```yaml
id: risks
budget_words: 500
scorecard_dimensions:
- risk_reward
en_title: Risks
zh_title: 风险
parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?risks?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?(?:风险|风险分析|投资风险)\s*[:：]?\s*$
components:
- disconfirming_evidence
floor:
  bullets_or_prose: true
pass_affinity:
- alternative_explanations
- competitive_rights
title_word_aliases:
- risks
- risk analysis
role: risk
subsections:
- en: The center of gravity
  zh: 风险重心
- en: Risk register
  zh: 风险清单
- en: Disconfirming evidence
  zh: 反面证据
```

300-400 词。各子节内容：

1. 风险重心：用一两句话点明是哪一条风险单独承载着整个投资逻辑。
2. 风险清单：每条已钉定风险一条要点，按评分从高到低排列，严格使用
   已钉定的风险列表。每条要点：已钉定的摘要逐字原文（它本身已是一句
   完整的结论句），然后是 " — N/10." 附评分，然后是一个分句的缓释
   措施，或 "No structural mitigation exists."。绝不允许主题标签，
   绝不允许新增钉定表中没有的风险。
3. 反面证据：2-3 条要点，`component: "disconfirming_evidence"` ——
   与本备忘录投资建议相悖的最强事实，每条用一个分句权衡。章节结尾
   给出其已钉定的评分卡句："This dimension scores N of M." 对应
   风险收益比。

## section: investment_decision
```yaml
id: investment_decision
budget_words: 700
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
- en: Scorecard
  zh: 评分卡
- en: What decides it
  zh: 决定性因素
- en: Recommendation
  zh: 投资建议
- en: Monitoring & triggers
  zh: 投后监控与触发条件
```

350-450 词。各子节内容：

1. 评分卡："Scorecard" 表 —— 9 个固定维度及其权重 —— 市场空间与增速
   15 | 行业地位 15 | 护城河 15 | 收入增长与质量 15 | 商业模式与单位
   经济 10 | 团队与治理 10 | 估值 10 | 退出确定性 5 | 风险收益比 5 ——
   列为 Score | Why（一行）。精确重复已钉定的分数与理由行；以合计行
   和门槛句收尾（80 分以上投资 / 70-79 分观察 / 70 分以下放弃）。
2. 决定性因素：六个问题压缩为 6 条要点，`component:
   "evidence_thresholds"` —— 每条格式为 "Question — Yes/No/
   Qualified: one-line basis."。回答为 No 或 Qualified 时，追加一个
   分句说明什么证据能扭转它。
3. 投资建议：带 `component: "investment_decision"` 的标注框 —— 已钉定
   的投资建议句逐字原文、入场条件、已钉定的基准情形结果、持有期、
   退出路径，以及基金占位符逐字原文："Proposed amount: [TO BE
   DETERMINED BY IC]"、"Allocation: [TO BE DETERMINED BY IC]"、
   "Strategy: [重仓 / 跟投 / 卡位 — IC to select]"。随后是一行带
   `component: "disclosures"` 的法律披露段落。已钉定的
   `decision_history_sentence` 作为历史记录逐字重述。
4. 投后监控与触发条件：3-4 条要点 —— 指标、当前值、触发阈值、应对
   措施。当结论为观察/放弃时，采用 "What changes the verdict"（什么会
   改变结论）的框架：触发条件即为重新入场的条件。
