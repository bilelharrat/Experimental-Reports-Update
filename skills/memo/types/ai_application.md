---
type: ai_application
label:
  en: AI application
  zh: AI 应用
scorecard:
  late:
    market_size_growth: 12
    industry_position: 16
    moat: 16
    revenue_growth_quality: 16
    business_model_ue: 14
    team_governance: 10
    valuation: 8
    exit_certainty: 4
    risk_reward: 4
  growth:
    market_size_growth: 14
    industry_position: 12
    moat: 18
    revenue_growth_quality: 16
    business_model_ue: 12
    team_governance: 14
    valuation: 8
    exit_certainty: 3
    risk_reward: 3
research_focus:
  all: >-
    This is an AI application company — a product built on top of a
    foundation model for one vertical or workflow (legal, enterprise
    knowledge, sales, coding, healthcare, tax and finance). Read every
    number through: category leadership (ARR, named customers, win rate
    against the closest direct competitor); workflow depth (a copilot
    sidebar the model vendor can replace at any time, or a system of
    record that owns the end-to-end task with its data and permission
    integrations?); delivery reliability (the proprietary evaluation
    harness and fault tolerance that carry a product from a 90% demo to
    99.9% enterprise production); pricing model (per seat, per usage, or
    per outcome — and whether revenue per customer expands or shrinks as
    the product moves from assisting people to replacing them); retention
    (net revenue retention, gross retention, pilot-to-production
    conversion); and model dependence (true software gross margin after
    inference and model cost, and what defence exists when the model
    vendor's next generation arrives).
  market_sizing: >-
    Break out two budgets quantitatively: the enterprise software (IT)
    budget that already exists for this workflow, and the labor or
    outsourcing spend (compensation budget) the product replaces or
    augments. Treat the model vendors' own vertical applications and the
    incumbent SaaS vendors' embedded AI features as competing claims on
    the same spend.
  competitive_position: >-
    Compare line by line against the vertical incumbents, the model
    vendors' own applications, and the two nearest startups — on ARR,
    named customers, win rate and price. Then examine what the product
    has that a general model vendor cannot erase in its next minor
    release: complex business-logic state machines, private system
    connectors, deep domain compliance and trust.
  adoption_distribution: >-
    Track the enterprise ladder: proof of concept -> departmental trial ->
    enterprise-wide deployment -> core system of record. Report the
    pilot-to-production conversion rate and the average time it takes,
    how usage per customer trends over time, and retention and expansion
    among customers already in production.

    Measure sales efficiency by segment (CAC payback, magic number).
    Establish whether growth is product-led or leans heavily on
    enterprise direct sales. Look through each deployment to the
    customization and implementation burden behind it (forward-deployed
    engineering and services cost).
  valuation_exit: >-
    Use vertical SaaS and next-generation enterprise application software
    as comparables, on EV / forward ARR adjusted for growth and net
    revenue retention. The exit analysis must state what ARR scale and
    what gross margin the valuation already assumes.
---
## What this type is
A product that wraps foundation-model capability inside a specific business
workflow and is paid for a definite business outcome — legal drafting,
enterprise knowledge, code generation, sales automation, clinical
documentation. The underlying model is replaceable infrastructure; the value
accumulates in workflow gravity, the context and permission system, domain
data and distribution.

## Scope and boundaries
- In scope: vertical or horizontal agents, enterprise workflow applications,
  B2B and B2C AI-native software.
- Out of scope: general foundation models, AI compute and infrastructure,
  hardware robots, consumer tools with no retention.

## Where the case usually lives
- **Irreversible workflow embedding** — the default interface for an
  employee's daily work and the system of record for its data, so the cost of
  moving out is high and the habit is sticky.
- **Category winner** — dominant mindshare and reference customers in one
  vertical, with a materially higher win rate (above 60%) than comparable
  startups.
- **High-quality revenue expansion** — ARR growth with NRR above 120% and a
  pilot-to-contract conversion rate above 60%, where revenue compounds with
  the customer's usage or work volume rather than being capped by seats.
- **Software-grade margin control** — dynamic multi-model routing, distilled
  small models of its own and caching, holding true gross margin at 70-80%
  after model and inference cost once the business scales.
- **Production-grade engineering reliability** — a vertical-specific
  evaluation harness and deterministic checks that push task completion and
  accuracy past 99%, enough for enterprise compliance and audit.

## What the report should favor
- Examine in this order: retention and true gross margin first, then
  commercial efficiency, and only then the technical implementation. Never
  treat "model performance" as the application's moat.
- The central test: if the underlying model drops 90% in price, or takes a
  large capability jump, is this product enabled or erased?
- Rule out thin wrappers, and consulting work dressed up as high-margin SaaS.
- Argue explicitly that the billing mechanism fits customer value over the
  long run: when the agent removes human hours, how does the company hold and
  raise average contract value?

## Type-specific metrics the sections must carry
ARR and year-on-year growth; net revenue retention and gross retention;
customer counts by segment (especially $100k+ and $1M+ ARR accounts);
pilot-to-production conversion and churn; AI-adjusted gross margin after
model API and inference spend; CAC payback; competitive win rate against the
key rival; model dependence (single-vendor token spend as a share of COGS,
and whether adaptive model routing exists).

## Failure modes -> risk areas
- **Competition — absorbed from above**: the model vendor ships the same
  capability; the incumbent SaaS giant bundles it free into its installed
  base.
- **Commercialization — seat cannibalization**: on traditional per-head
  pricing, the efficiency the product creates lets the customer cut headcount,
  and the seat count falls off a cliff.
- **Technology — the reliability trap**: a striking demo whose accuracy stalls
  at 90% in enterprise production, until a hallucination or compliance
  incident triggers concentrated cancellations.
- **Commercialization — margin collapse**: heavy dependence on an expensive
  closed model API, inference cost rising linearly with usage, and no scale
  economics.
- **Commercialization — services disguised as SaaS**: large customers are met
  with implementation and custom-development headcount, and margin and
  delivery time deteriorate quickly.

## Red flags
- More than 80% of the core capability is reproducible with a well-written
  prompt in a general model interface.
- Pilot conversion below 30%, or engagement decaying sharply within 90 days
  as the novelty passes.
- Uncapped usage subscriptions where a heavy user is gross-margin negative.
- Non-recurring custom development, consulting and integration persistently
  above 25% of revenue.
- No support for enterprise permission isolation, compliance audit trails
  (SOC 2, HIPAA) or private / VPC deployment.

## Comparables and exit norms
Comparables are vertical professional SaaS (Veeva, Procore) and AI-native
high-growth enterprise software peers, calibrated on EV / forward ARR against
growth (Rule of 40/60) and NRR. The exits are a defensive acquisition by an
industry incumbent, a strategic platform acquisition, or an IPO once ARR
passes $250-300M with a credible path to healthy free cash flow.
