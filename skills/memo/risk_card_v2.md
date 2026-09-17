## Risk Register Format Contract (hard requirement — validated before rendering)

The risk section presents risks as PER-RISK CARDS, not one wide risk
table. Structure, in order:

1. One short intro paragraph naming where the risk really concentrates —
   which single risk carries the thesis.
2. 4-6 risk cards. Each card is exactly two consecutive blocks:
   - a `heading` block (level 3) whose text is
     `{"en": "Risk N: <verdict sentence>", "zh": "风险 N：<结论句>"}`.
     The sentence is a COMPLETE PREDICATION with a finite verb that
     states the judgment — "Risk 1: The entry price already assumes
     success — ordinary execution earns nothing." Never a topic label
     ("Entry price"), never a naked statistic. Use the pinned risk
     summaries verbatim: the spine writes them in this form.
   - a `table` block with `component: "risk_register"`,
     `"layout": "key_value"`, `"headers": []`, and EXACTLY these eight
     two-cell rows (label cell first, content cell second). The first
     three rows are the reader's one-glance answer — which aspect, the
     verdict, how big — and the fourth is the explanation:
       1. `Risk Type` / `风险类型` — the area the pin sheet files the
          risk under, as its label: Market / Technology / Competition /
          Moat & defensibility / Commercialization / Concentration /
          Team, governance & regulation / Valuation & exit (Chinese
          市场 / 技术 / 竞争 / 护城河与壁垒 / 商业化 / 集中度 /
          团队、治理与监管 / 估值与退出). Not a sentence.
       2. `Verdict` / `一句话结论` — the pinned risk summary VERBATIM:
          one plain sentence with at most one number.
       3. `Impact` / `影响有多大` — the pinned impact VERBATIM: what the
          risk costs the investment, with the one number that sizes it.
       4. `Why it matters` / `为什么重要` — the explanation, written for
          a senior investor who has never seen this company, the way a
          professor walks a student through it: the fact, then why that
          fact is a problem, then what it costs, in that order. Every
          number is introduced by what it measures BEFORE it appears
          ("the sellers are discussing a price of $1.75T; that is about
          9 times the $190-200B of revenue the company plans for 2028"),
          the arithmetic is shown in-line ("2.6T divided by 1.75T is
          1.5x"), and each comparison names the rule it is judged
          against ("below our 1.5x hurdle"). Never a chain of figures
          the reader must decode; never a fact-to-conclusion jump with
          the middle step missing. End with the "so what" for the
          return in one sentence.
       5. `What we watch` / `跟踪信号` — 1-2 observable leading
          indicators, named and dated where possible. A signal, never an
          instruction to confirm or obtain something.
       6. `Mitigation` / `缓释措施` — the real mechanism that reduces
          this risk: a company action underway, a deal-structure term,
          or position sizing. When none exists, write exactly
          "No structural mitigation exists. <consequence>" — honesty
          over invention.
       7. `Likelihood` / `可能性` — `"High|Medium|Low: <short reason>"`
          (Chinese `"高|中|低：<简短理由>"`), grounded in evidence.
       8. `Risk Rating` / `风险评分` — `"N/10: <short reason>"`,
          impact-weighted importance to the case (Likelihood carries
          probability). 9-10 could break the case alone; 7-8 pushes the
          outcome well below the current path; 5-6 meaningful but
          monitorable; 3-4 limited; 1-2 minor.
3. Order the cards by Risk Rating, highest first. Use 4-6 cards selected
   from the evidence; omit irrelevant categories instead of filling a
   quota.
4. Keep the disconfirming-evidence treatment and the downside scenario
   as separate blocks after the cards, connected to the highest-rated
   risk.

The section's fixed numbered subsection headings (the subsection
scaffold below) wrap this structure: the intro paragraph sits under
subsection 1, all cards under the "Risk cards" subsection, and the
disconfirming evidence and downside/verdict passages under their own
subsections. Card headings stay level 3 beneath the level-2 subsection
headings.

Card prose style: short declarative sentences; concrete nouns and
numbers over abstractions; never "furthermore", "moreover", "notably",
"it is important to note", or symmetrical templated phrasing.
