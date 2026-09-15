---
type: ai_infra
label:
  en: AI infrastructure
  zh: AI 基础设施
research_focus:
  all: >-
    This is an AI infrastructure company — chips, inference clouds, data
    platforms, training data, orchestration software: the "picks and
    shovels" layer. Read every number through: Neutrality (does it win
    whichever model wins, or does it depend on one lab or one cloud?),
    Volume (tokens, GPU-hours, workloads, or data rows served — and the
    growth rate), Unit cost and performance versus the incumbent
    (NVIDIA / the hyperscalers) per unit of work, Gross-margin uplift as
    volume scales, and Customer concentration (how much of revenue sits
    with the top three customers, and are they also potential competitors).
  market_sizing: >-
    Size the layer the company actually sells into (inference compute,
    data platform spend, annotation) with independent house estimates,
    then show how much of that layer the incumbent already captures; a
    TAM that ignores NVIDIA's share is not a TAM.
  competitive_rights: >-
    Benchmark against the incumbent on cost per unit of work, latency,
    and availability, and against the hyperscalers' own silicon. Ask
    whether the customer's switching cost is real (software stack, CUDA,
    data gravity) or one procurement cycle away.
  deployment_behavior: >-
    Distinguish announced capacity from delivered capacity, bookings from
    revenue, and pilots from production workloads. Name the largest
    production customers and what share of their workload runs here.
  arithmetic_denominators: >-
    Reconcile bookings, backlog, contracted capacity and recognized
    revenue; convert capacity commitments into the capital they require
    and the utilization they assume.
  valuation_comps: >-
    Comps are semiconductor and infrastructure-software peers on EV /
    forward revenue and EV / gross profit; the exit chain must state the
    utilization and gross margin the exit multiple assumes.
---
## What this type is
Companies that sell compute, data, or the software that runs AI workloads —
accelerators and foundries, inference clouds, data lakehouses, annotation
and evaluation services, GPU orchestration. They earn on volume, so the
case is about whether volume comes to them and what margin survives.

## Where the case usually lives
- **Market size and growth** — the compute and data layers grow with every
  model generation; the question is which slice the company can serve and
  what the incumbent already owns.
- **Business model and unit economics** — gross margin per unit of work and
  its trajectory as volume scales; capital intensity (owned versus rented
  capacity); utilization.
- **Industry position** — neutral supplier to many labs and clouds versus
  captive supplier to one; delivered capacity versus announced capacity.
- **Moat** — switching costs in the software stack, data gravity, supply
  agreements (foundry, HBM, power), and ecosystem lock-in. Say which are
  contractual and which are habits.

## Type-specific metrics the sections must carry
Units of work served (tokens, GPU-hours, workloads) and growth; cost and
latency per unit versus the incumbent; gross margin and its trend; capex
and committed capacity (dollars, years, financing); utilization; top-3
customer share; net revenue retention; supply agreements and their terms.

## Failure modes -> risk areas
Concentration: three customers or one cloud partner carry most revenue and
can build in-house. Technology: the incumbent's next generation resets
cost-per-work; a model architecture shift strands specialized silicon.
Commercialization: capacity is announced but not delivered, or delivered
but not utilized. Market: inference demand shifts to the hyperscalers' own
chips. Valuation & exit: the price assumes utilization and margin that
have never been reported.

## Comparables and exit norms
Public semiconductor and infrastructure-software peers on EV / forward
revenue and EV / gross profit; exits are IPOs or acquisitions by a
hyperscaler or incumbent — name the plausible acquirers and the antitrust
constraint on each.
