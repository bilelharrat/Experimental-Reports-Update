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
pool runs the first max-workers specs immediately and queues the rest, so
the two tail passes always finish last. Keep every pass in
MEMO_SPINE_PIN_FEEDING_PASSES inside the immediate window (the speculative
spine holds its launch for them) and park the most section-local color
passes in the queue — their late arrival is what the delta check is FOR, and
it reads them as additive.

## pass: arithmetic_denominators
```yaml
label: Arithmetic / pressure tests
artifact: pressure_tests.md
```
Pressure-test valuation, contract values, SAFE/SPV economics, revenue
recognition, ARR/revenue proxies, unit arithmetic, and what the disclosed
numbers imply. Build ranges instead of false precision.

## pass: time_base
```yaml
label: Time-base integrity
artifact: time_base_checks.md
```
Date-tag every valuation, round, contract, pipeline, ARR/revenue, funding,
and customer metric. Separate contemporaneous, stale-mark, forward, and
trailing claims.

## pass: growth_bridge
```yaml
label: Growth bridge
artifact: growth_bridge.md
```
Bridge disclosed commercial activity into modeled revenue or value: binding
contracts, cancellable contracts, MOUs, LOIs, pipeline, conversion ranges,
implementation capacity, and recognition timing.

## pass: valuation_comps
```yaml
label: Valuation comparables
artifact: valuation_comps.md
```
Build the comparables set with growth-adjusted multiples, collect precedent
transactions, judge which of the three methods (comps / precedents / DCF-
earnings-power) can be run on the disclosures and why the others cannot, and
derive an implied fair-value range with the arithmetic shown. Translate the
entry price into what growth and margin it already pays for.

## pass: exit_paths
```yaml
label: Exit paths
artifact: exit_paths.md
```
Map the realistic exits: IPO readiness and timing evidence, M&A with named
plausible acquirers and the strategic or antitrust constraint on each,
secondary-market depth for this name, dated catalysts over the next 12-36
months, and the exit-year/multiple scaffolding a scenario table needs
(bear/base/bull exit valuations with dilution assumptions).

## pass: replacement_coexistence
```yaml
label: Replacement vs coexistence
artifact: replacement_vs_coexistence.md
```
Determine whether the company replaces incumbents, coexists as an additive
layer, licenses through incumbents, or depends on standards and ecosystem
adoption.

## pass: competitive_rights
```yaml
label: Competitive compression
artifact: competitive_notes.md
```
Assess competitive compression, IP/patent durability, rights or standards
leverage, defensibility, alternative technical approaches, and what could
reduce pricing power.

## pass: alternative_explanations
```yaml
label: Alternative explanations
artifact: disconfirming_evidence.md
```
Generate the strongest non-bullish interpretations of the facts. Identify
disconfirming evidence, downside sensitivity, and the specific risk or
valuation sensitivities that would change the decision.

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

## pass: deployment_behavior
```yaml
label: Adoption ladder
artifact: adoption_ladder.md
```
Assess deployment depth and adoption maturity by product/use case. Separate
announced, pilot, named production, repeatable production, renewal/upsell,
and broad deployment evidence.

## pass: gtm_operating_burden
```yaml
label: Distribution / GTM
artifact: distribution_notes.md
```
Assess distribution model, customer acquisition path, sales cycle,
implementation burden, budget owner, channel leverage, carrier or enterprise
access, and GTM strain.
