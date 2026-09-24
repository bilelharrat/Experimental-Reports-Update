## Chinese memo style guide and glossary

Standing guidance for every Chinese string in a BSH investment memo: the
translation of the finished English package, a Chinese-only repair, and any
Chinese written directly. The Chinese team edits the twin of this file
(skills/memo/zh/zh_style.md); the owner ports each change here.

### How the Chinese should read
- Write the way a Chinese research report (研报) reads: formal written
  Chinese, short declarative sentences, the judgment first and the support
  after it.
- Render the meaning, not the English syntax. Inside one string you may
  split a long English sentence into two Chinese sentences, reorder its
  clauses, or turn an English noun phrase into a Chinese verb phrase, so
  the result reads as if it had been written in Chinese. Never move text
  from one string to another, never merge or split strings, and never drop
  or add a claim, a caveat or a risk.
- Numbers and citation ids stay exactly as written. Every figure, range,
  multiple, percentage and date, and every `[S#]` / `[C#]` token, appears
  in the Chinese string exactly as in the English one; money keeps its
  English form ($24M, $1.0B+), as the number conventions above say.
- One English term, one Chinese term. Use the glossary below every time a
  term appears, in every section, so parallel translators agree. A term
  the glossary does not cover keeps the rendering the document first gave
  it.
- Do not mirror English contrast habits. "Rather than" and ", not X" do not
  become 而非 every time: say what the thing is, and keep 而非 / 而不是 for
  the sentence where the contrast is the point.
- Cut translationese: 进行 + noun (进行分析 → 分析), stacked 的 chains,
  被-passives the Chinese does not need, 对于……来说 and 通过……来
  scaffolding, 一个 / 一种 before every noun, and sentences that trail off
  on 的.
- Names follow the shared rule: keep the English name unless a widely used
  Chinese name exists, then write 中文名（English name）on first use.
- Section titles, subsection titles and risk-card row labels are fixed by
  the structure files and the renderer. Copy them; never re-translate them.

### Glossary
Required Chinese for each English term; "Avoid" lists variants that must
not appear (separated by 、; — means none). Rows marked "(to confirm /
待团队确认)" are defaults chosen where the team's older term table, the
team's drafts and the code disagreed; the notes below say what was chosen
and why.

| English | 中文 | Avoid |
|---|---|---|
| run-rate (revenue) | 年化收入 | 运行率、运行速率、年化运行率 |
| net revenue retention (NRR) | 净收入留存率 | 净收入保留率、净收益留存率 |
| gross margin | 毛利率 | 总利润率、总边际 |
| unit economics | 单位经济 | 单元经济学 |
| free cash flow | 自由现金流 | 免费现金流 |
| cash burn (to confirm / 待团队确认) | 现金消耗 | 燃烧率 |
| cash runway (to confirm / 待团队确认) | 现金可支撑时间 | — |
| valuation | 估值 | — |
| fair value range | 合理估值区间 | 公允价值范围 |
| pre-money valuation | 投前估值 | 货币前估值、前货币估值 |
| post-money valuation | 投后估值 | 货币后估值、后货币估值 |
| discount (SAFE or note conversion) (to confirm / 待团队确认) | 折扣 | 折让 |
| discount (price below peers or a prior round) (to confirm / 待团队确认) | 折价 | 折让 |
| premium (price above peers or a prior round) | 溢价 | 升水 |
| moat | 护城河 | 城壕 |
| durability (of revenue or an advantage) | 持续性 | 耐久性、耐用性 |
| base case | 基准情形 | 基础案例、基础情景 |
| bear case (to confirm / 待团队确认) | 悲观情形 | 看跌情形 |
| bull case (to confirm / 待团队确认) | 乐观情形 | 看涨情形 |
| MOIC (to confirm / 待团队确认) | 回报倍数 | — |
| IRR (to confirm / 待团队确认) | 内部收益率 | 内部回报率 |
| return hurdle (the fund's bar) | 回报门槛 | 障碍率、跨栏率 |
| exit multiple | 退出倍数 | — |
| cap table | 股权结构表 | 上限表 |
| lead investor | 领投方 | 铅投资者 |
| oversubscribed | 超额认购 | 过度认购 |
| sales pipeline (to confirm / 待团队确认) | 销售管线 | — |
| letter of intent (LOI) | 意向书 | 意图信 |
| tailwind | 利好因素 | 顺风 |
| headwind | 不利因素 | 逆风 |
| SAFE (simple agreement for future equity) | SAFE | 安全协议 |
| investment highlights | 核心投资亮点 | — |
| key risks | 核心风险提示 | — |
| recommendation | 投资建议 | — |
| scorecard | 评分卡 | 记分卡 |

### Rows to confirm
- discount: the older table had no entry, and one memo mixed 折让, 折价 and
  折扣 for the same word. Default: 折扣 for a SAFE or note conversion
  discount, 折价 for a price below peers or a prior round; 折让 in
  neither.
- bear / bull case: the team's older table writes 熊市 / 牛市情形; the
  founder's report framework writes 保守 / 中性 / 乐观 for scenario
  assumptions, and research reports write 悲观 / 乐观情形. Default:
  悲观情形 / 乐观情形 — 牛市 and 熊市 describe markets, not scenarios.
  Only the calques 看跌 / 看涨情形 are flagged, so the team can switch
  without every memo being flagged.
- cash burn / cash runway: the team's drafts write 烧钱 and 现金跑道; the
  shared translation rules prefer 现金消耗 and 现金可支撑时间 and
  discourage a mechanical 跑道. Default: the shared rules' words; neither
  of the team's words is flagged.
- MOIC / IRR: the older table says 回报倍数 / 内部收益率; the translation
  rules keep the Latin acronyms. Default: first use 回报倍数（MOIC）and
  内部收益率（IRR）, then MOIC and IRR alone; table headers may use the
  acronyms throughout.
- sales pipeline: the team's own drafts write 管线. Default: 销售管线 on
  first use, 管线 afterwards.
