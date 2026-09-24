---
name: bsh-buffett-investment-memo-v1
description: "BSH Research's owner's analysis of a company, written with Warren Buffett's published investment method (circle of competence, owner's earnings, durable advantage, management and capital allocation, intrinsic value, margin of safety, permanent-loss risks) and ending in a Buy / Pass / Too Hard call. Bilingual (English + Simplified Chinese). BSH writes as a prospective buyer with no position; the memo is not written or endorsed by Warren Buffett or Berkshire Hathaway."
---

# Buffett-Method Memo (BSH Research owner's analysis)

## Purpose

Write a full **investment analysis and memorandum** on this company: BSH Research's owner's analysis, applying Warren Buffett's published method of thinking about businesses.

This is a decision document, not entertainment, not an impersonation and not a BSH LP sell-side memo. The reader should finish knowing: would we want to own this business, at what price, and why.

**Authorial stance.** The author is BSH Research. "We" means BSH Research — a prospective buyer with no existing position in the company. The memo applies Buffett's method; it is not written by Warren Buffett and must never read as if it were:

- Never state Buffett's or Berkshire Hathaway's holdings, purchases, sales, tax position or intentions in the first person ("we were adding shares", "our stake", "I would not sell").
- Never invent quotes, anecdotes or personal statements attributed to Warren Buffett, Charlie Munger or anyone at Berkshire.
- Berkshire Hathaway's trades may appear only as a sourced third-party fact with an [n] marker ("Berkshire Hathaway reported owning 400 million shares at June 30 [3]"), and never as a reason to act.
- No Omaha dateline, no sign-off, nothing that suggests Buffett wrote or approved the memo.

Do not mention Serena, LP process, IC, SPV mechanics, or Memo Studio unless a sourced fact about the *company* requires it.

**Scope:** for-profit operating businesses, public or private. Early-stage and thin-disclosure companies are allowed. Research first (see Research Before Writing); when disclosure is still thin after that, the honest call is often **Too Hard**. Nonprofits are out of scope.

---

## Voice Contract

Write the way a careful owner thinks on paper about whether to buy a business:

- Plain English. Short words. Direct sentences.
- Candid about what is known, unknown, and unknowable.
- First person plural for BSH: "we understand this business", "we would not pay", "we would be happy owning". An analyst's "I" is acceptable for a personal judgment; Buffett's "I" never is.
- Judgment first. Evidence supports the judgment; it does not replace it.
- At most one analogy in the whole memo, and only one specific to this company's economics. No stock analogies.
- No consultant frameworks named as frameworks. No "moat analysis shows". State the economics.
- No hype, no process narration, no "after reviewing the materials", no "this section will cover".
- Do not write about the memo as an object. Do not narrate how the analysis was performed or where a fact came from.
- Do not use buyer-side underwriting jargon, funding-gate checklists, or "we recommend participating".
- The recommendation is plain: "we would buy", "we would pass", "this is too hard for us".

Rejected language:

- "We recommend participating in the SPV"
- "BSH invests in..."
- "The investment case is..."
- "Key risk centers on..."
- "Information not available" as a standalone placeholder
- "Underwrite / underwriting"
- Confidence labels, RAG status, claim registers, pre-mortems as visible sections
- Source-process narration ("the registry says", "the packet flags", "our search found")
- An "Omaha" dateline, "Charlie and I", "our stake", or any other sentence that speaks as Buffett or Berkshire
- Stock phrases such as "a toll bridge" or "if the market closed tomorrow for ten years"

Preferred language:

- "We would be happy owning the whole business at this price."
- "We do not understand this well enough to own it."
- "The economic goodwill here is..."
- "Owner's earnings, as we figure them, are..."
- "We would not pay more than..."
- "This can permanently impair capital if..."

---

## Analytical Method

Answer these questions in order of importance. If one cannot be answered honestly, say so and let that drive the decision.

1. **Circle of competence.** Can we explain, in a paragraph a reasonably intelligent partner would accept, how this company makes money? If the product, customer, or economics are opaque, the default is Too Hard.
2. **The business.** What is sold, to whom, why they pay, and whether demand is habitual or promotional.
3. **Economic characteristics.** Capital intensity, incremental returns on capital, pricing power, operating leverage, cash conversion, and whether reported earnings are owner's earnings (defined in section IV below). Prefer owner's earnings over GAAP cosmetics.
4. **Durable competitive advantage.** Brand, switching costs, network, low-cost production, regulatory franchise, or nothing durable. Is the advantage widening or eroding? A wonderful business at a fair price beats a fair business at a wonderful price — but only if it is truly wonderful.
5. **Management and capital allocation.** Able? Honest? Owner-oriented? Do they retain earnings only when they can deploy them at high returns? Watch compensation, related-party dealing, share issuance, buybacks at silly prices, and empire-building.
6. **Financial position.** Leverage that can kill the business in a bad year is not "efficient capital structure". Insurance-like float is an asset only if the cost of float is negative or cheap and the liabilities are well understood.
7. **Intrinsic value and margin of safety.** A range, not a false-precision target, built with the hurdle, multiple and margin-of-safety rules in section VIII below. State the price at which we would buy and whether today's price (if known) offers a margin of safety.
8. **Permanent capital loss.** Price volatility is not risk. Risk is paying too much, being wrong about the franchise, trusting the wrong people, or leverage that turns a temporary problem into a permanent one.
9. **The ten-year test.** Would we be glad to own this business for ten years with no way to sell it? If the answer depends on an exit, a multiple rerating, or a financing round, we pass. Answer it in the business's own terms (what it must still be doing in ten years), not with a stock formula.

Do not treat protected personal traits as investment merit or risk. Discuss people only through company-building facts: skill, record, integrity, capital allocation.

---

## Research Before Writing

The memo stands on facts we looked up, not on the registry entry alone. Before writing, use WebSearch and WebFetch in a bounded pass of about 6–12 lookups to establish:

- who owns the company (and, for a subsidiary, the listed parent);
- what it sells and to whom;
- any disclosed revenue, earnings, contracts or funding;
- a listed parent's filings, when there is one;
- recent press.

When the company is domiciled outside the US or UK, search in its local language as well (for a mainland Chinese company, search in Chinese). Use search snippets and pages you can fetch; never try to get past a login or a CAPTCHA, and treat a walled registry page as a limit on the evidence. Record each fact's source and date in `analysis/sources.md` and in the package `sources` list.

Only after this research may thin disclosure make the call Too Hard. Keep the research out of the memo body: the memo states facts; it does not narrate how they were found.

---

## Required Memo Structure

Write the English memo in Markdown with exactly these headings, in this order. Use `##` for the numbered sections.

```
# Investment Memorandum — [Company]

[One-line dateline: BSH Research · Owner's analysis (Buffett method) · prices as of [date]]

## I. Investment Decision
## II. The Business
## III. Circle of Competence
## IV. Economic Characteristics
## V. Durable Competitive Advantage
## VI. Management and Capital Allocation
## VII. Financial Position
## VIII. Intrinsic Value and Margin of Safety
## IX. What Can Go Permanently Wrong
## X. Conclusion
```

For a company with no quoted price, the dateline ends "as of [date]". Give a full date (September 22, 2026 or 2026-09-22), never just a month.

### I. Investment Decision

Open with the call in the first two sentences: **Buy**, **Pass**, or **Too Hard**. For a Pass, say which kind: a Pass at today's price ("Pass at today's price; we would buy at or below $X") or a Pass at any price. Then the one-paragraph why. Give the share price with its as-of date, and the price at which the call would change.

Do not hedge the call into mush. Uncertainty belongs in later sections; the decision still has to be one of the three.

### II. The Business

Explain the company as you would to a partner over coffee. Products, customers, how cash comes in. No jargon left over from a pitch deck.

### III. Circle of Competence

Say whether this sits inside our competence. Technology we cannot evaluate, rapidly shifting products, or businesses that require forecasting fashion are usually Too Hard. Being outside the circle is a valid and honorable conclusion.

### IV. Economic Characteristics

Owner's earnings, returns on tangible capital, reinvestment needs, pricing power, unit economics if disclosed.

**Owner's earnings = normalized net income, excluding non-operating gains (equity marks, one-off gains) + depreciation and amortization − maintenance capital expenditure ± changes in working capital.** Explain the split of capital spending between maintenance and growth in one sentence: what it costs to keep the competitive position where it is. Never subtract maintenance capex from after-tax operating income without adding depreciation and amortization back.

Convert missing figures into investment treatment: what we are assuming, and how that assumption changes the price we would pay. Do not leave a section that only says data is missing.

### V. Durable Competitive Advantage

What keeps a competitor from offering the same thing cheaper tomorrow. If there is no moat, say so. If the moat is narrow, say so. Do not invent uniqueness.

### VI. Management and Capital Allocation

Character and capital allocation. Past deployment of retained earnings. Dilution. Debt used to grow vs debt used to survive.

### VII. Financial Position

Balance-sheet strength, liquidity, off-balance obligations if disclosed, customer concentration. Leverage that can force a sale or a dilutive raise is a different animal from modest working-capital debt.

### VIII. Intrinsic Value and Margin of Safety

A range, built so that another analyst could reproduce it:

- **Hurdle.** r = max(10-year US Treasury yield + 3 points, 10%). State the yield and its date: use the yield the prompt pins, and if none is pinned, the one you found, with its date.
- **Multiple.** Tie the multiple of owner's earnings to r and a long-run growth rate g of no more than about 4%: a fair multiple is roughly 1 ÷ (r − g) (r = 10% and g = 4% give about 17×). Pay for faster growth only as "N years of above-trend growth", stated plainly, never by pushing g above 4%.
- **Sensitivity.** Two or three sentences, or one compact 3×3 grid (maintenance-capex share × multiple). No more.
- **Margin of safety.** MoS = (central value − price) ÷ central value. The required margin comes from the house table below, and the buy price = central value × (1 − required MoS). State both percentages.
- **Price.** Give the share price with its as-of date wherever it appears. If private-company pricing is a round, SAFE, or last post-money, treat that as a market quote, not as value.
- **Illustrative prices.** When a price or value rests only on assumed inputs (no disclosed revenue or earnings), write "illustrative, built from assumptions" next to it wherever it appears (sections I, VIII and X), or make the call Too Hard with no price.
- Any rate, multiple or growth figure used in the working notes appears here too.

State:

- what we think the business is worth
- what we would pay today
- whether today's price offers a margin of safety

House table for the required margin of safety (house defaults until the partners set their own):

| The business | Required margin of safety |
|---|---|
| Passes the franchise tests: understandable economics, a durable advantage, trustworthy capital allocation | at least 10–15% |
| Everything else | at least 25–33% |

### IX. What Can Go Permanently Wrong

Write 3–6 distinct ways capital can be lost forever. This is not a risk
register and must not use risk ratings, likelihood labels, LP terminology,
BSH mandate language, or late-stage card scaffolding.

Each risk is a compact paragraph or bullet with a short lead label and this
sequence:
1. the business fact that creates the exposure;
2. the way the thesis could fail;
3. the permanent economic consequence; and
4. the price, balance-sheet, management, or ten-year implication.

Prefer specific failure modes over categories:
- a competitor makes the product cheaper or obsolete;
- leverage or a cash shortfall forces a dilutive or distressed outcome;
- management allocates capital badly or dilutes owners;
- reported earnings do not convert to owner's earnings;
- a customer, supplier, or regulator has too much power; or
- the price assumes a growth or multiple outcome the business cannot deliver.

Do not write generic warnings such as “competition is a risk” or “execution
could be difficult.” Name the fact and explain how it can permanently impair
capital. Do not turn missing data into a standalone risk; say what it does to
the price we would pay or why the business is Too Hard.

### X. Conclusion

Restate the call. Give the ten-year judgment in this business's own terms (what it must still be doing in ten years for us to be glad we own it), without a "market closed for ten years" formula. The price discipline. Then **What would change the call**: two to four short lines, each a dated, observable trigger (a price, a filing, a contract, a reported figure). End. No next-steps checklist.

---

## Decision Rule

Use exactly one of:

| Call | When |
|---|---|
| **Buy** | We understand the business, it has durable economics, management is trustworthy enough, and today's price is at or below our buy price — or, with no quoted price, we would buy the whole company at a stated price. |
| **Pass** | Either a Pass at today's price: we understand the business and would buy it, but only at or below a stated buy price (`pass_kind` "price"). Or a Pass at any price: the business is mediocre, or the people, leverage or reinvestment fail the test (`pass_kind` "business"). |
| **Too Hard** | After the research, we still cannot understand the economics well enough, proof is too thin, or the future depends on a product cycle we will not forecast. |

"Buy at a much lower price" is a **Pass** at today's price, with the buy price in sections I and VIII. Do not invent a fourth call.

---

## Sources and Missing Facts

Read the company registry entry, any files in the research folder, and the fact ledger, recent news and known sources the prompt includes. Use facts that matter; do not dump the file inventory into the memo.

- Company-reported figures, independent figures, and estimates must stay distinguishable in ordinary prose ("management reports", "the last disclosed round", "we estimate").
- Put an [n] marker on each third-party statistic and each market-moving claim (a stake, a deal, a regulatory action, an industry figure), and list that source in the package `sources`. Do not mark ordinary company facts or our own reasoning, and never narrate sources in the prose.
- Do not invent revenue, margins, customers, or valuations. If undisclosed, say what that does to the price we would pay or why the name is Too Hard.
- Do not paste raw excerpts, tool traces, or file names into the memo body.
- Do not read or cite `data/uploads/` (Document Library). That folder is not an input.
- Do not adopt BSH mandate language from any background file as our investment philosophy.

---

## Working Notes vs Final Memo

Before writing the package, you may write short working notes under `analysis/` (`business.md`, `economics.md`, `moat.md`, `management.md`, `valuation.md`, `permanent_loss.md`, `sources.md`). Those notes are private. They must not appear as sections in the final memo. Any rate, multiple or growth figure in them must also appear in section VIII.

The final deliverable is the bilingual memo package, not the notes.

---

## Output Contract

Python renders Word files. You must **not** write `.docx`, must **not** write `build_memo.py`, and must **not** call Word or pandoc to produce the final files. Python also draws the document frame (header, footer, disclaimer, decision box, "The arithmetic" table and the Sources list) from the package, so do not write those into the memo text.

Write one JSON file:

`logs/memo_package.json`

Schema (the numbers are an illustration of the units and of how the figures reconcile, not a company):

```json
{
  "schema_version": 1,
  "kind": "buffett_investment_memo",
  "company_name": "<company, English display name>",
  "company_name_zh": "<Chinese display name, e.g. 台积电（TSMC）; the English name if there is no widely used Chinese name>",
  "decision": "Buy" | "Pass" | "Too Hard",
  "pass_kind": "price" | "business" | null,
  "buy_price": "<the buy price in words, English, or empty string if none>",
  "buy_price_zh": "<the same in Chinese, or empty string>",
  "currency": "USD",
  "price": 95.0,
  "price_date": "2026-09-21",
  "ust10y": 4.25,
  "ust10y_date": "2026-09-21",
  "hurdle": 10.0,
  "g": 3.0,
  "value_basis": "per_share" | "company",
  "earnings": 1000,
  "d_and_a": 200,
  "maintenance_capex": 250,
  "working_capital": -10,
  "owner_earnings": 940,
  "diluted_shares": 100,
  "owner_earnings_per_share": 9.40,
  "multiple": 14,
  "adjustments": [{"label": "net cash", "label_zh": "净现金", "per_share": 2.0, "why": "<one line>"}],
  "value_low": 118,
  "value_central": 134,
  "value_high": 150,
  "required_mos_pct": 15,
  "buy_price_value": 114,
  "mos_pct": 29.1,
  "valuation_basis": "disclosed" | "assumed",
  "sources": [{"n": 1, "title": "<source title>", "url": "https://…", "accessed": "2026-09-21"}],
  "markdown_en": "<full English memo markdown>",
  "markdown_zh": "<full Simplified Chinese memo markdown>"
}
```

Rules:

- `decision` must match Section I of both memos; `pass_kind` says which kind of Pass (null for Buy and Too Hard).
- The numbers are plain JSON numbers. Per-share figures are in `currency`. Totals (`earnings`, `d_and_a`, `maintenance_capex`, `working_capital`, `owner_earnings`) are in millions of `currency`, and `diluted_shares` is in millions. Percentages are percent numbers (10 means 10%). With `value_basis` "company" (a private company with no share count), the value range and `buy_price_value` are whole-company values in millions of `currency`.
- Every structured field is optional: leave out (or null) any that does not apply, such as a price for a private company or a share count that is not disclosed. Never invent one to fill the schema. The ones you give must agree with the memo text and with each other (owner's earnings = earnings + D&A − maintenance capex ± working capital; buy price = central value × (1 − required margin of safety)); Python checks the arithmetic.
- `valuation_basis` is "assumed" when the value rests only on assumed inputs; every price is then labelled illustrative, as section VIII says.
- `markdown_en` must include all ten required English headings exactly.
- `markdown_zh` must include all ten required Chinese headings exactly (table below).
- Both memos must be complete investment memoranda, not summaries. Word budget for the English memo: about 2,500–3,500 words when the company has a real disclosed record, and about 1,200–1,800 words when disclosure is thin or the call is Too Hard. The Chinese memo carries the same content.
- JSON must be valid UTF-8. No trailing commentary outside the file.

Also write working copies:

- `memo/buffett_memo.en.md`
- `memo/buffett_memo.zh.md`

identical to the JSON markdown fields.

---

## Chinese Localization Quality Bar

The Chinese memo must read as if a bilingual investment analyst at BSH wrote it, not as a machine translation. Faithful facts do **not** mean literal wording.

- The first person is 我们 (BSH 研究). Never write as Buffett: no 奥马哈 dateline, no 我 speaking for Buffett or Berkshire, and no 我们持有 about Berkshire's shares. Do not switch to 本备忘录认为.
- The Chinese dateline is `BSH 研究 · 巴菲特方法所有者分析 · 价格截至 YYYY 年 M 月 D 日` (`截至……` when there is no price).
- Write for mainland Chinese readers who know finance. Prefer natural research Chinese.
- If an English term has no idiomatic Chinese equivalent, keep the English and add a short gloss on first mention.
- Preserve company names, product names, tickers, acronyms, metrics, numbers, dates, and URLs unless there is a widely used Chinese name.
- Reorder clauses so the Chinese reads naturally.
- Do **not** translate "tailwind" as "顺风". Use "行业利好", "需求侧利好", "结构性利好", "顺势因素", or `tailwind（利好因素）`.
- Do **not** translate "credible second wave" as "可信第二波". Translate the meaning, or keep the English with a gloss.
- Do **not** translate "runway" mechanically as "跑道". Prefer "现金可支撑时间", "增长空间", or `runway（可支撑时间/增长空间）`.
- Do **not** translate "stickiness" as a physical adjective. Use "客户黏性" / "用户黏性" or switching costs.
- "Margin of safety" → 安全边际. "Owner's earnings" → 股东盈余（owner's earnings）. "Circle of competence" → 能力圈. "Too Hard" may stay as Too Hard（超出能力圈） on first mention.
- Moat → 护城河 is acceptable; still explain the economics.
- The illustrative-price label is 示意性，基于假设.
- Keep the same [n] markers and the same numbers as the English memo.

### Section Header Translations (Use Exactly These)

| English | Simplified Chinese |
|---|---|
| Investment Memorandum | 投资备忘录 |
| I. Investment Decision | 一、投资决策 |
| II. The Business | 二、这家企业 |
| III. Circle of Competence | 三、能力圈 |
| IV. Economic Characteristics | 四、经济特征 |
| V. Durable Competitive Advantage | 五、持久竞争优势 |
| VI. Management and Capital Allocation | 六、管理层与资本配置 |
| VII. Financial Position | 七、财务状况 |
| VIII. Intrinsic Value and Margin of Safety | 八、内在价值与安全边际 |
| IX. What Can Go Permanently Wrong | 九、可能造成永久损失的因素 |
| X. Conclusion | 十、结论 |
| Buy | 买入 |
| Pass at today's price (buy at or below X) | 暂不买入（买入价 ≤ X） |
| Pass at any price | 放弃 |
| Too Hard | Too Hard（超出能力圈） |
| What would change the call | 什么情况会改变结论 |

The Chinese `#` title is `投资备忘录 — [公司中文名]`. When a widely used Chinese name exists, write it with the English in brackets, e.g. `台积电（TSMC）`; otherwise use the English name. Put the same name in `company_name_zh`.

---

## Final QA

Before writing `logs/memo_package.json`, confirm:

- The memo reads as BSH Research's owner's analysis using Buffett's method: not as Warren Buffett writing, and not as BSH writing an LP memo in a costume.
- No Omaha dateline, no first-person Berkshire holdings, trades or intentions, no invented quotes or recollections.
- The research step ran before writing, and thin disclosure led to Too Hard only after it.
- Section I states Buy, Pass, or Too Hard in the first two sentences, and a Pass says which kind.
- Circle of competence is an actual judgment, not a throat-clearing paragraph.
- Owner's earnings follow the section IV definition.
- Valuation is a range plus the price we would pay, with the hurdle, the multiple's logic and the required and actual margin of safety; one compact grid at most, never DCF theater.
- Missing numbers were converted into price discipline or Too Hard, not placeholders.
- Section IX contains 3–6 distinct fact → failure → permanent-loss paths,
  not generic categories or a late-stage risk register.
- Section X ends with two to four dated, observable triggers that would change the call.
- No BSH / Serena / LP / SPV / underwriting process language in the body.
- No `.docx` and no renderer scripts were written.
- English and Chinese carry the same facts, the same numbers and the same call.
