---
type: ai_foundation_model
label:
  en: AI foundation model
  zh: AI 大模型与前沿实验室
scorecard:
  late:
    market_size_growth: 12
    industry_position: 18
    moat: 18
    revenue_growth_quality: 12
    business_model_ue: 12
    team_governance: 12
    valuation: 8
    exit_certainty: 4
    risk_reward: 4
  growth:
    market_size_growth: 15
    industry_position: 15
    moat: 15
    revenue_growth_quality: 12
    business_model_ue: 10
    team_governance: 18
    valuation: 8
    exit_certainty: 3
    risk_reward: 4
research_focus:
  all: >-
    This is a frontier-model lab. Read every number through four
    questions. (1) Intelligence and systems efficiency: is it first-tier
    on hard reasoning, coding and agentic workloads; does cluster MFU
    (model FLOPs utilization) meet the bar; and across the last 2-3
    generations is the lead WIDENING or being closed by open-weight and
    peer models? (2) Distribution and stickiness: who pays and who comes
    to depend on it — consumer subscriptions, enterprise API developers,
    or a cloud or coding tool that wraps the model as a middle layer —
    and what would a customer irreversibly lose if the model went dark
    tomorrow? (3) Real economics: token prices deflate 50-70% a year, so
    is the company subsidizing inference or does it hold a genuine
    advantage in hardware utilization and distillation cost? The
    gross-margin TRAJECTORY, not any single period, is the line between
    living and dying. (4) Compute and capital runway: net cash, hard
    compute commitments in years and dollars, burn multiple, and whether
    the next enormous round is actually financeable.
  market_sizing: >-
    NEVER merge the lenses. Show all three TAM layers side by side,
    quantified, and state which one the memo adopts as its base: (1)
    direct software spend on foundation models and AI platforms (hundreds
    of billions); (2) displacement of traditional enterprise IT
    infrastructure and software budgets (trillions of software spend —
    estimate the displacement rate); (3) substitution of knowledge work
    and outsourced services (tens of trillions of knowledge-worker
    compensation — estimate the penetration rate). Explain how the three
    nest, and why the labor pool cannot be treated as near-term ARR
    headroom.
  competitive_position: >-
    Benchmark against the global first tier (OpenAI, Anthropic, Google
    DeepMind, Meta, xAI, DeepSeek and peers) on real-task win rate,
    intelligence per dollar per million tokens, enterprise API share, and
    the pace of multimodal post-training. Then press the question: if an
    open-weight model next quarter reaches 95% of today's closed
    commercial model, how much pricing power survives and how much
    friction actually holds customers in place?
    Look past the public leaderboards at the engineering underneath a
    ten-thousand or hundred-thousand-accelerator cluster: model FLOPs
    utilization (MFU), how long a checkpoint restart costs after a
    failure, topology-aware scheduling. On the inference side, does the
    company run prefill-decode separation, KV-cache sharing across nodes,
    speculative decoding and mixed-precision serving — and what does the
    resulting all-in cost-per-token curve look like over time?
  team_governance: >-
    The core researchers are the only truly durable intangible asset.
    Inventory the top twenty algorithm researchers, systems architects and
    inference-optimization leads: technical background, equity vesting,
    non-compete status. Record core attrition over the last 12 months.
    Examine the governance structure — any for-profit/non-profit two-tier
    arrangement, public-benefit-corporation status, and where the board's
    control over commercialization strategy sits and where it has split.
  numbers_integrity: >-
    Strip the water out of revenue: separate consumer subscriptions,
    per-seat enterprise contracts, uncommitted API usage, long-term
    commitments, and any related-party resale through a cloud provider or
    strategic investor. Every "annualized revenue" or "run-rate ARR"
    figure must be restated to the actual measurement window it came from
    (latest month x12, or latest week x52), on a cash basis with
    discounts and subsidies identified rather than netted away.
  valuation_exit: >-
    Refuse a single static multiple. Build three probability-weighted
    scenarios (bull / base / bear) and run the full chain for each: entry
    valuation -> forward exit ARR -> steady-state free-cash-flow rate ->
    exit multiple -> exit return (MOIC and IRR). Also compute a
    replacement-cost floor (discounted installed compute + proprietary
    engineering assets + the cost of rebuilding the top research team) as
    the downside cushion under the valuation.
---
## What this type is
A company that trains its own general or domain frontier base model on a
frontier deep-learning stack (pre-training + reinforcement-learning
post-training + inference-time compute scaling), and captures value through
consumer surfaces, a developer API, enterprise private-cloud delivery and
agent runtimes. The technology is the foundation; the commercial outcome is
decided by compute-engineering efficiency and distribution moat.

## Scope and boundaries
- In scope: general large language models (LLM), frontier multimodal models
  (LMM), AGI labs, full-stack proprietary base-model platforms.
- Out of scope: thin application wrappers over someone else's model,
  fine-tuning workflow software with no model of its own, pure third-party
  GPU resale or hosting, consumer content-creation tools.

## Where the case usually lives
- **Peak intelligence and sustained cadence** — consistently first tier
  worldwide on hard reasoning, long-horizon agentic workflows and
  high-quality code generation, with the lead holding across two or more
  model generations. One generation's lead can be luck; a sustained one
  proves an organizational flywheel rather than a single spike.
- **Systems-engineering efficiency** — on the same silicon, industry-leading
  cluster MFU (above ~45%) and fault tolerance, so a model of the same
  parameter scale costs materially less to train and serve than peers.
  That is the cost card that survives a token price war.
- **Distribution gravity and the developer network** — millions of active
  developers and tens of thousands of enterprise integrations, with the
  model as the default architecture inside business-critical flows, so the
  ecosystem's complements hold customers in place.
- **Proprietary data and the post-training flywheel** — automated formal
  verifiers, process reward models (PRM) and proprietary
  environment-interaction data pipelines, which end the dependence on an
  exhausted supply of clean public corpora.
- **Capital and a strategic compute alliance** — low-cost guaranteed
  compute, priority chip allocation and joint go-to-market distribution
  from a hyperscaler or a leading silicon vendor.

## What the report should favor
- Keep the order: first whether the company is at the table, then whether
  it wins, and only then the unit economics. Be fair about heavy early
  capex and accounting losses, but insist on the rate at which compute
  spend converts into commercial value.
- Reject any claim resting on a public static leaderboard. Prefer private
  dynamic adversarial evaluations, industrial code generation, and
  closed-loop real-task win rate against the state of the art.
- Examine the middle-layer interception risk specifically: do the major
  downstream customers call the native API, or reach it through an
  aggregation or routing framework? If the model gets cheaper or faster
  tomorrow, does the customer relationship stay with the company?
- Keep "disclosed fact", "our own derivation" and "management narrative"
  visibly apart, and date-stamp the key operating numbers with their
  confidence range.

## Type-specific metrics the sections must carry
- **Technical and systems**: real win rate on private adversarial
  evaluations; MFU (%) on large-cluster training; mean time lost to an
  interrupted epoch and checkpoint recovery; inference latency (TTFT and
  inter-token latency); lossless retrieval recall across the context
  window.
- **Commercial and revenue**: true annualized revenue split by line
  (subscription, API, custom enterprise deployment); net revenue retention
  on the enterprise API; blended realized price per token and the
  gross-margin trend; concentration of the top five customers and the top
  two distribution channels (%).
- **Capital and compute**: net usable cash and monthly net burn; runway in
  months; total irrevocable compute purchase and cloud lease commitments in
  years and undiscounted dollars; incremental ARR per dollar of R&D compute
  consumed.
- **Organization and talent**: retention of the authors behind the core
  papers and technical reports; how competitive compensation and equity are
  for systems and research roles; the effect a key-person departure would
  have on the next model's delivery schedule.

## The economics stack (always shown)
Build and show this chain, marking each line "disclosed" or "our estimate":

- **Gross revenue**
  - − inference hardware and cloud COGS
  - − amortization of training capex and leases
  - − data licensing and synthetic labeling
  - − serving infrastructure, availability, ingress and egress
  - **= contribution gross margin**
  - − core algorithm and systems R&D compensation
  - − uncapitalized exploratory training compute
  - − developer ecosystem and channel concessions
  - − operations, legal, compliance, safety alignment and red-teaming
  - **= operating cash flow (or burn)**

## Failure modes -> risk areas
- **Technology — research stall and open-weight catch-up**: progress plateaus
  and the flagship model fails to open a visible gap over the next
  open-weight generation, so the premium API business falls off a cliff.
- **Valuation & exit — compute debt**: multi-year, expensive, irrevocable GPU
  leases signed at the top of a shortage become a fixed-cost millstone once
  efficiency improves or rental rates fall.
- **Concentration — channel interception and becoming a dumb pipe**: with no
  direct consumer or enterprise workflow surface of its own, the company
  degrades into invisible back-end compute, bought in bulk at low prices by
  clouds and aggregation layers.
- **Commercialization — funding stops**: commercialization lags, the next
  round cannot be raised at the expected mark before the capex is spent, and
  a protective liquidation or a punishing down round follows.
- **Team, governance & regulation — loss of the core brains**: strategy
  disagreements, disputes over the pace of commercialization or aggressive
  poaching take out the team behind the key architectural breakthroughs, and
  the research flywheel stops.

## Red flags
- Leaning only on published static academic benchmarks while refusing to
  supply blind A/B win rates from customer production environments.
- A large claimed ARR whose substance is related-party purchasing by
  strategic shareholders, compute barter arrangements, or "activity" bought
  with large free allowances and subsidies.
- Negative contribution margin on inference that fails to converge — margin
  that gets worse, not better, as volume scales.
- A single irrevocable hardware or cloud agreement so large that its breach
  penalty alone would exceed cash on hand.
- A cluster of senior researchers or systems engineers leaving in the last
  six months with no equivalent hiring behind them.

## Valuation models and exit norms
- **Three scenarios**:
  - **Bull (AGI / dominant-platform path)**: the frontier lead holds and the
    company occupies the underlying operating-system position — 25-40x
    forward recurring revenue, or priced as critical infrastructure.
  - **Base (oligopoly path)**: coexistence with two or three closed-source
    peers, margin converging to 60-70%, calibrated to the global
    software/platform leaders (10-18x forward ARR).
  - **Bear (open-source commoditization / pipe)**: the intelligence premium
    fades and the company retreats to a vertical or is valued on the
    replacement cost of its compute, plus discounted technical IP.
- **Exit paths**: a frontier lab is usually too large for an ordinary
  industrial acquirer, so the realistic routes are a strategic absorption by
  a trillion-dollar technology company if antitrust allows, or an IPO at a
  hundred-billion-dollar-plus valuation. The entry price must be shown,
  under the probability-weighted model, to leave at least 3-5x of value
  appreciation.
