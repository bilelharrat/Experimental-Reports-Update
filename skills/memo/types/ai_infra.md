---
type: ai_infra
label:
  en: AI infrastructure
  zh: AI 基础设施
scorecard:
  late:
    market_size_growth: 12
    industry_position: 15
    moat: 18
    revenue_growth_quality: 15
    business_model_ue: 15
    team_governance: 10
    valuation: 8
    exit_certainty: 4
    risk_reward: 3
  growth:
    market_size_growth: 15
    industry_position: 12
    moat: 18
    revenue_growth_quality: 12
    business_model_ue: 12
    team_governance: 15
    valuation: 8
    exit_certainty: 4
    risk_reward: 4
research_focus:
  all: >-
    This is an AI infrastructure company — the picks-and-shovels layer
    under the industry: silicon, compute cloud and networking, scheduling
    and orchestration, inference acceleration, data and vector pipelines,
    safety evaluation. Read every number through four questions. (1) Which
    track is it? Keep pure-software infrastructure and asset-heavy
    compute/hardware strictly apart, and NEVER let asset resale be scored
    as high-margin SaaS. (2) Neutrality and resistance to absorption: is
    this a neutral layer that takes a toll whichever model wins, or a
    stateless feature that a silicon vendor or a leading open-source
    project absorbs in its next minor release? (3) Real performance and
    TCO advantage: against the incumbent stack, do throughput per million
    tokens, P95 and time-to-first-token latency, and MFU deliver a
    total-cost-of-ownership reduction that cannot be replicated? (4)
    Capacity and order quality: contracted capacity versus delivered
    capacity, backlog versus recognized revenue, top-three customer
    concentration, and how likely those customers are to build the same
    stack in-house.
  market_sizing: >-
    Size each sub-layer separately — accelerator silicon, compute rental,
    inference scheduling middleware, data platforms. NEVER equate the
    industry's trillions of total spend with the TAM. Quantify, in the
    same table, the share incumbents (NVIDIA, the three large clouds)
    already hold in that layer: a TAM that ignores the incumbent's
    existing share is fiction.
  competitive_rights: >-
    Benchmark against NVIDIA's own stack (CUDA, TensorRT, NeMo), the
    hyperscalers' in-house stacks, and the leading open-source engines
    (vLLM, SGLang, Triton). Press hard on switching cost: has the product
    accumulated enterprise data and context gravity (stateful), or is the
    purchase merely a transient response to a compute shortage?
    Look past nameplate specifications at what runs in production:
    prefill-decode separation actually deployed, distributed KV-cache
    sharing and tiered offload efficiency, topology-aware scheduling on a
    ten-thousand-accelerator cluster, sub-second checkpoint fault
    tolerance. For heterogeneous silicon, examine how much real
    throughput the compiler extracts from non-CUDA hardware.
  deployment_behavior: >-
    Keep four levels strictly apart: announced capacity versus capacity
    actually delivered and racked; bookings and backlog versus revenue
    actually recognized; trial workloads versus business-critical
    production workloads. Name the real production customers and disclose
    what share of their core workload genuinely runs on this platform.
  arithmetic_denominators: >-
    Test revenue quality to the bottom: strip out pass-through revenue
    that is simply resold hardware or public-cloud capacity earning a
    margin on the transaction. Software revenue must be stated as pure
    subscription or usage ARR; compute services must convert billed GPU
    hours into true billable utilization after idle time and
    depreciation.
  valuation_comps: >-
    Value the two tracks differently. Pure-software infrastructure is
    calibrated against comparable infrastructure-software companies on
    EV / forward ARR and NRR multiples, with a 70%+ gross-margin
    requirement. Asset-heavy compute cloud and silicon are valued on
    semiconductor and data-centre logic — EV / EBITDA, per-accelerator
    payback period, and net asset value — and stress-tested there.
---
## What this type is
The layer beneath the models: compute acceleration, low-level scheduling and
management, performance optimization and data movement for training,
inference deployment and data workflows. These companies earn by carrying the
industry's model throughput and workloads. The investment question is whether
the company captures a durable systems-engineering advantage or a temporary
supply-demand dislocation.

## Scope and boundaries
- In scope: inference and training acceleration engines, distributed cluster
  scheduling and orchestration, high-performance communication and network
  optimization, KV-cache and vector databases, AI compilers, heterogeneous
  silicon and ASICs, cloud-native GPU compute platforms.
- Out of scope: foundation-model research labs, end-user vertical AI
  applications, outsourced data-labeling operations, traditional
  general-purpose colocation.

## The two-track rule (mandatory)
The memo must decide, in its first section, which track the company is on,
and must never mix the two assessment frameworks:

- **Track A — software infrastructure** (asset-light: SaaS, licence,
  usage-based pricing). Examine: depth of the code, where the open-source
  boundary sits, stateful stickiness, pure-software gross margin (>70%), net
  dollar retention (>130%).
- **Track B — compute and hardware infrastructure** (asset-heavy: bare-metal
  cloud, ASICs, dedicated clusters). Examine: financial leverage,
  per-accelerator payback (under 18-24 months), large-cluster MFU, billable
  utilization, and the impairment risk in hardware residual value.

## Where the case usually lives
- **Systems efficiency that cannot be replicated** — hardware-software
  co-optimization (prefill-decode separation, operator fusion, efficient
  memory reuse) delivering throughput and latency far beyond the standard
  open-source stack on the same hardware, cutting a customer's cost per
  token by 40% or more.
- **A stateful moat** — the product accumulates the enterprise's private
  business data, high-frequency retrieval indexes, context caches or core
  production scheduling state, so replacement is expensive; not a stateless
  proxy layer that can be unplugged at will.
- **Cross-platform neutrality and network** — independent of any single model
  vendor and any single cloud, becoming the enterprise's unified model
  gateway and compute router in a multi-model world.
- **A closed loop on open source** — a genuinely influential open standard or
  developer base driving bottom-up adoption, paired with a clear monetization
  flywheel in closed enterprise features: multi-tenant isolation, high
  availability and disaster recovery, dynamic elastic scaling.
- **Counter-cyclical survival** — a compute cloud whose own networking and
  scheduling software earns a premium, so that when silicon supply loosens
  and rental rates fall it still holds a healthy positive margin on systems
  efficiency alone.

## What the report should favor
- Convert each performance metric into the cash cost advantage it produces
  BEFORE assessing the technical narrative. Reject any benchmark score
  untethered from TCO.
- Test the absorption window explicitly: assume the mainstream open-source
  frameworks (vLLM, PyTorch) or the silicon incumbent (NVIDIA) ship this
  capability for free in their next major release — can the company survive
  independently?
- See through compute arbitrage: a business that leases silicon on high
  leverage and earns the spread, with no communication-scheduling or
  heterogeneous-efficiency software of its own, must NEVER be valued at
  technology-software multiples.
- Separate trial-period enthusiasm from production stickiness: spontaneous
  developer GitHub stars are not the same as the conversion rate into signed
  enterprise architecture purchases.

## Type-specific metrics the sections must carry
- **Systems performance and efficiency**: P95 / P99 latency and
  time-to-first-token; end-to-end concurrent throughput (tokens/s); MFU under
  the real workload; lossless network throughput and packet-loss tolerance.
- **Commercial and retention (software track)**: pure-software ARR and growth
  rate; net dollar retention and gross retention; the net expansion slope on
  usage-based pricing; CAC payback.
- **Operations and assets (hardware / compute-cloud track)**: how much
  installed capacity is actually racked, and billable utilization (%); capex
  and the interest cost of debt financing; per-accelerator payback period;
  revenue share of the top three customers and of the single largest.
- **Delivery and contractual constraints**: irrevocable signed backlog;
  penalty terms for late capacity delivery; supply and allocation guarantees
  (SLAs) from upstream silicon vendors.

## The cost and economics stack (always broken out)
Pick the model that matches the track:

- **Software infrastructure**:
  `ARR − delivery and customer-success cost − hosted cloud resource cost =
  pure software gross margin (must exceed 75%)`
- **Compute cloud / cluster**:
  `compute revenue − server hardware depreciation − power and PUE operations
  − data-centre network bandwidth − in-house scheduling R&D = operating gross
  margin (healthy above 35-45%)`

## Failure modes -> risk areas
- **Competition — squeezed from both sides**: leading open-source inference
  and scheduling frameworks evolve fast, mainstream capability gets
  standardized and packaged, and the startup's closed tooling becomes an
  unmaintained island.
- **Valuation & exit — asset mismatch and impairment (compute cloud)**:
  expensive hardware bought with high-interest debt, then a downstream model
  customer defaults or leaves, or the next silicon generation cuts prices,
  and a large write-down follows.
- **Moat — stateless means zero switching cost**: the tool sits at the edge of
  the call path (API format translation, lightweight prompt debugging), and a
  customer can replace the vendor in a few lines of code.
- **Concentration — the largest customer builds it themselves**: once its AI
  business crosses a threshold, the biggest customer builds its own
  scheduling architecture with a dedicated team and takes more than half the
  startup's revenue with it.
- **Commercialization — paper orders that cannot be delivered**: capacity
  promised at cluster scale but never delivered because of data-centre power
  constraints, liquid-cooling engineering defects or network faults, and the
  orders are cancelled.

## Red flags
- Core code that is essentially a thin wrapper over an open-source library,
  with no proprietary kernels or communication optimization.
- Community download counts and GitHub stars presented as commercial
  traction, while the paid conversion rate into enterprise production is
  negligible.
- Compute-cloud gross margin under 25%, with hardware residual depreciation
  kept out of COGS.
- A single customer above 40% of revenue while that customer is publicly
  hiring engineers for the same infrastructure layer.
- Only ideal-condition peak specifications (peak FLOPS) offered, with a
  refusal to supply measured degradation under mixed context lengths and high
  concurrency.

## Valuation models and exit norms
- **Valuation**:
  - **Pure software**: benchmarked against infrastructure-software leaders
    (Snowflake, Datadog, HashiCorp) on EV / forward ARR, typically 10-20x,
    with a growth premium where NRR exceeds 130%.
  - **Compute assets**: benchmarked against semiconductors and
    next-generation data-centre networking — strictly EV / EBITDA (8-14x), or
    a floor from replacement cost (NAV) and discounted cash flow.
- **Exit paths**:
  - **Independent IPO**: a software-track company needs ARR past $200M while
    holding the Rule of 40; a compute-track company needs stable positive
    EBITDA across a cycle and secured power assets.
  - **Strategic M&A**: the buyers are the three large clouds, the networking
    and silicon incumbents (NVIDIA, Broadcom, AMD) and the large enterprise
    software incumbents. Diligence must state the antitrust resistance each
    plausible buyer would face.
