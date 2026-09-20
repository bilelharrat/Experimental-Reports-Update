---
kind: memo_phase2_passes
---
# Phase 2 analysis passes

One block per pass, in DISPATCH ORDER (the order here is the order the
pipeline launches them — keep the pin-feeding passes first). Each block:
`## pass: <id>`, a yaml fence with `label` (UI thread name) and `artifact`
(the analysis/<file>.md the pass writes), then the pass's research focus
as prose (whitespace is normalized when loaded). Company-type addenda
come from skills/memo/types/<type>.md `research_focus` at run time.

Notes carried over from the code: Dispatch order is execution order: the
pool runs the first max-workers specs immediately and queues the rest.
Keep every pass in MEMO_SPINE_PIN_FEEDING_PASSES inside the immediate
window (the speculative spine holds its launch for them). At eight passes
against a per-run cap of ten subprocesses nothing queues, so no pass
arrives after the spine has drawn its pins — the delta check exists for
the day that changes.

Why eight and not twelve: passes that read the SAME evidence are merged,
so one agent forms one judgment from one reading instead of two agents
splitting it. Passes that read different evidence — or whose job is to
disagree — stay apart. Phase 3 and 4 are the expensive half of a run, so
the saving is real: four fewer agents, four fewer readings.

What the merge did NOT do is cut the evidence, and the original note
here said otherwise. Every pass fills every schema cap it is given, and
the caps are PER PASS, so dropping four passes dropped the finding count
by about a quarter, not by a third: measured on the Surge AI compact run
(2026-09-20__070546), eight passes handed Phase 3 233 findings, against
the "more than three hundred" twelve used to hand it.

That note also justified the cut by the memo those findings had to fill —
"a 3,500-word memo". The compact memo is 20,400 words now. The ratio
inverted, from roughly twelve words of memo per finding to ninety, and
the memo is still not short of evidence: one citation mark every 45-58
words, 17 of 19 sources cited, every calculation note cited, and sections
landing at or slightly over their word budgets rather than under. Eight
is still right — for the merge reason above, not for the ratio.

## pass: numbers_integrity
```yaml
label: Numbers & time-base integrity
artifact: numbers_integrity.md
```
Pressure-test every disclosed number AND date it. Test valuation, contract
values, SAFE/SPV economics, revenue recognition, ARR/revenue proxies, unit
arithmetic, and what the disclosed numbers imply; build ranges instead of
false precision. Then date-tag every valuation, round, contract, pipeline,
ARR/revenue, funding and customer metric, and separate contemporaneous,
stale-mark, forward and trailing claims. Both halves judge the same
figures, so report them together: a number that survives the arithmetic
but carries an eighteen-month-old mark fails this pass exactly as surely
as one that does not add up.

## pass: growth_bridge
```yaml
label: Growth bridge
artifact: growth_bridge.md
```
Bridge disclosed commercial activity into modeled revenue or value: binding
contracts, cancellable contracts, MOUs, LOIs, pipeline, conversion ranges,
implementation capacity, and recognition timing.

## pass: valuation_exit
```yaml
label: Valuation & exit
artifact: valuation_and_exit.md
```
Price the company and say how the money comes back — one pass, because the
exit multiple and the entry multiple are read off the same comparables.
Build the comparables set with growth-adjusted multiples, collect precedent
transactions, judge which of the three methods (comps / precedents / DCF-
earnings-power) can be run on the disclosures and why the others cannot,
and derive an implied fair-value range with the arithmetic shown.
Translate the entry price into what growth and margin it already pays for.
Then map the realistic exits: IPO readiness and timing evidence, M&A with
named plausible acquirers and the strategic or antitrust constraint on
each, secondary-market depth for this name, dated catalysts over the next
12-36 months, and the exit-year/multiple scaffolding a scenario table needs
(bear/base/bull exit valuations with dilution assumptions).

## pass: market_sizing
```yaml
label: Market sizing / TAM
artifact: market_sizing.md
```
Size the market the company actually competes in. FIRST collect every
external estimate you can find — at least three when they exist: syndicated
research houses (Gartner, IDC, Stratpace, Technavio, MarketsandMarkets,
Grand View, Statista ...), the company's own pitched TAM, bank or analyst
sizing — and record for each: who produced it, what it counts (the
definition), the value, the year, the retrieval date, and the URL. NEVER
discard an estimate as unusable because it disagrees with the company's
revenue or with another estimate; keep it and explain the definition
mismatch (a foundation-model-spend figure, a software-displacement figure,
and a labor-substitution figure measure different things and can all be
right). THEN build the memo's own derivation with every input named (base,
growth rate, displacement or penetration factor, and where each comes from)
and reconcile it against the external estimates, stating which definition
the memo adopts and why. Then TAM/SAM/SOM with the derivation method for
each, the market definition and value-chain position, growth drivers with a
supporting datum per driver, the policy/regulatory regimes that constrain or
subsidize the business, and where the ceiling sits ($20B / $100B / $500B
enterprise-value bands). Flag every number the company self-reports versus
independent sizing.

## pass: competitive_position
```yaml
label: Competitive position
artifact: competitive_position.md
```
Settle where this company stands against everyone else who could serve the
same demand. First decide the relationship: does it replace incumbents,
coexist as an additive layer, license through incumbents, or depend on
standards and ecosystem adoption? Then judge whether that position holds:
competitive compression, IP/patent durability, rights or standards leverage,
defensibility, alternative technical approaches, and what could reduce
pricing power. The two questions share a fact base — who the incumbents
are and what they can do — so answer them in one reading rather than two.

## pass: adoption_distribution
```yaml
label: Adoption & distribution
artifact: adoption_and_distribution.md
```
Establish how deeply the product is deployed and what it costs to get it
there — the same customer evidence answers both. Assess deployment depth
and adoption maturity by product/use case, separating announced, pilot,
named production, repeatable production, renewal/upsell, and broad
deployment evidence. Then assess the distribution model, customer
acquisition path, sales cycle, implementation burden, budget owner, channel
leverage, carrier or enterprise access, and GTM strain. Say plainly where a
thin adoption ladder is explained by a heavy distribution burden.

## pass: team_governance
```yaml
label: Team & governance
artifact: team_governance.md
```
Assess leadership track records, key-person dependence, board composition
and independence, ownership and voting control, ESOP, protective provisions,
missing officers (CFO especially), audit history, related-party exposure,
and public-company readiness. State facts with dates; separate verified
history from company-claimed bios.

## pass: alternative_explanations
```yaml
label: Alternative explanations
artifact: disconfirming_evidence.md
```
Generate the strongest non-bullish interpretations of the facts. Identify
disconfirming evidence, downside sensitivity, and the specific risk or
valuation sensitivities that would change the decision. This pass is
deliberately NOT merged into any other: its job is to argue against what
the other passes conclude, and an agent that just built a case is the
wrong one to attack it.
