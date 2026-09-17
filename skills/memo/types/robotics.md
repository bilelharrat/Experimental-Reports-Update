---
type: robotics
label:
  en: Robotics
  zh: 机器人与具身智能
scorecard:
  late:
    market_size_growth: 14
    industry_position: 12
    moat: 14
    revenue_growth_quality: 13
    business_model_ue: 16
    team_governance: 13
    valuation: 8
    exit_certainty: 5
    risk_reward: 5
  growth:
    market_size_growth: 15
    industry_position: 10
    moat: 14
    revenue_growth_quality: 12
    business_model_ue: 16
    team_governance: 16
    valuation: 8
    exit_certainty: 4
    risk_reward: 5
  early:
    market_size_growth: 19
    industry_position: 2
    moat: 9
    revenue_growth_quality: 8
    business_model_ue: 16
    team_governance: 28
    valuation: 8
    exit_certainty: 5
    risk_reward: 5
section_emphasis:
  company_team: 1.15
  business_financials: 1.25
  thesis_market: 1.15
research_focus:
  all: >-
    This is a robotics and embodied-AI company — humanoids, mobile
    manipulators, industrial and logistics embodied equipment, and
    cross-embodiment foundation models (VLA, the "robot brain"). Read
    every number through five questions. (1) Deployment reality: how many
    units actually run continuously on a customer's production floor,
    against what was shown at a launch event, ordered by intent, or
    piloted without payment? (2) True autonomy: look past the staged demo
    and quantify autonomous duration without teleoperated intervention,
    and task success rate. (3) Unit economics and the BOM curve: the slope
    at which bill-of-materials cost falls with volume, price per unit or
    per rented hour, and the customer's payback period. (4) The data
    flywheel and long-tail generalization: the cost of collecting
    real-robot demonstrations, sim-to-real transfer efficiency, and
    self-correction under physical disturbance. (5) Capital intensity and
    manufacturing at scale: the net cash runway needed to build the plant
    and float a fleet, and how much of the critical supply chain the
    company controls.
  market_sizing: >-
    Break the TAM into three nested layers and size each separately: (1)
    displacement of the existing labor pool in the target physical setting
    (worker count × fully loaded annual cost, with a penetration rate);
    (2) displacement of traditional dedicated industrial automation
    (annual replacement spend on AMR/AGV fleets and fixed industrial
    arms); (3) the installed-base market for embodied hardware (expected
    units in service × price or annual fee). NEVER equate the global
    trillion-dollar labor pool with the near-term addressable market.
  competitive_position: >-
    Against the mature incumbents (FANUC, ABB, Geek+ and the automation
    majors), compare reliability, cycle time and total cost of ownership.
    Against the frontier embodied labs (Figure AI, Tesla Optimus, 1X,
    Skild AI, Physical Intelligence), benchmark generalization across
    manipulation tasks, robustness to disturbance, and zero-shot or
    few-shot transfer speed. Then ask: against a dedicated automation cell
    costing a few thousand dollars, how much quantifiable premium does
    this robot's "foundation-model flexibility" actually create for the
    customer?
  adoption_distribution: >-
    Build and verify the six-rung ladder: strategic MOU -> laboratory
    proof of concept -> paid on-site pilot -> small-batch line trial ->
    fleet deployment at scale -> repeat purchase and expansion. Name the
    real customers on the factory floor, and disclose the dwell time and
    conversion rate at each rung; a press release is NEVER an industrial
    deployment.
    Look past the marketing at reliability on a real line: mean time
    between failures (MTBF), mean time to repair (MTTR), end-to-end task
    success rate, and interventions per hour. State plainly whether a
    demonstration video involved remote teleoperation or hard-coded
    trajectories.
  numbers_integrity: >-
    Check the financial and order denominators strictly: separate firm,
    legally binding backlog from non-binding LOIs and MOUs, and both from
    revenue actually invoiced and delivered. Restate any robot-as-a-service
    arrangement as net annual revenue per unit after depreciation,
    maintenance and forward-deployed engineering, with the capital payback
    period shown.
  team_governance: >-
    Hardware plus embodied models demands a compound engineering gene pool.
    Inventory the core team's background across four axes:
    vision-language-action model research, high power-density motors and
    actuators, force control and embedded firmware, and supply-chain
    volume manufacturing. Review progress on the manufacturing site and on
    international industrial safety certification (ISO 10218, ISO/TS
    15066, CE, UL).
  valuation_exit: >-
    Value the three tracks separately. The pure software / embodied-brain
    layer compares to AI infrastructure and foundation models (EV /
    forward ARR, or replacement R&D cost). A full-stack OEM is valued
    against advanced hardware manufacturing and high-end industrial
    robotics (EV / forward revenue, calibrated to hardware gross margin).
    A RaaS operator is discounted conservatively as a high-technology
    equipment-leasing asset (EV / EBITDA or DCF). NEVER apply a
    pure-software SaaS multiple to low-margin, asset-heavy hardware.
---
## What this type is
A company that fuses a frontier multimodal embodied model (vision, language,
spatial geometry, touch) with physical hardware (humanoid, biped, wheeled-leg,
multi-degree-of-freedom arms and dexterous hands) so it can perceive, plan and
carry out complex physical work autonomously in unstructured or
semi-structured environments. Commercially this is the substitution of
expensive, scarce or hazardous human physical labor at the marginal cost of
algorithms and electromechanical systems. The outcome turns on reliability and
autonomy in real working conditions, the BOM cost-reduction curve, and
crossing the supply-chain gulf from laboratory prototype to a thousand units
delivered.

## Scope and boundaries
- In scope: full-stack humanoid and general embodied robots, mobile
  manipulators for unstructured environments, embodied foundation models (VLA
  / robot brains), high-end dexterous hands and actuator assemblies.
- Out of scope: traditional fixed-trajectory industrial robots with no
  intelligence, low-end remote-controlled toys with no autonomous planning,
  pure software with no physical interaction, fixed-route warehouse AGVs with
  no dexterous manipulation.

## The three-track rule (declare before anything else)
The memo must state in its first section which track the company is on, and
must never mix the commercial and financial frameworks:

- **Track A — embodied brain / VLA.** Cross-embodiment general control models,
  monetized as IP licence or per-unit control fees, with no asset-heavy
  manufacturing. Examine: adaptation rate across heterogeneous hardware,
  zero-shot generalization, and the risk that the OEMs close the loop
  in-house.
- **Track B — full-stack embodied OEM.** Proprietary hardware (joints, frame,
  dexterous hands, sensors) plus deeply customized embodied algorithms, sold
  outright or leased as RaaS. Examine: hardware-software co-design, the
  per-unit BOM cost curve, production yield and supply-chain control.
- **Track C — vertical integration and work-as-a-service (RaaS).** Standard or
  assembled hardware built into an end-to-end solution for one setting
  (automotive press tending, solar stringing, surgery). Examine: customer
  payback, the margin erosion from forward-deployed engineers, and how
  exclusive the domain know-how really is.

## Where the case usually lives
- **A closed task loop in a structured setting** — a vertical chosen for high
  fault tolerance, high unit value and the sharpest labor shortage
  (automotive line handling, logistics depalletizing), with task completion
  above 99.5% and each unit replacing 1.5-2 full-time workers.
- **Hardware-software co-design and BOM reduction** — proprietary or
  exclusively sourced joint actuators, reducers and tactile sensors, bringing
  the all-in BOM under ~$30,000 even at hundreds of units, which is what makes
  a 12-18 month customer payback possible.
- **A measurable real-world data flywheel** — an efficient real-robot
  demonstration pipeline and high-fidelity sim-to-real distillation, so that
  as fleet operating hours accumulate, recovery from long-tail corner cases
  improves and the intervention rate falls quarter over quarter.
- **Autonomy that genuinely clears teleoperation** — hours of continuous
  autonomous work without a human in the loop or in line of sight (MTBF above
  ~500 hours), rather than a hidden operator driving remotely.
- **Fleet-level commitment from a lighthouse customer** — paid fleet orders
  from a global automaker, logistics major or top-tier electronics
  manufacturer, and admission to their standard takt time and approved
  supplier list.

## What the report should favor
- Examine in this order: measured reliability on the line and the payback
  arithmetic first, then manufacturing and supply chain, and only then the
  model architecture. Demo video carries the least weight of anything.
- Test for teleoperation: any demonstration video that does not fully disclose
  the state of the control station off-camera, or that hides playback speed
  and cut points, is assessed as non-autonomous.
- See through the order-intent bubble: strip out framework agreements (MOU)
  and letters of intent with no deposit or penalty. Count only cash deposits
  received or production orders with irrevocable breach terms.
- Measure the forward-deployed engineering burden: if delivering five robots
  requires three algorithm engineers resident in the customer's plant for
  months, this is low-margin technical outsourcing and must not carry a high
  multiple.

## Type-specific metrics the sections must carry
- **Reliability and autonomy**: end-to-end task success rate (%); MTBF
  (hours); mean time between interventions; sim-to-real transfer degradation.
- **Hardware and manufacturing cost**: all-in BOM per unit, broken down across
  actuators, silicon, sensors and structure; assembly and test labor hours per
  unit; yield at pilot and at volume (%); share of critical components made
  in-house versus bought.
- **Commercialization and the deployment ladder**: units actually deployed and
  running routinely at customer sites (trial versus production, separately);
  delivered units against announced backlog; customer payback period (months);
  hardware gross margin per unit (%).
- **RaaS operations (where applicable)**: net monthly revenue per unit;
  lifetime maintenance cost and spare-part consumption per unit; field support
  and maintenance cost as a share of revenue; fleet active utilization (%).
- **Safety and compliance**: certification under the human-robot collaboration
  safety regime (ISO 10218-1/2, ISO/TS 15066, CE machinery directive); the
  stop time (in milliseconds) for a loss-of-control event on a shared line.

## The unit economics and delivery stack (always broken out)
Build both chains and mark each key figure "disclosed" or "verified in
diligence":

### 1. Customer ROI and payback
- **Customer's annual net saving**
  - `= [ fully loaded wages and benefits of the workers replaced × units
    replaced (typically 1.5-2.0) ]`
  - `+ [ value of improved quality and reduced scrap ]`
  - − annualized depreciation or rental of the robot
  - − field maintenance, spare parts, power and connectivity
  - − retraining and supervision of the human operators alongside it
  - **Test**: `payback = total purchase and deployment cost ÷ annual net
    saving`. An industrial customer facing a payback beyond 24 months will
    resist expansion hard.

### 2. Per-unit contribution margin
- **Contribution margin per delivered unit**
  - `= net average selling price per unit`
  - − joint actuators, motors and reducers
  - − edge compute (GPU/SoC), lidar, depth cameras and tactile sensors
  - − machined structure, wiring harness, battery and enclosure
  - − assembly, calibration and factory test labor
  - − on-site commissioning and customization (forward-deployed engineering)
  - − first-year warranty reserve and spare-part consumption

## Failure modes -> risk areas
- **Technology — a striking demo with no engineering usability**: near-perfect
  in the lab or showroom, but intervention rates spike on a real floor facing
  changing light, dust, vibration, uneven ground and irregular objects, and
  the units come back.
- **Commercialization — BOM overrun and manufacturing hell**: chasing maximum
  degrees of freedom and exotic sensors drives per-unit materials past
  $100,000 with slow cost reduction, and the price lands far beyond what an
  industrial customer will pay.
- **Commercialization — the systems-integrator trap**: without a generalizing
  embodied brain, every new customer and every new process needs the control
  logic rewritten and engineers resident on site, and delivery cost consumes
  the margin.
- **Competition — low-cost replication**: with no fundamental patent position
  in structure or actuation, the Chinese electromechanical supply chain
  reverse-engineers the unit at a third of the cost and a hardware price war
  follows.
- **Team, governance & regulation — a safety incident**: heavy embodied
  hardware loses control in a mixed human-robot or commercial setting, injures
  a worker or starts a fire, bringing large claims, licence revocation and an
  industry-wide loss of trust.

## Red flags
- Published demonstration video with dropped frames and edit splices, and a
  refusal to provide an uncut continuous take of autonomous work.
- Claimed orders in the tens or hundreds of millions that diligence shows to
  be non-binding strategic frameworks (MOU) or letters of intent with no
  deposit.
- Mean time between interventions under 15 minutes in real conditions, or a
  1:1 safety operator still standing by for an emergency stop.
- Customer payback beyond 36 months, or a selling price below the direct BOM
  cost.
- A team composed entirely of academic researchers, with no supply-chain or
  manufacturing leader who has taken electromechanical hardware to volume.
- No formal functional-safety regime for human-robot collaboration, and core
  joints without third-party mandatory safety certification.

## Valuation models and exit norms
- **Valuation**:
  - **Brain / embodied model (Track A)**: valued as a model lab — the team's
    technical barrier, architectural patents and strategic option value; at
    growth stage anchored on EV / forward licence revenue (12-20x).
  - **OEM and industrial deployment (Tracks B and C)**: benchmarked against
    advanced intelligent equipment, semiconductor production equipment and the
    EV supply chain, priced strictly on **EV / forward delivered revenue
    (3-8x)** or **EV / EBITDA (12-20x)**, adjusted for the share of
    proprietary actuators, hardware gross margin (must exceed 35-45%) and the
    delivery rate against irrevocable orders in hand.
- **Exit paths**:
  - **Strategic M&A**: the buyers are the industrial automation majors (ABB,
    FANUC, Siemens), the large automotive groups defending their own line
    automation (Toyota, BMW, Hyundai), and the technology majors buying the
    embodied team and its perception data.
  - **IPO**: an OEM or systems company must have crossed the volume-production
    and delivery-validation phase — thousands of units delivered a year,
    combined hardware and service gross margin positive, and a credible
    self-funding path in operating cash flow.
