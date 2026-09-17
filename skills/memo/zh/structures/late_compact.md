---
en_sha256: 457c6898d14219dcf4f1c80efabb8c73ab376f513e1e1215b3cfe9b792c5feee
---
---
stage: late_compact
version: 1
risk_format: cards
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

后期（late-stage）精简版结构 —— 本基金的主力备忘录：七个章节，全文约
15,000-17,000 词，写给一位刚进入投资领域、但仍必须做出正确判断的读者。
所谓"精简"指的是结构形状，而不是深度：七个章节而非十二个，只保留读者
真正需要的两张表（Deal Snapshot 交易速览、Key Metrics Snapshot 关键
指标速览）、评分卡、风险清单，以及每章至多两张图表。证据纪律与完整版
报告完全一致：同一份共享事实表、同一份评分卡、同一套数据诚实规则。

深度现在是重点。本结构的上一个版本只写了 6,600 词，创始人的结论是：
读者无法看出这笔投资到底立在什么之上，除非把整份报告翻一遍。篇幅的
存在，是为了让每一个判断都被解释清楚：这个数字衡量的是什么、它是怎么
算出来的、对这一类公司而言什么才算正常、以及什么情况会改变结论。篇幅
只能用于解释，绝不能用于新增论断，也不能把同一个论断换个说法再讲一遍。
已钉定事实是底线：精简只删评论，绝不删已钉定的事实。每一项已钉定的
关键指标（含其精确数值）、每一个情景数字、合理估值区间、入场条款、
每条风险摘要（逐字原文并附评分），以及各归属章节的评分卡句（"This
dimension scores N of M."）都必须出现在本备忘录中 —— 否则钉定回显
（pin-echo）关卡会拒收整个报告包，无论文笔多么优雅。章节字数预算是
软性目标，真正拒收的关卡设在远高于它的位置：每个章节的
`budget_words`（见其 yaml）是该章节全部英文文本（含表格单元格）应当
瞄准的篇幅，`budget_hard_multiple` 则是确定性关卡真正拒收的倍数 ——
执行摘要、公司与团队、估值与回报为 1.3 倍，市场论点、财务与投资决策
为 1.5 倍，风险清单为 2 倍（它诚实的长度取决于风险有几条）。写到目标
字数是"准备收尾"的信号，绝不是"就此中断"：把手上这个论点说完，把
章节收住，然后继续。一个只写了一半的判断，比一个写长了的章节更糟，
因此绝不可为了压到某个数字而删掉钉定事实、子节标题或评分卡句。远低于
目标字数同样是失败，而且是更常见的那一种：它意味着某个判断只被陈述，
却没有被解释。章节偏短时，正确的做法绝不是灌水，而是回头把每一个只给
了结论的判断，补上它背后的推理。每个
章节都按其声明的编号子节组织；全局适用的数据诚实、导航与图表规则由
共享上下文承载。要点与散文各有其位：并列事实用要点，从证据走向结论的
论证用散文段落。

## section: executive_summary
```yaml
id: executive_summary
budget_words: 2600
budget_hard_multiple: 1.3
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

2,400-2,600 词（约四到五页）。这一节是合伙人真正会从头读到尾的部分，
很多人**只**读这一节，因此它必须独立承载整个投资论证：读者即使只读到
这里，也应当知道公司是做什么的、本轮要什么、在决策所依赖的**每一个
维度**上强在哪里、弱在哪里、每个数字是怎么算出来的、什么可能让这笔
投资失败，以及我们的建议是什么。

写给一位刚进入投资领域的读者。每个数字出现之前，先说明它衡量的是
什么；每个比较都说明它对照的标准；每个结论后面都跟上支撑它的证据，
若该数字是推导出来的，还要说明它是怎么推导的。篇幅是用来解释的 ——
绝不用于新增论断，也不用于把同一个论断换个说法再讲一遍。

各子节内容：

1. 项目基本概况：一句平实的话说明公司做什么、为谁做；一句说明
   行业/地域；一句说明其在后期融资阶梯上的位置；一句说明公司类型
   以及该类型下什么是决定性的。不超过 120 词。
2. 本轮融资方案：轮次、工具、规模、价格、隐含持股比例，以及这个价格
   已经预设了什么 —— 入场倍数须在同一口气中给出解读。3-4 句。
3. 核心投资亮点：
   开头：以共享事实表中已钉定的案例总结句开头，用公司名称替换
   "The case" —— 说明哪些维度支撑本案、哪些维度较弱，并附分数。
   此处不得加入风险判断或估值判断。
   bullets 块：`"component": "investment_highlights"`，**恰好三项**，
   按钉定顺序排列（三项是钉定环节固定的数量，本节不得增减）。
   每条要点格式（严格）：第一行是已钉定的标题逐字原文（纯文本，不加
   星号或 markdown；渲染器会把它加粗），随后是已钉定的证据句。
   禁止项：不得出现裸露主题标签（如单独写 "Price."）；不得在亮点中
   写出风险、估值敏感性或投资建议；不得新增数字，也不得写入事实表中
   没有的内容。

   每条标题都必须是一个读者可以单独引用的**结论**：它说明关于这家公司
   什么是成立的、以及为什么重要，而不是它属于哪个话题。"企业级渠道
   承载了分发" 是话题，不合格；"分发不必自建，因为三大云已经在代售"
   是结论，合格。每条标题之后跟**两句**证据（钉定字段允许 2-3 句），
   每句都是完整的句子，说明这个数字衡量的是什么、数字本身、以及它
   来自哪里。证据句绝不以 "证据："这类标签开头 —— 它们就是正文。

   风格：简洁、面向投资人、可直接放入执行摘要。

   工作示例（恰好三条；方括号中的评分维度是钉定字段，**不**写进报告）：

   ```
   Anthropic 这笔投资主要由行业地位（14/15）、收入增长与质量（13/15）
   和护城河（12/15）支撑；较弱的是估值（6/10）与退出确定性（4/8）。

   "component": "investment_highlights"

   [industry_position]
   技术领先已经被商业化验证 —— 这是极少数能把前沿模型变成规模化收入的
   公司之一。
   年化收入衡量这种转化发生得有多快，按公司自己的口径（最近一个月乘以
   十二），它从 2025 年 12 月的约 $9B 升至 2026 年 7 月的 $65B[S4]。
   企业收入占比衡量这些收入是否稳固、而非消费端的来去自如，同一份披露
   显示它约占总收入的 80%[S4]。

   [revenue_growth_quality]
   Claude Code 把编码工具变成了 Agent 的入口，并且在整个行业转向之前
   就占住了这个位置。
   Claude Code 的年化收入衡量增长中有多少来自单一产品，按公司口径已
   超过 $2.5B[S4]。年付费超过 $1M 的客户数衡量采用的深度而非广度，
   在 2026 年 2 月至 4 月之间翻倍[S4]。

   [moat]
   分发不必自建，因为三大云已经在代售 —— 企业可以通过一个已经通过审批
   的供应商直接采购。
   在 AWS Bedrock、Google Vertex AI 与 Microsoft Foundry 上的可用性
   衡量有多少条采购路径无需新增供应商审查，三大云全部覆盖，其中
   Microsoft Foundry 于 2026 年 6 月 29 日实现 GA[S9]。经由这些渠道
   到达公司的收入衡量账面上有多少依赖它们，根据已披露的企业收入拆分，
   我们自己的估算为 25%-30%[C7]。
   ```

   三条亮点之后，输出**维度全景扫描**：一个 `bullets` 块，
   `"component": "dimension_scan"`，把共享事实表中维度扫描的**每一行**
   按钉定顺序逐条列出，每个维度一条要点。它存在的理由是：读者必须能在
   **同一个地方**看到决策所依赖的八件事 —— 市场够不够大、增速如何、
   行业地位、护城河壁垒、团队强度、如何赚钱、是否盈利、上市预期 ——
   并且带着各自的数字，而不必翻遍整份报告去找。

   每条要点的格式为："<维度> — <得分>/<满分>，<强/中等/弱>。<why 句>"，
   随后是已钉定的证据句，证据句须带上数字、该数字衡量的是什么，以及它
   的来源（来源用 [S#]，我们自己的计算用 [C#]）。该块以一句话开头说明
   这份扫描是什么，好让新读者知道该怎么读它。商业模式与单位经济这一条
   带**两句**证据：公司如何收费、这种收费方式能否挺过下一次产品形态
   变化；以及它是否赚钱 —— 当前毛利率，以及要转正需要改变什么。任何
   被判为**弱**的维度，结尾加 "→ 见核心风险提示"，并且**必须**出现在
   第 4 子节中。

4. 核心风险提示：800-900 词，这个字数是硬约束。开头一句点明是哪一条
   风险单独承载着整个投资逻辑。随后是一个 `bullets` 块，
   `"component": "key_risks"`，收录评分最高的**三条**已钉定风险，按钉定
   顺序排列 —— 仅当维度扫描中判为**弱**的某个维度未被这三条覆盖时，才为
   每个未覆盖的弱维度再加一项，**总数最多五项**。每一个弱维度都必须被
   其中某一项覆盖，或由扫描行指向风险清单 —— 这正是读者所依赖的那道检查。

   不要写成"每条已钉定风险各一项"。风险章节的清单会以完整篇幅承载全部
   风险；本子节只承载"读者若只读到这里就必须知道"的那几条。（按每条
   风险一项来写，在一次真实运行中达到了 2,039 词，仅此一项就冲破了本
   章节的上限。）

   每一项以 "<Area label> — <pinned summary verbatim>。" 开头，随后用
   三到四句**解释**它，顺序如下：

   - 给它定量的算式，把数字写进算式里，并附上计算注释的 [C#]，让读者
     能看见它是怎么算出来的，而不是只能选择相信；
   - 在这里什么才算正常，好让读者判断这个数字是否糟糕（例如"成熟软件
     的可比倍数约在 8 倍左右；前沿大模型公司在强势市场中可以更高，
     因此 9 倍偏高但并非离谱"）—— 指令中的公司类型透镜会说明这一
     类型的"正常"是什么样子；
   - 什么条件成立时这条风险不会兑现，或者缓释措施，或者
     "No structural mitigation exists."；
   - 一句话说明**需要核查什么**：能够对它下定论的那两三个事实。

   每一项以 "Impact: <pinned impact verbatim>. (N/10, <likelihood>
   likelihood)" 收尾，并在同一个括号内给出可能性之所以如此的那**一条**
   理由。
5. 投资结论与建议：一个结论标注框（callout）—— 已钉定的投资建议句
   逐字原文、入场条件、合理估值区间、基准情形的回报倍数(MOIC)·内部
   收益率(IRR)、持有期，以及基金占位符逐字原文。若已钉定结论层级和
   评分卡，则以 "{tier} — {total}/100" 开头。已钉定的
   `decision_history_sentence` 在标注框之后作为历史记录逐字陈述。

## section: company_team
```yaml
id: company_team
budget_words: 2400
budget_hard_multiple: 1.3
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
- adoption_distribution
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

2,200-2,400 词。创始人及其身边的团队，是决策所依赖的八件事之一，因此本节要
**论证**团队，而不是罗列团队：他们是谁、他们此前做成过什么、这些经历如何预示
这一次、班底在哪里偏薄，以及治理结构让他们能做什么是普通董事会不会允许的。
对某个人的每一个判断都必须有证据 —— 担任过的职位、交付过的结果、一次离职、
一份文件 —— 绝不能只是印象。各子节内容：

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
budget_words: 2600
budget_hard_multiple: 1.5
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
- competitive_position
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

2,400-2,600 词。本节承载八个维度中的四个 —— 市场有多大、增长有多快、公司在
其中排在哪里，以及什么在保护这个位置 —— 因此它是论证类章节中最长的一节。先用
你掌握的每一个外部估计给市场定量，说明本备忘录采用哪一种口径以及为什么，并把
算式摆出来。然后把公司放进这个市场里定位，最后才论证护城河：它由什么构成、
什么会侵蚀它、它还能撑多久。各子节内容：

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
budget_words: 2300
budget_hard_multiple: 1.5
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
- numbers_integrity
- growth_bridge
- adoption_distribution
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

2,200-2,300 词。公司**如何收费**与**是否赚钱**是两个不同的问题，本节按这个
顺序、用数字把两个都回答。盈利能力要有自己的论证：当前毛利率、毛利率里面装着
什么、转正的路径，以及什么会打断这条路径。一位从未见过这种成本结构的读者，读完
本节应当能够判断它是否成立。各子节内容：

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
budget_words: 1900
budget_hard_multiple: 1.3
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
- numbers_integrity
- valuation_exit
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

1,800-1,900 词。本节的每一个数字都是推导出来的，因此每一个数字都要展示其算式，
并带上对应计算注释的 [C#]。先说明入场价格已经预设了什么，再说它是否合理；并且
给读者一个可以据以判断倍数的对比 —— 这一类型的公司通常按什么倍数成交，以及这家
公司为何落在相对于它们的那个位置。退出预期也属于本节：上市在现实中可能何时发生，
以及在那之前必须先成立什么。各子节内容：

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
budget_words: 2800
budget_hard_multiple: 2.0
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
- competitive_position
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

2,600-2,800 词。这一节过去是一段描述性的文字，创始人的评价是"抓不住
重点"；现在它是一份**清单**：每条风险一张卡片，与完整版报告同一形状，
读者可以扫一遍标题，停在真正要紧的那一条上。

各子节内容：

1. 风险重心：用两三句话点明是哪一条风险单独承载着整个投资逻辑、它为
   什么排在其他风险之上，以及一旦兑现这笔投资会变成什么样子。
2. 风险清单：每条已钉定风险一张**卡片**，按评分从高到低排列，严格使用
   已钉定的风险列表 —— 绝不新增钉定表中没有的风险，也绝不遗漏任何一条
   已钉定风险。卡片格式见指令中的风险卡合约：一个 `heading`，标题为
   "Risk N: <已钉定的摘要>"，随后是固定的若干行。每张卡片约 300-400 词，
   篇幅主要花在 "Why it matters" 这一行上：带数字的算式及说明它如何
   算出的 [C#] 注释，然后是对这一类公司而言什么才算正常（公司类型透镜
   会说明"正常"是什么样子），然后是什么条件成立时这条风险不会兑现。
   "What we watch" 要点名真实的信号，以及能够对它下定论的那两三个
   事实 —— 绝不写 "monitor execution" 或 "track traction" 这类空话。
3. 反面证据：3-5 条要点，`component: "disconfirming_evidence"` ——
   与本备忘录投资建议相悖的最强事实，每条用两三句话权衡：这个事实是
   什么、它为什么对我们不利，以及我们为什么仍然维持该建议（或者诚实
   地说明，它正是评分之所以如此的原因）。章节结尾给出其已钉定的评分卡
   句："This dimension scores N of M." 对应风险收益比。

## section: investment_decision
```yaml
id: investment_decision
budget_words: 1400
budget_hard_multiple: 1.5
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

1,300-1,400 词。最短的一节，因为到这里论证已经完成：给出投资建议、条款、什么
会改变这个建议，以及我们将跟踪什么。不得出现新证据、新数字 —— 凡是重要到该写在
这里的内容，前面某一节必定已经论证过。各子节内容：

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
