---
type: ai_foundation_model
label:
  en: AI foundation model
  zh: AI 大模型
# Optional per-stage weight overlays (nine keys, sum 100). Absent family
# = stage defaults. v1 proposal for the owner and mentor to tune.
scorecard:
  late:
    market_size_growth: 15
    industry_position: 15
    moat: 17
    revenue_growth_quality: 15
    business_model_ue: 10
    team_governance: 12
    valuation: 10
    exit_certainty: 3
    risk_reward: 3
  growth:
    market_size_growth: 15
    industry_position: 12
    moat: 17
    revenue_growth_quality: 15
    business_model_ue: 10
    team_governance: 15
    valuation: 10
    exit_certainty: 3
    risk_reward: 3
research_focus:
  all: >-
    This is a frontier-model lab. Read every number through four
    questions: Intelligence (is it first-tier on coding, reasoning,
    agentic work — and is the GAP to the next lab growing or shrinking
    across the last 3-4 model generations?), Distribution (who reaches
    the model — consumer app, enterprise API, cloud marketplaces,
    coding tools — and what would customers lose if it vanished
    tomorrow?), Economics (revenue = usage x price, with token prices
    falling 50-70% a year; what is the gross-margin TRAJECTORY, not the
    level, and how much revenue is subsidized inference?), and
    Capital (cash, burn, compute commitments in dollars and years, and
    whether the next round is fundable).
  market_sizing: >-
    Show three market lenses side by side and never collapse them:
    (1) foundation-model / AI-platform spend (Gartner, IDC, Stratpace —
    hundreds of billions), (2) software and IT-services displacement
    (trillions of software budget, a displacement share), (3) labor
    substitution (the labs' own pitch — tens of trillions of wages, a
    penetration share). State which lens the memo adopts for TAM and why
    the other two are shown.
  competitive_rights: >-
    Compare against the frontier set (OpenAI, Google DeepMind,
    Anthropic, xAI, Meta, Mistral, DeepSeek) on capability lead,
    capability-per-dollar, and enterprise API share. Ask: if a rival's
    model were 10% better next quarter, how many customers switch, and
    how fast?
  team_governance: >-
    Research talent is the asset. Count the core research, systems and
    product leaders, note departures in the last 12 months, and answer:
    if the twenty most important researchers left tomorrow, what remains?
  arithmetic_denominators: >-
    Separate consumer subscriptions, enterprise seats, API usage,
    coding-tool revenue and any resale through intermediaries. Convert
    every "annualized run-rate" into what it actually measures (latest
    month x12 or latest week x52) before comparing it to anything.
  valuation_comps: >-
    Always build the chain: entry valuation -> exit-year revenue ->
    exit-year gross margin -> exit multiple -> exit valuation -> MOIC ->
    IRR. A good company is not a good investment if the chain returns
    less than 1.5x.
---
## What this type is
A company whose product is a frontier model and the surfaces that carry it
(consumer app, enterprise API, coding agent, cloud marketplace). Value is
created by intelligence, captured through distribution, and kept only if the
economics survive falling token prices.

## Where the case usually lives
- **Industry position** — first-tier capability on the workloads that pay
  (coding, agentic work, reasoning), measured by enterprise API share and
  by the lead over the next lab across several model generations, never by
  one benchmark. A single generation's lead can be luck; three is a moat.
- **Market size and growth** — the market is real at every lens, but the
  honest number depends on the lens. A memo that shows one lens is hiding
  the others.
- **Revenue growth and quality** — sevenfold growth in months is common in
  this class; the question is how much is organic, how much is subsidized
  inference, and how much runs through intermediaries that can re-route it.
- **Moat** — six layers: research, talent, compute, data, distribution,
  ecosystem. The first three decide who leads; the last three decide who
  wins without leading. Evidence for each layer, not adjectives.

## Type-specific metrics the sections must carry
Frontier position by workload (and its trend); enterprise LLM API share;
annualized revenue by line (consumer / enterprise / API / coding tools);
net revenue retention on enterprise; gross-margin trajectory; inference cost
per revenue dollar; revenue per compute dollar; cash, burn and committed
compute (dollars and years); share of revenue through the top two channels.

## The economics stack (always shown)
Revenue − inference cost − training amortization − cloud/GPU − data and
licensing − serving infrastructure = contribution margin; then − R&D −
S&M − G&A = operating cash flow. State which lines are disclosed and which
are the memo's estimate.

## Failure modes -> risk areas
Technology: the next generation from a rival erases the lead. Competition:
price deflation (token prices fall faster than usage grows). Concentration:
two coding intermediaries or one cloud carry a quarter of revenue.
Commercialization: subsidized inference never reaches margin. Valuation &
exit: the price already assumes the multi-year plan; the only exit is an
IPO at a multiple no software company has held.

## Comparables and exit norms
Comps are the other labs' private marks (state the date and the buyer) and
the hyperscalers' AI revenue multiples; the exit route is an IPO at
software-leader multiples (8-15x forward revenue) — say explicitly what the
entry price assumes about that multiple.
