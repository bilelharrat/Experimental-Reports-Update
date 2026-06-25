---
name: bsh-investment-memo-latestage-v1
description: "Generate Berkeley Summit House (BSH) investment memos (.docx) for growth, late-stage, and pre-IPO companies, using the V3 formatting-enhanced, non-linear, falsification-first framework with versioned, non-destructive run storage and professional document packaging. Produces two parallel .docx files per run — one in English and one in Simplified Chinese (简体中文) — with identical structure, identical analytical content, and CJK-safe typography in the Chinese version. The final deliverable is an exec-ready LP-facing sell-side investment memo, not a buyer-side diligence memo or BSH internal allocation note. Trigger whenever Serena asks to evaluate an allocation opportunity, write up a growth-stage or pre-IPO company, create an investment memo for a financing round, or analyze a Pitchbook / CB Insights summary for a growth, late-stage, or pre-IPO company."
---

# BSH Investment Memo Generator (Growth / Late-Stage / Pre-IPO, Non-Linear, Versioned, Non-Destructive, Formatting-Enhanced)

## Purpose

Generate a professional investment memo for Berkeley Summit House (BSH) that allows the three co-founders to evaluate a **growth-stage, late-stage, or pre-IPO deal** asynchronously. The memo synthesizes all available inputs — Pitchbook / CB Insights summaries, partner notes, public filings, pricing benchmarks, procurement data, company materials, and independent research — into a clear, structured Word document with a recommendation and explicit ask.

**Scope:** This skill is for priced or otherwise institutionally sponsored growth financings, late-stage rounds, secondary opportunities, and pre-IPO companies. Do not use it for angel, seed, or pre-product deals. For Series A/A2 and early-growth opportunities, run the memo with stage-calibrated expectations rather than imposing pre-IPO disclosure norms.

This version is a **true superset** of the Phase 1 prototype, scoped to growth, late-stage, and pre-IPO:
- It preserves the full execution spine and memo-generation workflow.
- It upgrades the analysis layer to a non-linear, falsification-first system.
- It adds run-folder versioning and strict non-destructive storage rules.
- It enforces a formatting-enhanced document packaging contract (cover page, callouts, tables, page numbers, style system).
- It assumes the depth of analysis appropriate for growth-stage, late-stage, and pre-IPO investment decisions and produces a stable, comparable memo structure.

---

## Human Executive Memo Voice Contract

The analytical artifacts are internal working material. The final memo is the decision document.

Write the final English memo like a senior BSH investment partner would brief IC after live diligence:
- decisive, not exploratory
- fluent, not template-driven
- judgment-led, not process-led
- grounded in evidence, but expressed as conviction under uncertainty
- written in first-person sponsor voice when stating our view, access, conviction, and action

Convert evidence into partner-level conclusions. Do not narrate how the analysis was performed. Do not reproduce confidence scaffolding, methodology notes, task labels, validation language, reviewer prompts, or research workflow language in final body prose.

If the Serena memo packet includes selected operator narrative choices, use them as human-in-the-loop guidance for:
- the intro stance in the Executive Summary,
- the risk-section posture and lead risk,
- the conclusion / Investment View posture.

These choices are source-backed direction, not copy-paste text. Integrate them into natural IC prose and override them only when the evidence directly contradicts the selected posture.

Make statements directly. Do not write about the memo as an object, do not
narrate what the memo/document/section/analysis does, and do not use
writer-process phrasing.

Avoid meta-commentary about the document itself:
- do not write memo/document/process narration, analysis-process narration, or writer-process language
- do not write detached third-person constructions for the investment call; recommendation, access, base case, and action sentences need a first-person sponsor subject or a direct investment-case subject
- use first-person sponsor language instead: "we believe", "we are being offered", "we recommend", "we would proceed if", and "we would revisit if"
- do not explain uncertainty with phrases like "due to lack of data" or "this implies false precision"
- state uncertainty directly: "Revenue is not disclosed", "contracts are not revenue-recognized", "pipeline is early-stage"

Open with the sponsor thesis: why we care about the category, why the timing matters, why this company is shaping the layer or market that matters, and why we want exposure. Then explain technical proof, commercial proof, and the SPV / round mechanics.

Express closing conditions as expected bars, not questions. Replace question-form bullets with expected-bar statements: "The investment case is supported if final A2 terms, closing timing, SAFE conversion, and the binding-contract split remain within the disclosed range."

Do not use legal-rights shorthand in operating tables. Translate it into economic meaning: "The SPV offers limited direct governance and reporting; the manager controls investor-level decisions as a single block."

Do not use buyer-side underwriting vocabulary in final prose or tables: no
"underwrite", "underwriting", "underwritten", "before underwriting", "before
we underwrite", or "right way to view the underwriting". Use investment-case
language instead: "we give credit to", "our base case credits", "the
investment case rests on", "the valuation is supported by", or "we proceed
once the evidence is confirmed." Do not use writer-process framing such as
"we frame it as", "we frame the market", or "the framework"; state the
investment conclusion directly. Do not write imperative diligence commands
such as "Require X before underwriting"; write active expected bars such as
"We proceed once X is confirmed" or "Our base case gives credit after X is
confirmed."

Concrete positive writing patterns:
- Opening: "We invest behind physical-world infrastructure that makes people safer and more capable. ZaiNar matters because accurate network-side positioning is becoming a control layer for defense, industrial automation, logistics, and Physical AI."
- Transaction: "We are being offered SPV exposure to a SAFE expected to convert into the A2 at an effective entry near $2.55B after the discount, subject to confirming the final A2 terms and conversion mechanics."
- Recommendation: "We recommend proceeding if the binding-contract split, final A2 terms, SAFE conversion mechanics, and closing evidence confirm the current investment case."
- Revisit trigger: "We would revisit if the A2 prices materially below the current mark, slips beyond the expected closing window, or the binding contract figure is not large enough to support the valuation."
- Evidence gap: "Revenue is not disclosed; our base case uses binding contract value, implementation timing, and conservative conversion ranges rather than treating pipeline or MOUs as revenue."
- Risk: "Key risk centers on whether signed commercial interest converts into repeatable deployments quickly enough to support a $3.0B valuation."

Rejected language categories:
- detached third-person recommendation or opportunity framing
- memo/document/process narration
- analysis-process narration
- passive sponsor/counterparty capability speculation
- legal-rights checklist shorthand in operating tables
- uncertainty apologies instead of direct evidence treatment

Banned phrase / rewrite guidance:

| Avoid | Prefer |
|---|---|
| The investment case is not that... | This is not a conventional SaaS case. |
| The principal risk is that... | Key risk centers on... |
| Detached recommendation framing | We recommend... / We would proceed if... |
| Detached opportunity framing | We are being offered... |
| Detached base-case framing | Our base case gives credit for... |
| Memo/document/process narration | Remove the frame; make the investment statement. |
| Analysis-process narration | State the conclusion directly. |
| Uncertainty apology | State the disclosed and undisclosed facts directly. |
| Detached decision label | Investment Decision / We recommend... |
| Sponsor-capability speculation | The expected bar is... / The investment case is supported if... |
| No voting or information rights | The SPV offers limited direct governance and reporting; the manager controls investor-level decisions. |
| underwrite / underwriting | give credit to / investment case / valuation support |
| before we underwrite... | before we give full credit to... / once confirmed |
| the right way to view the underwriting | the investment case rests on... |
| We frame it as... | State the conclusion directly without writer-process narration. |
| Require X before underwriting | We proceed once X is confirmed. |
| False precision | State the evidence range without over-modeling it. |
| not treated as ARR | not revenue-recognized |
| commercial momentum is material, but... | The pipeline is large but not contractually binding. |

**Sell-side register (enforced automatically).** This is an LP-facing,
exec-ready sell-side investment memo, not an internal IC, buyer-side diligence
checklist, or BSH internal allocation note. Write every deal mechanic,
governance point, and recommendation as plain narrative prose describing what it
means economically for investors. Say that a valuation rests on or is supported
by specific evidence; that a structure offers limited governance, reporting, or
oversight; and frame the decision as a clear recommendation with stop-or-revisit
conditions. Describe SPV, SAFE, and round economics as plain deal mechanics,
never as legal-rights or diligence-checklist terms. Do not write `MFN`,
`down-round protection`, `information rights`, `voting rights`, `named lead`,
`named institutional lead`, or `governance at the LP level` in the final memo;
translate the economics into plain investor language.

For Wisdom-sponsored opportunities, write in a Wisdom / BSH sponsor register:
"we invest", "we want to be in the room", "we are participating through the
SPV", and "we recommend proceeding if...". Do not describe the sponsor,
investors, or recommendation from a detached third-person vantage point unless
identifying a legal counterparty.

The final memo reads like an experienced investor explaining the opportunity: here is what is happening, what must be true, what can go wrong, and what would make the investment attractive or unattractive.

---

## Analytical Standard: Falsification First

This is not a company summary. It is an exec-ready investment memo.

The goal is to determine:
1. what is true,
2. what is likely overstated,
3. what remains unproven,
4. what the business quality actually is once headline claims are pressure tested.

Do not simply restate management, investor, or company-folder claims. Treat every important claim as a hypothesis that must be tested from the outside in.

For every major claim used in the memo — ARR, customer count, growth rate, NRR, market share, pricing power, deployment depth, moat, workflow adoption, replacement dynamics, IPO readiness, and valuation — create a private Claim Register before writing.

The Claim Register must include:

| Claim | Date | Origin | Source Type | Independent? | Arithmetic Pressure Test | Secondary Corroboration | Disconfirming Evidence | Status |
|---|---|---|---|---|---|---|---|---|
| Example: revenue claim | [date] | company press release | primary | No | compare against prior revenue, employee count, and customer count | procurement data / investor estimates / analyst reports | growth deceleration, acquisition effect | Supported / Partially supported / Unproven / Disconfirmed |

A claim is not "validated" just because it appears in multiple documents. If the documents ultimately trace back to the company, treat them as a single company-originated claim until independently corroborated.

---

## Before You Start

Read the BSH background file to understand the investment thesis, criteria, and decision process:

```text
[BSH Assistant]/Settings/Serena_Background.md
```

This file is essential context. The memo must be evaluated against BSH's specific thesis (AI sector — consumer and business; immigrant founders; Asian ethnicity preferred; long-term partnership mindset; human-centered values).

**Check for a company research folder — do this before anything else.** Look for a folder named after the company inside the BSH Assistant directory:

```bash
ls "[BSH Assistant]/[Company Name]/"
```

If that folder exists, read **every file inside it** before writing a single word of the memo. This includes PDFs, Word docs (.docx), images, and screenshots — all of them. These files contain proprietary research (PitchBook data, CB Insights reports, partner insights, internal notes) that is not available publicly and that materially affects the analysis. Use the appropriate tools for each file type:

- `.docx` files → `pandoc file.docx -o file.md` then read the markdown
- `.pdf` files → `python -m markitdown file.pdf`
- `.png` / `.jpg` image files → Read tool (renders images visually)

Incorporate everything from these files into the memo.

---

## Source Provenance and Conflict Resolution

Use the company folder as privileged input, not as automatic truth.

Every fact used in the memo must be tagged by provenance:
- Company-originated
- Investor/intermediary estimate
- Independent secondary
- Internal analysis / model inference

Important:
- If a folder document quotes company data, treat it as company-originated until independently corroborated.
- If a folder document contains investor notes, analyst summaries, or internal commentary, do not assume the underlying facts are verified.
- When a folder source conflicts with public or independent sources, do not automatically prefer the folder. Instead:
  1. state the discrepancy,
  2. identify likely source bias,
  3. determine which figure is more reliable and why,
  4. mark the other figure as stale, promotional, estimated, or unverified as appropriate.

The memo must distinguish clearly between:
- company-reported facts,
- independently corroborated facts,
- estimates,
- and unresolved discrepancies.

Cite folder documents explicitly in Section VI (Sources, Source Classes, and Fact Reference Index).

---

## Run Output Safety and Versioned Storage

Never overwrite prior memo runs.

For each run, create a unique run directory under:

```text
[BSH Assistant]/Investment Memos/[Company Name]/
```

Use this run folder format:

```text
[YYYY-MM-DD]__[HHMMSS]__[slugified-company-name]__memo-run/
```

Example:

```text
[BSH Assistant]/Investment Memos/AlphaSense/2026-04-13__194512__alphasense__memo-run/
```

Inside each run folder, create:

```text
memo/
inputs/
analysis/
logs/
```

Expected contents:

**memo/**
- final English `.docx`
- final Simplified Chinese `.docx` (mirrors the English file's structure and content)
- optional `.md` working draft (English)
- optional `.md` working draft (Chinese)
- optional `.txt` memo summary for presentation

**inputs/**
- extracted deck markdown
- fetched website text
- copied or referenced source notes
- extracted PDFs / converted files
- any intermediate text derived from source materials

**analysis/**
- `claim_register.md`
- `pressure_tests.md`
- `time_base_checks.md`
- `growth_bridge.md`
- `distribution_notes.md`
- `disconfirming_evidence.md`
- `scenario_swim_lanes.md`
- `validation_log.md`
- `gating_questions.md`
- optional `competitive_notes.md`
- optional `adoption_ladder.md`
- optional `replacement_vs_coexistence.md`
- optional `core_franchise_resilience.md`

**logs/**
- tool actions
- validation results
- run metadata
- `run_manifest.md`
- `file_inventory.md`
- errors / warnings if any

The final memo file paths must be:

```text
[BSH Assistant]/Investment Memos/[Company Name]/[RUN_FOLDER]/memo/[Company Name] - Investment Memo - [YYYY-MM-DD]__[HHMMSS].docx
[BSH Assistant]/Investment Memos/[Company Name]/[RUN_FOLDER]/memo/[Company Name] - 投资备忘录 - [YYYY-MM-DD]__[HHMMSS].docx
```

Both files must be produced for every successful run. The Chinese file uses `投资备忘录` in place of `Investment Memo` so the two are visually distinguishable in a file list. Both files share the same timestamp.

Do not delete, replace, or mutate files from prior runs.

Also create a run manifest for every execution at:

```text
logs/run_manifest.md
```

The run manifest must record:
- run timestamp
- company name
- script / skill version
- source files ingested
- derived artifacts created
- validation status
- final memo path
- whether any warnings or missing artifacts remain

Also create:

```text
logs/file_inventory.md
```

List every file written in the current run folder so storage integrity can be audited later.

If a file or run folder with the target name already exists, generate a new timestamped run folder instead of overwriting.

---

## Data Preservation Rules

- Never delete prior memo runs.
- Never overwrite existing output files.
- Never modify source files in the company folder.
- Any derived artifacts must be written only into the current run folder.
- If a prior run exists on the same day, create a new timestamped run folder.
- Validation, intermediate extracts, and notes must be stored alongside the run, not mixed into shared directories.
- If a tool fails or validation fails, preserve the failed run's artifacts in its run folder for debugging.
- Create the current run folder before major extraction work begins so all downstream artifacts have a stable location.
- Never reuse an earlier run folder as a working directory for a new run.
- When a run completes, preserve both successful and failed intermediate artifacts unless they contain obvious duplicate temporary junk.
- If the memo is regenerated within the same run, save it as a new timestamped file inside the same run folder rather than overwriting the prior draft.

---

## Step 1: Gather Inputs

**First, complete the company folder check above** — that is always Step 0. Then ask Serena which of the following she has (or check what files are present in context). For late-stage / pre-IPO deals, expect Pitchbook or CB Insights material as a primary input wherever obtainable; for Series A/A2 and early-growth deals, use the sponsor memo, round materials, partner notes, company deck, and independent public research as the core package without treating missing pre-IPO-style materials as a flaw by itself:

- **Pitchbook / CB Insights summary** — primary input for growth / pre-IPO investment decisions; required wherever obtainable
- **Public peer filings or analyst notes** — for benchmarking growth, multiples, and operating profile
- **Procurement / pricing benchmarks / partner notes** — strongly preferred for revenue quality and deployment depth
- **Pitch deck or investor-materials excerpt** — PDF or PPTX file (treat as company-originated)
- **Founder / executive bios** — text, URL, or uploaded file
- **One-pager or intermediary intro** — text or file
- **Company website** — URL to fetch (treat as company-originated)

Work with whatever is available, but calibrate missing information to stage and round context. A partial memo is better than no memo — clearly mark any sections as "Information not available" when inputs are missing rather than fabricating data.

Write all derived input artifacts into the current run folder under `inputs/`.

**To extract text from a pitch deck:**
```bash
# For PPTX:
python -m markitdown /path/to/deck.pptx

# For PDF:
python -m markitdown /path/to/deck.pdf
```

**To fetch a website:**
Use the WebFetch tool with the company URL and prompt: "Extract company description, product overview, founding team, traction metrics, and any funding information."

If a website URL is available, also check for recent news, funding announcements, or coverage relevant to the current period and store useful findings in the run folder.

---

## Step 2: Falsification-First, Non-Linear Research, Pressure Testing, and Synthesis

Before writing the memo, do not start with the story. Start with the claims.

This step is the **analysis engine**. It is the only place where the 15-point redesign is inserted. Everything else in the workflow is preserved and extended, not replaced.

All intermediate analytical artifacts from this step must be written into the current run folder under `analysis/`.

### Stage Sensitivity

This skill is scoped to growth-stage, late-stage, and pre-IPO deals. Apply full pressure testing across revenue quality, deployment depth, pricing power, gross margin and operating margin where available, GTM efficiency, competitive compression, capital structure, and valuation timing.

If a deal turns out to be early-stage or early-growth once inputs are reviewed, calibrate expectations to that stage rather than forcing late-stage diligence norms onto thin data. Frame missing later-stage diligence inputs as confirmation work, not automatic disqualifiers.

### Source hierarchy

Use sources in this order:

**Tier 1: revealing secondaries**  
Use these first whenever available.
- procurement / spend data
- pricing benchmarks
- legal / licensing terms
- developer / API / integration docs
- migration docs
- product release logs
- headcount mix and hiring data
- sales-org and rep-performance data
- app / extension / usage proxies
- partner ecosystem evidence
- regulatory / compliance materials
- public financial filings of relevant peers for benchmarking

**Tier 2: structural / contextual secondaries**  
Use these to frame the market and competitive structure.
- analyst reports
- competitor documentation
- ecosystem partner materials
- product architecture writeups
- market structure research
- industry surveys from non-company sources

**Tier 3: opinion / sentiment sources**  
Use these last, and never as primary proof of business strength.
- G2
- Gartner Peer Insights
- TrustRadius
- App Store / Chrome extension reviews
- employee review sites

Rules:
- Never use Tier 3 to validate ARR, customer count, NRR, deployment depth, moat quality, or competitive replacement dynamics.
- Use Tier 3 only to identify repeated motifs: friction, cost pushback, missing functionality, adoption barriers, and renewal sentiment.
- Do not use company case studies, press releases, or company-commissioned surveys as independent sentiment evidence.

---

## Required Core Passes (Always Run)

The following passes must run on every deal, though their depth scales by stage and available data.

### 1. Arithmetic & Denominator Pass
For every important numeric claim, run arithmetic pressure tests before narrative interpretation.

At minimum, test:
1. ARR / customer
2. implied seats per customer using disclosed per-seat pricing where relevant
3. ARR / employee where relevant
4. valuation / contemporaneous ARR versus stale-mark ARR
5. growth quality: organic vs inorganic / acquisition-boosted
6. implied budget size per team or department if relevant
7. comparison against public and private peers on revenue multiple, growth, margins (if known), and ARR per employee

Use formulas and current case-specific numbers. Do not hardcode company-specific example figures from prior analyses into the skill itself.

Do not stop at one pressure test. Validate key claims from at least two different angles whenever possible.

Write results to:
```text
analysis/pressure_tests.md
```

### 1A. Time-Base Integrity Rule
Every valuation, ARR, revenue, pricing, growth, and multiple statement must be date-tagged.

For every multiple claim, explicitly state:
- numerator date (valuation / enterprise value / post-money date)
- denominator date (ARR / revenue date)
- whether the multiple is:
  - **contemporaneous**,
  - **stale-mark shorthand**,
  - **forward estimate**, or
  - **trailing shorthand**

Never present a stale-mark shorthand multiple as the true **entry multiple** unless the entry transaction occurred at that denominator level.

Build a dated table showing at minimum:
- last priced valuation and date
- ARR / revenue at that time if known
- implied contemporaneous multiple
- latest ARR / revenue and date
- implied stale-mark shorthand multiple
- why the distinction matters for the investment decision

Write results to:
```text
analysis/time_base_checks.md
```

### 1B. Growth Bridge Requirement
Build a bridge from prior reported ARR / revenue to current ARR / revenue. This is required for every deal under this skill.

Break the change into as many of these buckets as evidence allows:
- starting ARR / revenue base
- acquired revenue contribution
- price uplift
- seat / usage expansion
- new logos
- cross-sell / attach products
- unknown / unattributed remainder

Use ranges when exact values are unavailable. Do not hide unknowns inside a single growth number.

Write results to:
```text
analysis/growth_bridge.md
```

### 2. Deployment Depth Pass
Translate headline customer counts, user counts, or product usage claims into likely deployment depth.

Assess:
- typical seats per customer
- concentration among super users or specific departments
- shallow versus broad rollout
- year-1 to year-2 seat expansion where inferable
- whether the product is a beachhead tool or an enterprise standard

The key question is not "How many customers?" but "How deeply deployed per customer?"

### 3. Alternative Explanation Pass
For every positive metric or trend, generate at least 2 plausible alternative explanations before interpreting it as strength.

Examples:
- Revenue growth may reflect acquisition, pricing, bundling, or one-time attach, not deep organic expansion.
- Customer growth may reflect shallow logo acquisition, not broad deployment.
- Product release frequency may reflect catch-up or fragmentation, not adoption.
- High ratings may reflect incentivized reviews and super-user satisfaction, not enterprise-wide fit.

Then state what evidence would separate the bullish explanation from the alternative explanation.

Write results to:
```text
analysis/disconfirming_evidence.md
```

---

## Required Stage-Calibrated Passes (Run on Every Deal)

These passes are required, not optional, but their depth and evidentiary expectations must scale to the stage and source package. They may use proxies when direct evidence is unavailable, but they may not be skipped silently. If any pass cannot be completed, document the gap and convert it into an expected bar, support threshold, or stop/revisit condition.

### 4. Procurement / Spend Pass
Assess:
- procurement evidence
- pricing benchmarks
- per-seat or per-contract spend
- budget owner
- signs of finance pushback
- expansion vs consolidation behavior

### 5. Adoption Ladder Pass
For every important product capability, assign the highest proven stage:

0. announced only  
1. documented / available  
2. pilot / early access evidence  
3. named customer production evidence  
4. repeatable deployment evidence across customers  
5. renewal / upsell evidence  
6. broad deployment evidence beyond early adopters

Do this separately for:
- core search
- gen-AI summaries
- workflow automation
- APIs
- agentic workflows
- integrations

Write results to:
```text
analysis/adoption_ladder.md
```

### 6. GTM Efficiency & Strain Pass
Analyze:
- ARR per employee
- hiring mix
- open roles
- customer success burden
- support intensity
- quota attainment proxies if available
- signs of GTM elasticity versus strain
- whether growth appears self-propelling or sales-assisted and high-touch

### 7. Competitive Compression Pass
Assess whether incumbents are:
- catching up on features,
- bundling similar capabilities into larger platforms,
- undercutting the product's expansion path,
- or compressing the moat from an adoption or pricing standpoint.

### 8. Post-Acquisition Reality Pass
If acquisitions are central to the story, determine whether the business is:
- a unified platform,
- a cross-sold bundle,
- or a still-fragmented product family.

Look for evidence in:
- migration materials,
- release notes,
- customer reviews,
- support docs,
- job postings,
- legacy branding persistence,
- integration language in product docs.

### 9. Core Franchise Resilience Pass
Ask what remains true if the newest AI / agent / workflow expansion features fail to monetize.

Separate:
- the current core franchise that appears durable today
- the upside modules that are still speculative

Build the investment case on the strength of the current core first. Treat future workflow or agent adoption as upside only unless independently evidenced.

Write results to:
```text
analysis/core_franchise_resilience.md
```

---

## Non-Linear Analysis Engine

Do not analyze the company once from top to bottom.

Instead, revisit the same major claims through repeated orthogonal passes. The purpose is to prevent narrative coherence from arriving too early.

### Orthogonal Passes
Run these independently and allow them to challenge one another:

1. Arithmetic / denominators
2. Deployment / behavior
3. Budget / ownership
4. Rights / licensing / dependency
5. Replacement vs coexistence
6. GTM / operating burden
7. Time-series change-over-time
8. Competitive compression

Write the memo only after these passes have been completed at the level appropriate to the deal stage.

---

## Claim Stress Matrix

For every major claim, test it using at least 3 distinct methods and 2 distinct source classes wherever possible.

Required methods:
- arithmetic implication
- outside-in behavioral proxy
- contractual / structural evidence
- competitive comparison
- alternative explanation analysis
- time-series consistency check

Example claim categories:
- revenue quality
- deployment depth
- moat
- pricing power
- replacement dynamics
- workflow adoption
- IPO readiness

Write the working matrix to:
```text
analysis/claim_register.md
```

---

## Denominator Rule

Any claim about scale, penetration, market presence, customer count, content volume, usage, growth, or market leadership must trigger a denominator search.

Do not accept:
- customer counts
- user counts
- market-coverage claims
- corpus-size claims
- usage claims
- "millions of users" style claims

until the analysis asks:
- average revenue per customer?
- median seats per customer?
- depth of deployment?
- share of spend or workflow?
- owned vs licensed corpus?
- active vs nominal customers?
- paid vs free / shallow vs deep use?

## Distribution Over Average Rule
Averages are only the first pass.

Whenever the memo uses average ARR/customer, seats/customer, ACV, spend, usage, or adoption metrics, the analysis must also ask whether the underlying distribution is likely skewed.

At minimum, consider:
- median vs average deployment
- top-decile account depth
- long-tail shallow accounts
- whether a small number of large accounts explain most expansion
- whether the average hides meaningful churn or budget-cut risk in smaller accounts

If only averages are available, explicitly state at least two plausible distribution shapes and explain how each would change the investment conclusion.

Write results to:
```text
analysis/distribution_notes.md
```

---

## Silence Analysis

For each bullish claim, ask:

> "If this were broadly true, what evidence would likely exist in the wild?"

Then check whether that evidence appears.

Examples:
- If agentic workflows are broadly deployed, expect implementation docs, partner case studies, customer references, app usage proxies, API adoption signals, and workflow-specific job postings.
- If the product is deeply embedded across enterprises, expect evidence of wide user rollout, internal enablement materials, broader integrations, and non-expert use cases.
- If the moat is truly proprietary, expect durable rights language, exclusive datasets, or high switching frictions visible outside company materials.

Absence of expected evidence is a signal. Record it explicitly.

---

## Mandatory Business-Quality Workstreams

The memo must explicitly analyze the following:

### 1. Revenue quality, not just revenue size
Determine how much of growth appears to come from:
- organic seat growth,
- price increases,
- acquisitions,
- services / expert calls / usage-based attach,
- cross-sell from acquired products,
- expansion to new functions or departments.

Do not assume NRR, gross margin, or pricing power. If not externally supported, mark them unproven.

### 2. Budget owner and spend resilience
Identify which budget likely owns the product:
- research / strategy,
- corp dev,
- finance,
- IT,
- data / analytics,
- business unit,
- or mixed.

Then assess resilience:
- mission-critical or discretionary,
- concentrated among power users or broad teams,
- vulnerable to budget cuts or protected by workflow criticality,
- signs of finance pushback on per-seat pricing,
- evidence of pricing expansion versus seat expansion.

### 3. Deployment depth, not logo count
Translate headline customer counts into likely deployment depth:
- typical seats per customer,
- super-user concentration,
- shallow versus broad rollout,
- year-1 to year-2 seat expansion,
- whether the product is a beachhead tool or an enterprise standard.

The key question is not "How many customers?" but "How deeply deployed per customer?"

### 4. Moat quality and rights durability
Do not treat corpus size alone as a moat.

Break the moat into:
- owned proprietary content,
- exclusive content,
- licensed content,
- revocable or conditional content,
- public content,
- workflow lock-in,
- compliance / trust advantage,
- product-quality advantage.

Ask:
- what is actually owned,
- what is contractually licensed,
- what can be taken away,
- what depends on third-party terms,
- and which part of the moat strengthens or weakens as AI improves.

### 5. Feature availability versus production adoption
Do not confuse a product launch or API doc with actual deployment.

For integrations, APIs, agents, and workflow modules, ask:
- how many customers appear to be using them in production,
- whether adoption is growing beyond the initial power-user beachhead,
- whether they deepen usage or merely improve demos,
- what evidence exists outside company announcements.

Field availability is not field adoption.

### 6. Replacement versus coexistence
Quantify whether the product:
- replaces incumbents,
- coexists beside them,
- or is mainly an add-on layer.

Estimate this using:
- procurement evidence,
- comparison reviews,
- migration evidence,
- job posts,
- partner ecosystem behavior,
- and product packaging.

Treat coexistence-heavy products differently from true rip-and-replace systems.

### 7. Sales efficiency and GTM strain
Analyze:
- ARR per employee,
- hiring mix,
- open roles,
- customer success burden,
- support intensity,
- quota attainment proxies if available,
- signs of GTM elasticity versus strain,
- whether growth appears self-propelling or sales-assisted and high-touch.

### 8. Adoption by workflow layer
Segment users into distinct adoption curves:
- search / retrieval users,
- summary / gen-AI answer users,
- workflow / automation users,
- API / embedded users,
- agentic workflow users.

Do not collapse these into one "AI adoption" narrative. Each has different deployment depth, stickiness, and monetization value.

### 9. Post-acquisition integration reality
If acquisitions are central to the story, determine whether the business is:
- a unified platform,
- a cross-sold bundle,
- or a still-fragmented product family.

Look for evidence in:
- migration materials,
- release notes,
- customer reviews,
- support docs,
- job postings,
- legacy branding persistence,
- integration language in product docs.

### 10. Competitive pressure and compression risk
Assess whether incumbents are:
- catching up on features,
- bundling similar capabilities into larger platforms,
- undercutting the product's expansion path,
- or compressing the moat from an adoption or pricing standpoint.

---

## Replacement vs Coexistence Scoring

Score the product on a 1–5 scale where relevant:

1 = almost entirely additive  
2 = mostly additive, occasional replacement  
3 = mixed  
4 = mostly replacement in defined workflows  
5 = broad system-of-record replacement

Estimate this using:
- procurement evidence
- customer stack evidence
- migration docs
- comparison reviews
- partner ecosystem signals
- job postings
- implementation burden

Write results to:
```text
analysis/replacement_vs_coexistence.md
```

---

## Business Reality Classification

Before choosing comps, classify the company by observed economics and operating burden, not by aspirational category.

Possible classifications:
- AI-native SaaS
- hybrid SaaS + information services
- workflow software with high-touch implementation
- premium data / content infrastructure
- services-assisted software
- marketplace / transactional layer

Use evidence such as:
- ARR per employee
- headcount mix
- support / services burden
- content operations burden
- implementation intensity
- pricing model
- gross margin clues
- customer success intensity

Benchmark the company against what it behaves like, not what management calls it.

---

## Negative Search Requirement

For each bullish claim, run at least one search specifically designed to find contradiction, friction, or weakness.

Examples:
- pricing pushback
- integration issues
- layoffs or difficult quotas
- manual workflow complaints
- replacement claims that fail
- licensing dependence
- security / compliance limitations
- customer churn or consolidation
- implementation case studies
- API production adoption gaps

Document the most important findings in:
```text
analysis/disconfirming_evidence.md
```

---

## Evidence Entropy Rule

Multiple sources repeating the same company-originated fact do not count as multiple confirmations.

Before treating a claim as corroborated, determine whether the sources are genuinely independent or are downstream repetitions of the same original claim.

Downgrade confidence when:
- many sources cite the company directly
- analyst writeups rely on management interviews
- review sites repeat marketing narratives
- market maps list the company without usage proof

## Final Memo Source Strategy
End-of-memo source lists are necessary, but final memo prose and operating tables must not look like a research scratchpad.

Do not put inline source markers, bracketed source IDs, file names, artifact names, or raw source-trace tokens in the main memo body or operating tables. This means no body/table strings such as `[S1]`, `[WV]`, `[companies.yaml]`, `[internal]`, `memo_packet`, `source_trace`, or analysis file names. Detailed traceability belongs in:
- `analysis/claim_register.md` and related analysis artifacts;
- a dedicated **Sources, Source Classes, and Fact Reference Index** section;
- clearly separated validation appendices.

In Sections I through V, use reader-facing source-class language instead:
- if a material fact is primarily company-reported, say **company-reported** or **management discussion** on first mention;
- if a fact is independently supported, say **public third-party** or **independently supported**;
- if a fact is inferred rather than directly reported, label it as an **estimate** or **internal model**;
- if a claim is unresolved, say so in the body and pair it with model treatment or diligence thresholds.

The reader can tell whether a claim is company-originated, independently supported, estimated, or unresolved without seeing internal citation tokens. The fact index maps every material claim back to source title, source class, date, confidence, and usage.

## Disclosure Gap -> Model Treatment Rule
Disclosure gaps are modeling inputs, not stopping points.

When a material metric is missing or only partially disclosed, the memo must state:
- what is disclosed;
- what is not disclosed;
- the source class for the available evidence;
- the model treatment used in the memo;
- what new evidence would change the model.

Default private-company commercial conversion framework:
- binding signed contract: 80-100% conversion credit;
- signed but cancellable or milestone-based contract: 50-75% conversion credit;
- MOU: 15-35% conversion credit;
- LOI: 10-25% conversion credit;
- pipeline: 5-15% conversion credit;
- unqualified ecosystem logo: 0% revenue credit unless contract status is disclosed.

When recognized revenue, ARR, ACV, retention, or gross margin is not disclosed, include at least one outside-in sanity bridge using customer count, site count, contract value, term length, employee count, implementation capacity, comparable contract duration, or another defensible proxy. Avoid repeated "not disclosed" statements unless each one is paired with treatment and a diligence threshold.

---

## Precision Language Gates

Do not use the following phrases unless the evidence threshold is met:

- **"Moat"** — only if broken into owned, exclusive, licensed, behavioral, and workflow components.
- **"Platform"** — only if there is evidence of multi-function deployment beyond a single core use case.
- **"Default workflow layer"** — only if there is evidence of broad deployment depth, integration adoption, and replacement or standard-setting behavior.
- **"Dominant"** — only if the company leads on a clearly defined dimension with independent support.
- **"Sticky"** — only if supported by retention, renewal, or repeated behavioral evidence.
- **"Reasonable valuation"** — only if benchmarked against contemporaneous ARR and relevant peers.

## No Unsupported Probabilities Rule
Do not assign numeric probabilities, adoption percentages, or overly precise scenario weights unless the evidence basis is explicitly stated.

Default behavior:
- use **Bear / Base / Bull** without numeric probabilities, or
- use **Low / Medium / High confidence** labels

Numeric probabilities are allowed only when:
- the evidence basis is stated,
- the confidence level is stated,
- and the memo explains why those probabilities are more useful than simple scenario framing.

Never give a false sense of calibration just because a number looks precise.

## Evidence-State Rule
Separate what is already evidenced today from what still depends on future execution, but keep the taxonomy private.

In particular:
- describe current deployment, current growth quality, and current moat components as proven only when evidenced
- frame agentic workflows, broad enterprise rollout, durable pricing expansion, and future platform status as future possibilities unless current evidence proves they are already happening
- do not use future-state optionality to justify current-state labels like "dominant," "default workflow layer," or "platform" without present evidence
- do not render visible parenthetical labels such as `(present-state)`, `(upside-state)`, or `upside-only` in the final memo

---

## Pre-Mortem and Reverse IC

Before finalizing the recommendation, write two short internal memos and store them in the run folder under `analysis/`:

1. **Pre-Mortem**  
   "It is 24 months later and this investment looks materially worse than expected. What most likely went wrong?"

2. **Reverse IC**  
   "Assume we must recommend PASS. What are the three strongest facts supporting that conclusion?"

Do not reuse the same evidence in both the bull and bear case without stating the ambiguity.

---

## Mind-Change Triggers

For each major uncertainty, state:
- what evidence would upgrade confidence
- what evidence would downgrade confidence
- whether the missing evidence can be confirmed to the expected bar

Examples:
- deployment depth
- revenue quality
- pricing resilience
- replacement dynamics
- moat durability
- organic growth

Store these in:
```text
analysis/validation_log.md
```

---

## Required Analytical Output

Before writing the memo, answer these questions privately and record them in the analysis artifacts:

1. What do the headline numbers imply when pressure tested?
2. What does outside-in evidence suggest is actually deployed?
3. Where does the company seem strongest?
4. Where does the bull case rely on unproven assumptions?
5. What has been confused with a moat but is really just scale or marketing?
6. What is the likely base-case role of the product in the stack: system of record, workflow layer, point solution, or premium add-on?
7. What are the most likely scenario swim lanes and what evidence supports each?

Write scenario conclusions to:
```text
analysis/scenario_swim_lanes.md
```

## Missingness Calibration Rule
Absence of critical data is not neutral.

Missing information about NRR, gross margin, burn, EBITDA / operating margin, customer concentration, pricing durability, or capital structure must be calibrated to stage and round context. For Series A/A2 and early-growth deep-tech financings, lack of disclosed ARR, margin, a public lead name, or detailed side-letter terms is common; do not automatically turn those gaps into a high-severity risk or a low-conviction recommendation. For later-stage and pre-IPO rounds, the same missingness carries more weight.

When critical metrics are missing:
- explicitly state what is missing
- explain why it matters
- calibrate confidence to stage, sponsor access, syndicate quality, scarcity, and available proxies
- move the missing item into the top expected-bar list only if it could materially change the recommendation

## Top 3 Expected Bars
Collapse all open diligence into the three highest-value expected bars that would most change how strongly we can defend the recommendation.

These are not questions and not process asks. Write each as:
- the expected bar that supports the investment case;
- the support threshold that makes the recommendation defensible;
- the confirmation evidence that would substantiate the bar;
- the stop/revisit condition if the bar resolves below threshold.

Additional confirmation bars may be included after the top three, but they are secondary.

Write the internal expected-bar list to the existing artifact path:
```text
analysis/gating_questions.md
```

Write the memo narrative only after completing this work.

---

## Transition from Analysis to Memo Writing

Only proceed to Step 3 after Step 2 produces, at minimum, these artifacts in the current run folder:

- `analysis/claim_register.md`
- `analysis/pressure_tests.md`
- `analysis/time_base_checks.md`
- `analysis/growth_bridge.md`
- `analysis/distribution_notes.md`
- `analysis/disconfirming_evidence.md`
- `analysis/scenario_swim_lanes.md`
- `analysis/validation_log.md`
- `analysis/gating_questions.md`

These are working artifacts for the run and must be preserved.

The transition summary passed into memo writing must include:
- validated claims
- unproven claims
- strongest disconfirming evidence
- deployment reality
- business classification
- contemporaneous vs stale-mark multiple view
- growth bridge summary
- average vs distribution risk summary
- base / bull / bear swim lanes
- top 3 expected bars

---

## Step 3: Generate The Memo Package For Both DOCX Files

Every successful run produces two parallel `.docx` files: one in English and one in Simplified Chinese. They share the same timestamp, the same structure, the same data, and the same analytical conclusions. The Chinese file is a faithful translation of the English file — not an independently-authored memo and not a summary.

Do **not** hand-write per-run Python or JavaScript renderer scripts. The DOCX
layout system is fixed product code. Build the memo as structured data in
`logs/memo_package.json`. The server will run the fixed renderer after this
Claude subprocess exits. The renderer owns DOCX styles, cover layout, headers,
footers, tables, callouts, bilingual font handling, validation files, file
inventory, and manifest finalization.

The memo package is the dynamic surface. It must include:
- `schema_version: 1`
- `company` metadata: name, descriptor, stage, sector, location, round
- `run` metadata: run id and as-of date
- `sections`: ordered section objects using the exact memo structure below
- section `blocks` of type `heading`, `paragraph`, `bullets`, `callout`, or `table`
- bilingual strings as `{ "en": "...", "zh": "..." }` wherever text appears
- `sources`: source title, source class, model treatment, and as-of date

Forbidden run artifacts include `build_memo.py`, `build_memos.py`,
`generate_memo.py`, `render_memo.py`, and JavaScript variants. If you need
different layout behavior, express it through the package data and the supported
block types rather than writing new code.

Recommended generation order:
1. Finish the English memo first — the English version is the source of truth for analytical content.
2. Validate that the English memo is complete, the structure matches the spec, all required tables and callouts are present, and the recommendation verdict is clear.
3. Translate the English memo into Simplified Chinese following the rules in the **Bilingual Output: English + Simplified Chinese (简体中文)** section below.
4. Write the bilingual structured package to `logs/memo_package.json`.
5. Cross-check that the Chinese memo's tables, callouts, recommendation, and Closing Confirmation Bars match the English memo exactly in content (only language differs).

Save the outputs into the current run folder under:
```text
memo/[Company Name] - Investment Memo - [YYYY-MM-DD]__[HHMMSS].docx
memo/[Company Name] - 投资备忘录 - [YYYY-MM-DD]__[HHMMSS].docx
```

Create the run folder and required subdirectories if they do not exist. The
server renderer will create validation files and file inventory entries after
Claude exits, but the analysis artifacts and package data remain your
responsibility.

## Document Packaging Contract (Mandatory)

The memo must be packaged as a designed investment memorandum, not plain paragraphs inside a DOCX.

The document is only acceptable if it has:
- a real cover page with visual hierarchy
- a consistent style system across headings, body text, tables, callouts, headers, and footers
- structured data components rendered as tables, not collapsed into prose
- visible page numbers rendered correctly
- compact but readable page architecture
- a layout that is skimmable for asynchronous co-founder review

Do not rely on default Word theme formatting. Apply explicit styles or direct formatting to all major components.

## Cover Page Layout (Mandatory)

The cover page must be visually stronger than the body pages and must not look like a loose metadata note.

Required cover-page elements:
1. BSH brand line or small running identifier
2. Primary centered title: `BERKELEY SUMMIT HOUSE`
3. Subtitle: `Confidential Investment Memo`
4. Prominent company display name in large navy type
5. Optional one-line company descriptor / category subtitle
6. A centered metadata block containing:
   - Date
   - Stage
   - Sector
   - Location
   - Round (for late-stage transactions where round size and post-money are public or in-talks)

   Do not include a `Prepared by` line on the cover. Internal authorship belongs in the run manifest, not the deliverable.
7. **Table of Contents** placed below the metadata block, listing the six body-section entries only — I. Executive Summary, II. Company Overview, III. Investment Highlights, IV. Investment Risk, V. Financial Forecast & Valuation, VI. Sources, Source Classes, and Fact Reference Index — with their page numbers. Do **not** include the Validation & Assumptions Log appendix in the TOC; appendix material is auditing scaffolding rather than navigable narrative content. Use a small Tiffany-rule header labeled `TABLE OF CONTENTS` (English) or `目录` (Chinese), then a compact two-column layout (section name on the left, page number right-aligned with dot leaders or simple right-alignment). Include only top-level (Heading 1) entries to keep the cover page uncluttered. Subsection headings are reserved for the body, not the cover.

Preferred implementation:
- Use a dedicated cover page with a different first-page header/footer if supported.
- Prefer no running header on the cover page.
- Prefer page numbering to begin on page 2 as `Page 1`.
- If different first-page behavior is brittle in the implementation, keep the cover clean and ensure the footer still renders a correct page number.

Do not use a loose left-aligned list as the primary cover-page layout.
Do not allow the cover page to look like default Word output.

## Executive Summary Packaging (Mandatory)

The Executive Summary must be visually structured for rapid review and must follow the five-subsection order defined in the memo structure: Investment Opportunity → Investment Thesis → Investment Risk → Investment Recommendation → Closing Confirmation Bars.

Required executive-summary components:
1. **Key Metrics Snapshot** table inside Investment Opportunity, near the top of page 2
2. **Valuation Timing Warning (for BSH)** callout inside Investment Opportunity whenever contemporaneous vs stale-mark multiples differ materially
3. A deal-specific investor-facing evidence callout when it adds value, such as **What Is Priced In**, **What Still Needs Confirmation**, **Bear-Case Evidence**, or **Evidence Required Before the Next Step-Up**
4. A clear **Investment Recommendation** verdict (Proceed / Proceed if confirmed / Hold pending confirmation / Pass) with explicit confirmation items when conditional
5. **Closing Confirmation Bars** callout inside the Executive Summary
6. Clear separation between:
   - facts evidenced today
   - future execution dependencies
   - unresolved expected bars

Do not use `(for BSH)` callout suffixes in the final memo. Confirmation bars contain expected thresholds, support evidence, and stop/revisit implications that defend the recommendation.

Recommended packaging order on the page:
- Investment Opportunity narrative + Key Metrics Snapshot table + (Valuation Timing Warning (for BSH) callout if relevant)
- Investment Thesis bullets
- Investment Risk bullets + deal-specific evidence callout if useful
- Investment Recommendation
- Closing Confirmation Bars callout

## Mandatory Structured Components

The following sections must use tables, not prose-only formatting:

**Always required**
- I. Executive Summary → Key Metrics Snapshot (inside Investment Opportunity)
- II. Company Overview → Team → Board of Directors
- II. Company Overview → Revenue
- II. Company Overview → Key Metrics
- III. Investment Highlights → Competitive Analysis (comparison table)
- III. Investment Highlights → Moat
- IV. Investment Risk → Risk Register
- V. Financial Forecast & Valuation → Time-Base Integrity Table
- V. Financial Forecast & Valuation → Growth Bridge Table
- V. Financial Forecast & Valuation → Scenario Analysis
- Appendix: Validation & Assumptions Log

Minimum table expectations:
- Every memo produced by this skill: at least **8** tables

Do not collapse structured comparison material into prose just because the prose is shorter.

## Callout Box Component Library

Use styled callout boxes for high-signal content. Build these using single-cell tables or another robust DOCX-safe layout mechanism.

Required callout types:

### 1. Critical Warning Box
Use for:
- stale-mark multiple warnings
- missing unit economics warnings
- major source-integrity warnings
- thesis-defining caveats

Style:
- left accent border in Tiffany Blue `0ABAB5`
- light fill (Pale Tiffany `E6F7F6` or Pale Gold `F7F0D9` when a warning tone is warranted)
- compact internal padding
- bold label line (e.g. `CRITICAL:`)
- no default paragraph styling

### 2. Decision Gate Box
Use for:
- top 3 expected bars
- recommendation conditions
- expected bars and support thresholds

Style:
- light neutral or pale fill
- strong heading line
- compact bullets or numbered items

### 3. Evidence Summary Box
Use for:
- strongest supporting fact
- strongest disconfirming fact
- what remains unproven
- what must be true for the bull case

Style:
- pale fill
- clean left border
- concise bullet treatment

At least **3 callout boxes** are required in every memo produced by this skill.

## Page Architecture Rules

The memo must feel compact, intentional, and professionally packaged.

Required page-flow rules:
- The cover page stands alone.
- The Executive Summary begins on page 2.
- Do not force every major section onto a new page.
- Let sections flow naturally unless a page break clearly improves readability.
- Avoid isolated headings at the bottom of a page.
- Keep tables with their headings where possible.
- Avoid half-empty pages unless a deliberate section break is justified.
- Prevent large blank regions created by poor spacing or unnecessary page breaks.
- Prefer compact metadata blocks and structured tables over long runs of repeated label/value prose.

Use keep-with-next, keep-lines-together, and sensible paragraph spacing where possible.

### Memo Structure

Use this exact structure, in order. Because deals in scope range from Series A/A2 growth opportunities to pre-IPO rounds, scale financial, capital-structure, competitive, governance, and valuation coverage to the actual stage and available source package. The required additions below are part of the exact structure and must be included.

---

**[COVER PAGE]**  
Use the mandatory cover-page layout above.  
Required text content:
- Berkeley Summit House — Confidential Investment Memo
- Company: [Name]
- Date: [Date]
- Stage: [Late-Stage / Pre-IPO / Growth — specify round letter if known]
- Sector: [AI / Consumer / etc.]
- Location: [City, Country]
- Round: [round size / post-money / instrument]

Do not include `Prepared by` on the cover. Author attribution belongs in the run manifest.

Preferred display hierarchy:
- BSH title
- memo subtitle
- company display name
- optional company descriptor
- centered metadata block

---

**I. Executive Summary**

Start this section on page 2.

The Executive Summary is a tight synthesis of Sections II (Company Overview), III (Investment Highlights), and IV (Investment Risk). It opens with our sponsor thesis and why we want exposure, then explains the deal, the evidence supporting investor returns, the failure modes, and the expected bars that control whether the recommendation holds.

Write it like a spoken IC summary, not a report introduction. In compressed prose, answer: what the company is, what transaction is in front of BSH, why now, why the company could win, what must prove true, why the deal could fail, and the investment view. Use the required subsection labels for navigation, but keep the language direct and partner-like.

Required subsection order:
1. Investment Opportunity
2. Investment Thesis (summary of III)
3. Investment Risk (summary of IV)
4. Investment Recommendation
5. Closing Confirmation Bars

*Investment Opportunity*  
Lead with the opening thesis contract before any table:
1. sentence 1: why we care about this category or market shift;
2. sentence 2: why this company is the asset we want exposure to;
3. sentence 3: what we are being offered and at what entry terms;
4. sentence 4: the central price/proof tension, especially when valuation has moved faster than disclosed commercial proof;
5. sentence 5: what we recommend and the confirmation items that can move the decision.

The first two body paragraphs must state sponsor conviction, company relevance, transaction, valuation / entry terms, central price/proof tension, and recommendation. Do not start with negative throat-clearing, meta-language, or detached recommendation/opportunity constructions; use "we recommend", "we would proceed if", and "we are being offered" instead.

Then describe the deal itself: round size and structure (priced equity, secondary, SPV), valuation / price per share, discount or premium versus the most recent priced round, co-investors and their reputations, access channel where relevant, expected liquidity timeline, and any investor-facing co-investment terms (management fee, carry).

Include a **Key Metrics Snapshot** table near the top with the most important available metrics, such as:
- ARR / revenue
- customer count
- growth rate
- last priced valuation and date
- current implied multiple (label as contemporaneous, forward, or stale-mark shorthand)
- stage / round letter
- headcount
- replacement / coexistence score if relevant

If contemporaneous and stale-mark multiples differ materially, include a **Valuation Timing Warning (for BSH)** callout box here.

*Investment Thesis* (3–5 bullets, summary of Section III)  
The core reasons BSH would invest. Each bullet uses a bold, concrete investor claim followed by 1–2 sentences of supporting logic. The first sentence makes the claim; the second sentence states the source class or model treatment and what must prove true. Do not use parenthetical evidence-state labels in the final memo.

These bullets must be derivable from Section III. Do not introduce thesis claims here that are not developed in III.

*Investment Risk* (3–5 bullets, summary of Section IV)  
The strongest reasons not to invest, framed as the risks most likely to change the recommendation. Each bullet names the risk and the disconfirming or stress evidence behind it.

If a callout improves readability, render a deal-specific investor-facing evidence box with one of these headings:
- **What BSH Is Buying**
- **What Is Priced In**
- **What Still Needs Confirmation**
- **Bear-Case Evidence**
- **Evidence Required Before the Next Step-Up**

Do not use scaffold headings such as "Critical Reality Check," "Strongest independent support," "Still unproven," or "Already true versus upside-only." Translate those analytical distinctions into normal investor language.

*Investment Recommendation*  
A clear recommendation: **Proceed / Proceed if confirmed / Hold pending confirmation / Pass**. Follow with 2–4 sentences defending the logic. If conditional, state the expected bars that support the recommendation and the stop/revisit implications if those bars resolve below threshold.

Treat this as the Investment View: state conviction, dependencies, failure modes, and recommendation. Do not summarize the memo's structure or methodology.

*Closing Confirmation Bars*  
Render the **Closing Confirmation Bars** as a concise callout box. These are the three expected bars that most directly support or weaken the recommendation. Each bar must be stated quantitatively or specifically where the source package allows: binding contract value at or above the stated threshold, A2 economics within the disclosed range, SAFE conversion mechanics matching the expected entry, or named deployment evidence supporting the valuation. Do not phrase these as questions.

---

**II. Company Overview**

Section II is descriptive — the facts about the company. Save evaluative judgment about whether these facts argue for or against the deal for Section III.

Explain the operating reality: what the company does, what workflow or physical-world process it changes, who uses it, what it replaces or augments, and how it is deployed in real environments. Avoid taxonomy-heavy descriptions that read like market-map labels.

*Product Overview*  
What the product does, who uses it, and what problem it solves. Use concrete examples of the user experience or workflow.

*Core Technology / Differentiation*  
What the technical approach is, in plain language. Describe what would be technically distinctive without yet judging defensibility — that comes in III (Moat).

*Value Proposition*  
From the customer's perspective: why they pay for this, what pain it removes, and how it compares to the status quo or alternatives.

*Business Model*  
Pricing model (SaaS, usage-based, transactional, hybrid), contract structure, average contract value if known, gross / net retention if disclosed, and how the model scales operationally.

*Key Partners and Relationships*  
Strategic partnerships, distribution channels, platform integrations, OEM or channel deals, and notable enterprise relationships.

*Team*  
Two components, both required.

*Founders / Management Team* — for each founder and key executive:
- Name, title
- Immigration background (yes/no, origin) and age if known — these are BSH thesis factors
- Relevant prior experience and domain expertise
- Why this person is suited to this problem (factual; quality assessment lives in III)

*Board of Directors* — render as a table. List board members with background and strategic value, including institutional investor representatives, independent directors, and observer seats if known. Note open seats and governance dynamics relevant to a pre-IPO transition.

*Revenue*  
Render the revenue picture with a table when more than one revenue component is in play.
- ARR / revenue run rate and growth rate (MoM or YoY)
- Customer segments and notable logos
- Revenue concentration risk (does any single customer represent >10% of revenue?)
- Net retention, gross retention, and expansion vs. new-logo contribution where disclosed or inferable
- Organic vs. acquisition-boosted growth split (factual breakdown)
- Pricing-led vs. seat / usage-led growth split (factual breakdown)
- Average deployment metrics with distribution caveats (how the average may hide a skewed customer base)

*Key Metrics*  
Render as a table. Include the highest-signal operating metrics, such as:
- ARR / customer
- implied seats per customer where relevant
- ARR / employee
- gross margin and operating margin if disclosed
- burn rate and runway if disclosed
- replacement / coexistence score
- adoption depth across workflow layers (search / retrieval, summary / gen-AI, workflow / automation, API / embedded, agentic) — keep these separate; do not blur them into one "AI adoption" narrative
- budget owner and signs of spend resilience

---

**III. Investment Highlights**

Section III answers the evaluative question: why or why not invest. Every claim made here must be traceable to a fact in Section II, an external source, or analysis in the run-folder artifacts.

*Industry Trends & Market Context*  
Cover 2–3 major tailwinds or market dynamics that create the opportunity. For each:
- State the trend with supporting data (market size, growth rate, key research sources)
- Explain why it creates an opening specifically for this company's approach
- Note any risks if the trend reverses or slows

Keep market context limited to structural forces: demand drivers, timing, budget sources, and why buyer behavior is changing now. Do not write a broad market essay.

*Competitive Analysis*  
Open with a 2–3 sentence overview of how the competitive landscape is structured.

Frame competition as deal dynamics: who blocks the sale, who owns distribution, where substitution actually happens, and whether the product replaces incumbents or coexists beside them. Avoid vendor-list prose that does not explain buying friction or displacement risk.

For each major competitor, cover:
- What they do and who they target
- Key strengths
- Key weaknesses vs. this company
- How the company differentiates

Use a comparison table. This subsection must not be prose-only.

*Replacement vs. Coexistence* — state whether the product is mostly replacing incumbents, mostly coexisting beside them, or functioning mainly as an additive layer. Quantify or clearly characterize this. If scored on the 1–5 scale, surface the score in a table row rather than burying it in prose.

*Moat*  
Render as a table.
Break the moat into:
- owned content / data
- exclusive content / data
- licensed content / data
- conditional / revocable content / data
- workflow lock-in
- trust / compliance advantage
- product / UX advantage

Then add a paragraph on **rights durability**: what is contractually protected, what depends on third-party terms, what could be taken away, and which parts of the moat strengthen or weaken as AI improves.

*Quality of Financials*  
Evaluate revenue *quality*, not just size. Address:
- how much of growth is organic vs. acquisition-boosted vs. pricing
- deployment depth vs. logo count
- distribution shape behind any average metric
- net retention durability and expansion mechanics
- gross / operating margin trajectory if disclosed
- capital efficiency (ARR per employee, GTM strain)
- whether unit economics support the implied multiple

This subsection sets up the detailed numbers in Section V — keep judgments here qualitative and reference V for the full math.

*Quality of Business Model*  
Evaluate:
- budget owner and spend resilience (mission-critical vs. discretionary, signs of pricing pushback)
- pricing power and expansion mechanics (price uplift, seat expansion, cross-sell)
- adoption durability across workflow layers (search, summary, workflow, API, agentic) — credit each layer separately
- post-acquisition reality if acquisitions are central to the story (unified platform vs. cross-sold bundle vs. fragmented family)
- competitive compression risk

*Quality of Team*  
Evaluate the team named in Section II:
- founder–market fit and operating track record
- ability to execute through an IPO or large-scale transaction
- bench depth at CFO, CRO, COO levels
- governance maturity (board composition, independent directors, audit readiness)
- alignment with BSH's long-term partnership thesis

---

**IV. Investment Risk**

Section IV consolidates everything that argues against the deal — the risks themselves and the explicit disconfirming evidence behind them. Do not soften or balance against the thesis here; that work happens in the recommendation logic in Section I.

*Risk Register*  
Render as a compact risk table with 4–6 rows.

Each risk statement is a sharp one-sentence risk. Put evidence, mitigants, and monitoring notes in the compact table fields or adjacent notes, not in layered explanatory risk prose.

| # | Risk | Severity | Likelihood | Disconfirming Evidence | Mitigant / Monitoring Approach |
|---|------|----------|------------|------------------------|-------------------------------|
| 1 | [risk] | High / Med / Low | High / Med / Low | [evidence] | [mitigant] |

*Key Disconfirming Evidence*  
Beyond the risk table, surface the strongest factual evidence that cuts against the thesis. This is not a risk list — it is the body of evidence a skeptical investor would lead with. Use an evidence-summary callout box if the disconfirming evidence is especially central to the case.

*Pre-Mortem Summary*  
A short paragraph distilling the run-folder Pre-Mortem: assume it is 24 months later and this investment looks materially worse than expected — what most likely went wrong?

---

**V. Financial Forecast & Valuation**

Even when direct financial access is limited, build a picture from available data:
- Known or estimated revenue and growth rate
- Burn rate and runway (if disclosed)
- Path to profitability or cash flow neutrality
- Valuation methodology: use comparable public or private companies

*Outside-In Sanity Checks*  
Include arithmetic pressure tests such as:
- ARR / customer
- implied seats per customer where relevant
- ARR / employee
- valuation multiple timing sanity checks
- comparison against peers on growth and operating profile

Include a short **Time-Base Integrity Table** showing:
- last priced valuation and date
- ARR / revenue at that time
- implied contemporaneous multiple
- latest ARR / revenue and date
- implied stale-mark shorthand multiple

*Growth Quality Notes*  
Explain whether the company's growth appears to be driven by:
- organic expansion
- pricing
- acquisitions
- services / usage attach
- cross-sell into adjacent workflows

Include a **Growth Bridge Table**. If direct evidence is unavailable, build a bridge using ranges and clearly label the unattributed remainder.

*Capital Structure & Dilution Notes*  
Distinguish enterprise value from the value likely accruing to common shareholders.

Where relevant:
- include known debt
- note liquidation preferences if known
- note whether secondaries are occurring
- include an explicit dilution / option-refresh / future-round assumption if the cap table is incomplete
- avoid implying that headline enterprise value flows directly to BSH without dilution or preference effects

*Scenario Analysis*  
Use a scenario table.

| Scenario | Revenue (target year) | CAGR | Comparable Multiple | Implied Enterprise Value | Dilution / Preference Assumption | Implied Value to Common | BSH IRR |
|----------|----------------------|------|--------------------|--------------------------|----------------------------------|-------------------------|---------|
| Bear Case | $X | X% | Xx | $X | [assumption] | $X | X% |
| Base Case | $X | X% | Xx | $X | [assumption] | $X | X% |
| Bull Case | $X | X% | Xx | $X | [assumption] | $X | X% |

Do not assign numeric scenario probabilities unless the evidence basis is stated. Default to scenario framing rather than faux-precise probabilities.

Note assumptions explicitly. If financials are unavailable, say so and explain what proxy signals you're using.

---

**Investment Decision / Closing View**

Before Sources, include a substantive final investment close that mirrors the opening thesis. It must state:
- recommendation: Proceed, Proceed if confirmed, Hold pending confirmation, or Pass;
- expected bars and support thresholds that defend the recommendation;
- stop / revisit conditions;
- what changes the next-round / step-up case;
- next diligence actions in priority order.

Do not let legal disclosures or source lists become the memo's substantive ending.

---

**VI. Sources, Source Classes, and Fact Reference Index**

Use a compact source table or numbered fact index that maps material claims to source class and source detail. This is the only main memo section where detailed source IDs, source titles, and internal source references may appear.

Clearly distinguish, where relevant:
- company-originated sources
- internal folder sources (PitchBook, CB Insights, partner notes)
- independent secondary sources
- opinion / review sources
- internal model or estimate

Recommended columns: Fact / claim, source class, source title or source ID, date, confidence, memo usage. Keep source IDs out of Sections I through V and all operating tables.

---

**Appendix: Validation & Assumptions Log**

Appended after Section VI. This is a structured audit table, not a narrative section.

Render as a table. List every material claim or fact in the memo and record:
- provenance,
- whether independent support exists,
- what disconfirming evidence exists,
- current status,
- next diligence step.

| # | Claim | Provenance | Independent Support | Disconfirming Evidence | Status | Confidence | Next Diligence Step |
|---|---|---|---|---|---|---|---|
| 1 | [claim] | company / investor / secondary / internal analysis | [yes/no + source class] | [summary] | Supported / Partially supported / Unproven / Disconfirmed | High / Medium / Low | [next step] |

The Validation & Assumptions Log is mandatory — a memo without it does not pass the validation gate.

---


## Bilingual Output: English + Simplified Chinese (简体中文)

The Chinese memo is a parallel deliverable, not a translation appendix. It must match the English memo in structure, analytical depth, table content, and recommendation. It is intended for BSH co-founders and partners who prefer to read in Chinese, including GP partners and LP relationships.

### Translation Scope

Translate into Simplified Chinese:
- All section headers and subsection labels
- All body prose, callout text, and bullet points
- All table column headers and any descriptive cell text
- Status labels (e.g., "Supported / Partially supported / Unproven / Disconfirmed")
- The recommendation verdict (e.g., "Proceed / Proceed if confirmed / Hold pending confirmation / Pass")
- Footer / running header text

Preserve in original Latin form (do **not** translate):
- Company name (legal entity name and product/brand names)
- Names of executives, founders, board members, investors, and intermediaries
- Ticker symbols and corporate identifiers
- Currency amounts, percentages, dates, and ratio expressions (e.g., `$420M`, `42%`, `2026-04-13`, `12x`)
- Industry-standard acronyms (ARR, NRR, GTM, IPO, SaaS, API, MoM, YoY, IRR, EBITDA, CAGR, LTV, CAC) — but provide the Chinese gloss in parentheses on first mention if it materially aids comprehension (see glossary below)
- File paths, URLs, code blocks, and run-folder references
- Source citation markers and document filenames

### Chinese Localization Quality Bar

The Chinese memo must read like it was written by a bilingual investment analyst, not machine-translated. Faithful content does **not** mean literal wording.

Rules:
- Write for mainland Chinese institutional investors. Prefer natural finance / research Chinese over word-by-word translation.
- If an English term has no idiomatic Chinese equivalent, keep the English term and add a short Chinese gloss on first mention. It is better to preserve English than to invent awkward Chinese.
- Preserve product names, framework/library names, model names, company names, tickers, acronyms, metrics, numbers, dates, and URLs unless there is a widely used Chinese name.
- Reorder clauses so the Chinese sentence reads naturally. Do not preserve English syntax when it produces stiff or confusing Chinese.
- Do **not** translate "tailwind" as "顺风". Depending on context, use "行业利好", "需求侧利好", "结构性利好", "顺势因素", or keep `tailwind（利好因素）`.
- Do **not** translate coined phrases like "credible second wave" as "可信第二波". Translate the meaning instead: "第二轮增长的可信度", "有望形成第二波增长", "第二波增长是否成立", or keep the English phrase with a short gloss if the phrase is being discussed as a term of art.
- Do **not** translate "runway" mechanically as "跑道" unless the phrase is already idiomatic in context. Prefer "现金可支撑时间", "增长空间", or `runway（可支撑时间/增长空间）`.
- Do **not** translate "stickiness" as a literal physical adjective. Use "客户黏性", "用户黏性", or describe retention / switching costs.
- For English category labels embedded in Chinese paragraphs, keep the English where it is clearer and explain once: e.g., `OEM（原始设备制造商）`, `API（应用程序接口）`, `SaaS`, `ARR`.

### Section Header Translations (Use Exactly These)

| English | Simplified Chinese |
|---|---|
| Berkeley Summit House — Confidential Investment Memo | Berkeley Summit House — 机密投资备忘录 |
| Cover Page | 封面 |
| Table of Contents | 目录 |
| I. Executive Summary | 一、核心摘要 |
| Investment Opportunity | 投资机会 |
| Investment Thesis | 投资逻辑 |
| Investment Risk | 投资风险 |
| Investment Recommendation | 投资建议 |
| Closing Confirmation Bars | 交割确认标准 |
| Key Metrics Snapshot | 关键指标速览 |
| What BSH Is Buying | BSH 本次配置的核心资产 |
| What Is Priced In | 估值中已反映的预期 |
| What Still Needs Confirmation | 仍需确认的事项 |
| Bear-Case Evidence | 悲观情景证据 |
| Evidence Required Before the Next Step-Up | 下一轮估值上调前所需证据 |
| Investment Decision / Closing View | 投资决策 / 结论观点 |
| Closing Confirmation Bars | 交割确认标准 |
| Valuation Timing Warning (for BSH) | 估值时点警示（仅供 BSH） |
| (for BSH) | （仅供 BSH） |
| II. Company Overview | 二、项目简介 |
| Product Overview | 产品概述 |
| Core Technology / Differentiation | 核心技术与差异化 |
| Value Proposition | 价值主张 |
| Business Model | 商业模式 |
| Key Partners and Relationships | 主要合作伙伴与关系 |
| Team | 团队 |
| Founders / Management Team | 创始人与管理团队 |
| Board of Directors | 董事会 |
| Revenue | 收入 |
| Key Metrics | 关键指标 |
| III. Investment Highlights | 三、投资亮点 |
| Industry Trends & Market Context | 行业趋势与市场背景 |
| Competitive Analysis | 竞争分析 |
| Replacement vs. Coexistence | 替代 vs. 共存 |
| Moat | 护城河 |
| Quality of Financials | 财务质量 |
| Quality of Business Model | 商业模式质量 |
| Quality of Team | 团队质量 |
| IV. Investment Risk | 四、投资风险 |
| Risk Register | 风险清单 |
| Key Disconfirming Evidence | 关键反证 |
| Pre-Mortem Summary | 预先反思摘要 |
| V. Financial Forecast & Valuation | 五、财务分析 |
| Outside-In Sanity Checks | 外部验证测算 |
| Time-Base Integrity Table | 时点一致性表 |
| Growth Quality Notes | 增长质量说明 |
| Growth Bridge Table | 增长桥接表 |
| Capital Structure & Dilution Notes | 资本结构与稀释说明 |
| Scenario Analysis | 情景分析 |
| Bear Case / Base Case / Bull Case | 悲观情景 / 中性情景 / 乐观情景 |
| VI. Sources, Source Classes, and Fact Reference Index | 六、资料、来源分类与事实索引 |
| Appendix: Validation & Assumptions Log | 附录：验证与假设日志 |

### Standard Glossary (English term → Chinese gloss)

Use these on first mention if the audience may benefit. Do not over-translate; for routine financial acronyms in body prose, the original Latin acronym is fine.

| Term | Chinese gloss |
|---|---|
| ARR | 年度经常性收入 |
| NRR | 净收入留存率 |
| Gross retention | 毛留存率 |
| Burn rate | 现金消耗率 |
| Runway | 现金可支撑时间 / 增长空间（按语境） |
| GTM | 市场进入策略 |
| Moat | 护城河 |
| Deployment depth | 部署深度 |
| Replacement vs. coexistence | 替代 vs. 共存 |
| Stale-mark multiple | 旧基准估值倍数 |
| Contemporaneous multiple | 同期估值倍数 |
| Forward multiple | 前瞻估值倍数 |
| Growth bridge | 增长拆解 |
| Capital structure | 资本结构 |
| Dilution | 股权稀释 |
| Liquidation preference | 清算优先权 |
| Scenario analysis | 情景分析 |
| Pre-mortem | 预先反思 |
| Reverse IC | 反向投资委员会 |
| Confidence: High / Medium / Low | 信心度：高 / 中 / 低 |
| Status: Supported / Partially supported / Unproven / Disconfirmed | 状态：支持 / 部分支持 / 未证实 / 已被否定 |

### Recommendation Verdict Translations

Use exactly these strings:

| English | Chinese |
|---|---|
| Proceed | 建议参与 |
| Proceed if confirmed | 确认后建议参与 |
| Hold pending confirmation | 待确认后再决定 |
| Pass | 不推荐 |

### Translation Quality Rules

- The Chinese memo is a **faithful translation**, not a paraphrase or summary. Every claim, every number, every disconfirming fact, and every decision question in the English memo must appear in the Chinese memo.
- Do not soften critical warnings, valuation timing caveats, or disconfirming evidence in translation. Tone-shift in either direction is a defect.
- Do not introduce new analysis in the Chinese memo that is not in the English memo.
- Use formal written Chinese (书面语), not colloquial register. The audience is institutional investors.
- Use idiomatic Chinese finance / research phrasing. If a literal translation sounds odd, keep the English term with a brief Chinese explanation rather than forcing a calque.
- Numerical and currency formatting stays in original form (e.g., `$420M`, not `4.2亿美元`) unless Serena specifies localization.
- Dates stay in `YYYY-MM-DD` form.
- Inline citation markers and source identifiers stay in their original form.
- When a Latin acronym appears in a Chinese sentence, leave one half-width space on each side for readability (e.g., `公司的 ARR 增长` rather than `公司的ARR增长`).

### Typography for the Chinese Memo

Apply this font system to the Chinese `.docx`:

| Element | Font (in priority order) |
|---|---|
| Body text | "Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", "SimSun" |
| Cover title (BSH) | "Microsoft YaHei", "Noto Sans CJK SC" — bold, Navy `1B2A4A` |
| Headings | "Microsoft YaHei", "Noto Sans CJK SC" — bold, Navy `1B2A4A` |
| Table headers | "Microsoft YaHei", "Noto Sans CJK SC" — bold, white on Navy fill |
| Latin / numeric runs inside Chinese paragraphs | Arial (the docx engine normally falls back to Arial automatically; if not, set the runs explicitly) |

Other typography rules:
- Use Chinese-style punctuation (，。；：「」『』《》) for Chinese-language sentences. Do not mix Latin punctuation into Chinese sentences.
- Increase body line spacing slightly to 1.15 for the Chinese memo to improve CJK character readability.
- Tables: keep the same Navy header / Pale Tiffany alternating row design; only the text content changes.
- Page numbers: use `第 X 页` format in the footer of the Chinese memo (e.g., `第 1 页`, `第 2 页`).
- Running header on body pages: `[Company Name] | BSH 机密投资备忘录`

### Cover Page (Chinese Version)

Mirror the English cover layout. Required text content:
- Berkeley Summit House — 机密投资备忘录
- 公司：[Name in original form]
- 日期：[YYYY-MM-DD]
- 编制人：Serena
- 阶段：[Late-Stage / Pre-IPO / Growth — keep English label, optionally append Chinese gloss in parentheses]
- 行业：[AI / Consumer / etc. — keep English label, optionally append Chinese gloss]
- 地点：[City, Country in original form]

The cover title `BERKELEY SUMMIT HOUSE` stays in English. The subtitle `Confidential Investment Memo` is translated to `机密投资备忘录`.

---

## Step 4: Formatting Notes

## Document Style System (Mandatory)

Apply an explicit style system. Do not rely on default Word theme formatting.

### Font System
- Body font: Arial, 10pt or 10.5pt
- Cover title (BSH): Arial, 24–28pt, bold, Navy `1B2A4A`
- Cover company name: Arial, 22–26pt, bold, Navy `1B2A4A`
- Cover subtitle / descriptor: Arial, 13–15pt, Grey `666666`
- Heading 1: Arial, 15–16pt, bold, uppercase, Navy `1B2A4A`
- Heading 2: Arial, 11.5–12.5pt, bold, Navy `1B2A4A`
- Heading 3 / subsection labels: Arial, 10–10.5pt, bold, Black `111111`
- Table header text: Arial, 9.5–10pt, bold, White `FFFFFF`
- Table body text: Arial, 9.5–10pt
- Footer / header text: Arial, 9pt, Grey `666666`

### Color Palette
Use the BSH palette consistently:
- Navy `1B2A4A` — major headings, major title text, table header backgrounds
- Tiffany Blue `0ABAB5` — accent rules, left borders on callout boxes, thin dividers
- Pale Tiffany `E6F7F6` — alternating table row shading, evidence callouts
- White `FFFFFF` — table header text
- Grey `666666` — secondary metadata text
- Black `111111` — body text
- Soft Gold `C9A227` — optional restrained accent for valuation warnings or citation markers
- Pale Gold `F7F0D9` — warning callout background
- Warm Grey `F3F3F3` — neutral callout background

Use accent colors sparingly. Maintain sharp institutional layout; avoid decorative styling.

## Cover Page Styling

The cover page must exceed the initial version, not merely match it.

Preferred cover-page composition:
- Small brand line or header at top
- Large centered `BERKELEY SUMMIT HOUSE`
- Centered subtitle `Confidential Investment Memo`
- Thin Tiffany divider line
- Large centered company name
- Optional company descriptor in grey
- Centered metadata block beneath

Preferred metadata block implementation:
- borderless centered table or tightly controlled centered paragraphs
- clean spacing between rows
- no loose left-column labels stacked awkwardly
- no excessive empty space between title and metadata

If supported, use a different first page so the cover has no running header and no visible footer page number.

## Header / Footer Contract

- Running header on body pages: `[Company Name] | BSH Confidential Investment Memo`
- Header text must be compact and subdued
- Include a thin accent line only if it improves clarity and does not clutter the page
- Footer must display a real visible page-number field

Required page-number behavior:
- `Page 1`, `Page 2`, etc. must render visibly
- A footer that displays only `Page` with no number is a failure
- If the cover page suppresses numbering, ensure numbering starts correctly on the next page

## Paragraph Spacing & Density

Target a compact but readable memo.

Recommended settings:
- Body paragraphs: 1.05–1.12 line spacing
- Paragraph spacing after body text: 3–5pt
- Heading 1 spacing: 12–16pt before, 5–7pt after
- Heading 2 spacing: 8–10pt before, 3–5pt after
- Table spacing: 4–8pt before and after
- Avoid consecutive blank paragraphs as a spacing method

Use compact spacing suitable for serious review without cramped pages.

## Section Header Treatment

Heading 1 must have:
- bold uppercase navy text
- strong hierarchy
- a Tiffany underline rule or bottom border
- consistent spacing before and after

Heading 2 must:
- be bold navy
- remain visually distinct from body text
- not look like plain paragraph labels

Do not let section headings default to generic Word heading styles without explicit formatting.

## Table Design Standard

Tables are a core part of the memo package and must look deliberate.

Required table design rules:
- Header row: Navy fill `1B2A4A`, White bold text
- Body rows: alternating white / Pale Tiffany `E6F7F6` shading where useful
- Borders: subtle and clean; avoid heavy grid clutter
- Cell padding: comfortable but compact
- Numeric columns: right-align where appropriate
- Text columns: left-align
- Repeat header row on page breaks when supported
- Keep tables with their headings where possible

Recommended table uses:
- Key Metrics Snapshot (in Executive Summary → Investment Opportunity)
- Board of Directors (in Company Overview → Team)
- Revenue (in Company Overview)
- Key Metrics (in Company Overview)
- Competitive matrix (in Investment Highlights)
- Moat (in Investment Highlights)
- Risk Register (in Investment Risk)
- Time-Base Integrity Table (in Financial Forecast & Valuation)
- Growth Bridge (in Financial Forecast & Valuation)
- Scenario Analysis (in Financial Forecast & Valuation)
- Validation & Assumptions Log (appended)

## Callout Box Design Standard

All critical callouts must be visually differentiated from body text.

### Critical Warning Box
- Left border: Tiffany Blue `0ABAB5`
- Background: Pale Gold `F7F0D9` or Pale Tiffany `E6F7F6`
- Label line in bold
- Compact internal spacing
- Use for stale-mark warnings, missing unit economics, key caveats

### Evidence Summary Box
- Left border: Tiffany Blue
- Background: Pale Tiffany
- Use for What BSH Is Buying, What Still Needs Confirmation, Bear-Case Evidence, and Evidence Required Before the Next Step-Up

### Confirmation Bar Box
- Background: Warm Grey or Pale Tiffany
- Use for Closing Confirmation Bars and recommendation-support thresholds

Do not render these as plain paragraphs with only bold text.

## Executive Summary Layout Rules

The Executive Summary must have visible structure and follow the five-subsection order: Investment Opportunity → Investment Thesis → Investment Risk → Investment Recommendation → Closing Confirmation Bars.

Required elements:
- Key Metrics Snapshot table inside Investment Opportunity
- Valuation Timing Warning (for BSH) callout inside Investment Opportunity when contemporaneous vs stale-mark multiples differ materially
- deal-specific investor-facing evidence callout when it improves IC readability
- Closing Confirmation Bars callout inside the Executive Summary
- Visible separation between Opportunity, Thesis, Risk, Recommendation, and Closing Confirmation Bars

The Executive Summary must be highly skimmable in under two minutes.

## Page Architecture Rules

- Cover page alone
- Executive Summary begins on page 2
- Avoid hard page breaks before every section
- Use page breaks deliberately only for major readability wins
- Prevent orphaned headings and stranded callouts
- Keep important tables close to the paragraphs that introduce them
- Avoid half-empty pages created by poor break logic
- Appendix may be denser and more utilitarian than the main body

## Visual Quality Standard

Use the visual standard of a high-quality LP-facing sell-side investment memo, not a default generated report.

It must:
- look polished without feeling glossy
- privilege clarity, comparability, and scan-ability
- make critical warnings impossible to miss
- present structured data in tables rather than prose walls
- maintain visual consistency from cover page through appendix

---

## Step 5A: Analytical and Visual Validation Before Finalizing


Do not finalize the memo unless all of the following are true:

### Analytical Requirements
1. At least 3 arithmetic pressure tests are explicitly performed.
2. Every major thesis claim has at least one independent secondary source OR is clearly marked as company-reported / unproven.
3. At least one disconfirming fact is surfaced for each major bullish argument.
4. Revenue quality is discussed separately from revenue size.
5. Customer count is translated into likely deployment depth.
6. Corpus / data moat claims are broken into owned, exclusive, licensed, and conditional components where relevant.
7. Integrations / agents / APIs are analyzed in terms of real-world adoption, not just feature availability.
8. Replacement versus coexistence is quantified or explicitly marked unresolved.
9. Scenario analysis includes evidence, not just valuation math.
10. Numeric probabilities are used only when the evidence basis is explicitly stated.
11. Every material valuation multiple is labeled as contemporaneous, forward, or stale-mark shorthand.
12. A growth bridge is completed for every deal; if direct evidence is unavailable, the bridge uses ranges and labels the unattributed remainder.
13. Average-based conclusions include an explicit distribution caveat where relevant.
14. Missing critical unit economics reduce confidence rather than being treated as neutral omissions.
15. Tier 3 review sources are not used as primary proof of topline claims.
16. All analysis artifacts are saved into the current run folder.
17. `logs/run_manifest.md` and `logs/file_inventory.md` exist and are complete.
18. Both the English and Simplified Chinese final memo files exist inside a unique run-specific `memo/` directory and share the same timestamp.
19. No prior run files were overwritten.

### Final Prose QA Requirements

Before DOCX generation, scan the English memo body and remove:
- banned phrases from the Human Executive Memo Voice Contract
- detached third-person recommendation, opportunity, or base-case framing
- self-referential memo/document/process language and writer-process language
- bracketed source tokens, source IDs, file names, artifact names, and raw source traces outside the Sources, Source Classes, and Fact Reference Index
- meta language about "the memo", "the analysis", "the framework", "this section", or the writing process
- methodology leakage from claim registers, research tasks, evidence matrices, validation logs, confidence scoring, or reviewer prompts
- scaffold labels such as "Critical Reality Check", "present-state", "upside-state", "upside-only", "Strongest independent support", and "Still unproven"
- fuzzy phrases such as "soft instrument", "hard IP wall", "moat narrows", "no-rights SAFE", "where nothing else works", and "least-proven part of the story"
- English em dash bridges in body prose and operating tables
- repetitive openings and symmetrical bullet phrasing that make the memo feel generated
- over-explained risks that belong as one-sentence risk statements with evidence in compact notes or tables
- template-visible structure and unnatural model voice

If a sentence explains how the memo was built, rewrite it as the investment judgment. If a sentence apologizes for missing data, state the uncertainty directly.

### Visual / Formatting Requirements
20. The cover page uses the mandatory cover-page layout and does not look like a loose metadata note.
21. Body pages use explicit fonts and sizes; the document does not fall back to default Word theme formatting.
22. Section headers are styled consistently and visibly.
23. The Executive Summary follows the five-subsection order (Investment Opportunity → Investment Thesis → Investment Risk → Investment Recommendation → Closing Confirmation Bars) and includes:
    - a Key Metrics Snapshot table inside Investment Opportunity
    - a Valuation Timing Warning (for BSH) callout inside Investment Opportunity when contemporaneous vs stale-mark multiples differ materially
    - a deal-specific investor-facing evidence callout when it improves IC readability
    - an explicit Investment Recommendation verdict (Proceed / Proceed if confirmed / Hold pending confirmation / Pass)
    - a Closing Confirmation Bars callout
24. All mandatory table-driven sections are actually rendered as tables (Key Metrics Snapshot, Board of Directors, Revenue, Key Metrics, Competitive Analysis, Moat, Risk Register, Time-Base Integrity, Growth Bridge, Scenario Analysis, Validation & Assumptions Log).
25. The memo contains at least **8** tables.
26. The memo contains at least **3** callout boxes.
27. The footer shows visible page numbers (`Page 1`, `Page 2`, etc.). A footer that renders as only `Page` is a hard failure.
28. The document has no large accidental blank regions caused by poor page-break logic.
29. Important tables are kept near their headings and not stranded awkwardly.
30. The memo does not visually resemble default Word output.

### Bilingual Output Requirements
31. A Simplified Chinese `.docx` exists alongside the English `.docx` in the same `memo/` directory and shares the same timestamp.
32. The Chinese memo uses the exact section header translations specified in the **Bilingual Output** section.
33. The Chinese memo uses CJK-safe fonts (Microsoft YaHei or Noto Sans CJK SC) for all CJK text; Latin / numeric runs inside Chinese paragraphs render in Arial.
34. The Chinese memo's tables, callouts, recommendation verdict, and Closing Confirmation Bars match the English memo's content exactly — only the language differs.
35. The Chinese memo preserves company name, executive names, ticker symbols, currency amounts, percentages, and dates in their original Latin form (per the translation scope rules).
36. The Chinese memo uses Chinese-style punctuation (，。；：「」《》) inside Chinese-language sentences and leaves a half-width space on either side of any Latin acronym embedded in a Chinese sentence.
37. The Chinese memo's footer renders page numbers as `第 X 页` and the running header reads `[Company Name] | BSH 机密投资备忘录`.

### Visual QA Gate
Before delivery, perform visual QA on rendered output or preview pages of **both the English and Chinese memos**, sufficient to inspect:
- cover page
- executive summary page
- at least one table-heavy page
- footer/page-number rendering (including `Page X` for English and `第 X 页` for Chinese)
- one later body page with section headers and callouts
- for the Chinese memo: a CJK-rendering check to confirm fonts resolve correctly and there are no `□` tofu boxes

If rendered page inspection is available, save preview images under:
```text
logs/previews/
logs/previews_cn/
```

If either memo fails visual QA, fix the layout before delivery.

If any of these conditions are not met, state the limitation directly and convert unresolved items into expected bars, support thresholds, or stop/revisit conditions.

---

## Step 5: Validate and Present


After writing `logs/memo_package.json`:
1. Confirm `logs/memo_package.json` is the only dynamic rendering input and no generated renderer script exists in the run folder.
2. Do not run the fixed renderer yourself. The server will render, validate,
   update `logs/run_manifest.md`, and update `logs/file_inventory.md`.
3. Briefly summarize in the chat reply: recommendation, top 2 reasons to proceed or pass, and the top 3 expected bars. Use English for the chat summary unless Serena requests otherwise.
4. Do not move, rename, or delete prior runs as part of presentation.

---

## Thesis Checklist Quick Reference

| BSH Criterion | Details |
|---------------|---------|
| Sector | AI — consumer-facing and business-facing AI startups |
| Stage | Growth / late-stage / pre-IPO (direct); mid-stage via GP partners. Calibrate expectations to the actual round. |
| Founder background | Immigrant or underrepresented background |
| Founder ethnicity | Asian ethnicity preferred |
| Relationship | Long-term partnership mindset |
| Values | Human-centered tech; service to people and planet |

---

## Example Usage

**Serena says:** "Can you evaluate this pre-IPO deal? I have the Pitchbook summary."  
→ Check for `BSH Assistant/[Company Name]/` folder → read all documents in it (PitchBook, CB Insights, partner notes, etc.) → create a new run folder → note late-stage context (GP partner channel) → run full analysis passes → produce English `.docx` memo → translate to Simplified Chinese → produce Chinese `.docx` memo → validate both → present both files

**Serena says:** "We're being offered allocation in [Company]'s next round — late-stage, pricing is set. Write the memo."  
→ Check for `BSH Assistant/[Company]/` folder → read PitchBook / CB Insights / partner notes → create a new run folder → build dated valuation table (last priced mark vs. current ARR), growth bridge, capital structure / dilution analysis, and competitive compression review → produce English `.docx` memo with risk register, scenario table, and validation log → translate to Simplified Chinese → produce Chinese `.docx` memo → validate both → present both files

**Serena says:** "Can you write up [Company] — there's a secondary opportunity at a late-stage mark."  
→ Check for `BSH Assistant/[Company]/` folder → read all documents in it → create a new run folder → flag the contemporaneous-vs-stale-mark multiple distinction in the executive summary callout → run pressure tests including post-acquisition reality and core franchise resilience → produce English `.docx` memo → produce Simplified Chinese `.docx` memo → validate both → present both files

**Serena says:** "Here's an early-growth deal — write the memo."
→ Run the memo with stage-calibrated expectations. Do not force pre-IPO diligence norms onto a Series A/A2 or early-growth financing.

---

## Final Principle

Prefer a memo that is precise, critical, and partially unresolved over a memo that is smooth, confident, and weakly validated.

This system is only successful if it preserves execution reliability, memo consistency, non-destructive storage, and investment rigor all at once.

It must prefer:
- dated, traceable, source-aware arithmetic over slogan-like valuation framing
- growth bridges over blended growth narratives
- distribution-aware deployment analysis over average-only math
- top 3 expected bars over long undifferentiated diligence lists
- confidence calibrated to missingness, not confidence despite missingness
