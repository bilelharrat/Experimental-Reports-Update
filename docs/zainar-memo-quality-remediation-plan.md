# ZaiNar Memo Quality Remediation Plan

Last updated: 2026-06-22

## Purpose

This plan tracks the concrete fixes needed after reviewing the generated
ZaiNar memo, the hand-edited comparator, screenshots, the existing memo
pipeline docs, and the previous Human Executive Memo Voice prompt upgrade.

The prior style upgrade improved the prompt stack, but the latest generated
memo shows the final-output contract is still internally inconsistent:

- The prompt wrapper says the final memo should hide process scaffolding.
- The memo skill still requires inline citation markers in material
  paragraphs.
- The memo skill still mandates a "Critical Reality Check" callout whose
  labels read like an analysis scaffold, not an IC memo.
- The output has no hard post-generation lint gate for bracketed source
  tokens, methodology labels, em dash overuse, or non-human phrasing.

The goal is not to make the memo less rigorous. The goal is to keep source
traceability and uncertainty discipline in the analysis layer, while the final
memo reads like a serious investor document.

## Evidence Reviewed

- Generated memo: `/Users/rparker/Downloads/ZaiNar, Inc. - Investment Memo - 2026-06-22__093627.docx`
- Hand-edited comparator: `/Users/rparker/Downloads/Seline0617BSH_ZaiNar_Investment_Memo_Final_Exec_Ready_2026-06-16.docx`
- Screenshots showing citation leakage, weak warning language, and "Critical
  Reality Check" output.
- Prior plan: `docs/investment-memo-style-upgrade-plan.md`
- Pipeline doc: `docs/memo-pipeline.md`
- Research hardening doc: `docs/research-tools-improvement-plan.md`
- Memo skill: `server/skills/bsh_investment_memo_latestage.md`
- Prompt wrapper: `server/claude_runner.py`
- Memo packet handoff: `server/serena_analysis.py`

## Progress Tracker

| Workstream | Status | Notes |
|---|---:|---|
| Extract generated and hand-edited memo text | Done | Generated memo has 14 source-like bracket leaks, 16 total square-bracket references, 52 em dashes, and mandated scaffold labels. |
| Locate prompt/spec conflicts | Done | `server/skills/bsh_investment_memo_latestage.md` requires inline citation markers and "Critical Reality Check". |
| Define remediation issues | Done | See issue list below. |
| Update final memo source-trace contract | Done | `server/skills/bsh_investment_memo_latestage.md` now bans inline source markers in body/tables and requires source-class language plus a fact reference index. |
| Replace scaffolded Executive Summary components | Done | Mandatory "Critical Reality Check" was removed; investor-facing evidence callouts are now contextual. |
| Strengthen introduction and conclusion contract | Done | Skill and wrapper now require opening thesis, memo spine, and a final Investment Decision / Closing View before Sources. |
| Add disclosure-gap modeling contract | Done | Skill and wrapper now require disclosed / not disclosed / source class / model treatment / change-the-model handling plus default conversion ranges. |
| Add hard final-output linter | Done | Added `server/memo_quality_lint.py` and wired it into normal memo completion and stale-run recovery as a fail-closed English DOCX quality gate. |
| Add focused prompt and linter tests | Done | Added prompt, packet, linter, and memo worker quality-gate tests for source leakage, scaffold phrases, fuzzy phrases, em dash, disclosure gaps, and table cells. |
| Run a fresh ZaiNar memo regression | Pending | Not launched in this implementation pass; requires a fresh external memo generation and review against the new linter. |

## Implementation Notes - 2026-06-22

- Resolved the prompt/spec conflict by making the final-writing override explicitly supersede old inline-citation and scaffold-label instructions.
- Kept detailed traceability available in analysis artifacts and the fact index, while banning raw source IDs and internal artifact names from Sections I-V and operating tables.
- Added a compact memo spine handoff to `memo_packet.md`: `core_bet`, `entry_tension`, `current_proof`, `unproven_but_modelable`, `kill_criteria`, and `action`.
- Added a DOCX quality gate that extracts paragraphs and table cells, classifies source/fact-index and validation appendix sections, writes `logs/memo_quality_lint.md`, and marks reports `failed_quality_gate` on P0 findings.
- Verified with focused tests:
  - `PYTHONPATH=. pytest tests/test_memo_quality_lint.py tests/test_memo_prep.py tests/test_memo_analysis.py -q`
  - `PYTHONPATH=. pytest tests/test_serena_analysis.py -q`

## Root Cause

This is not one bad generation. It is a spec conflict.

`server/skills/bsh_investment_memo_latestage.md` currently says:

- "Every material paragraph ... must include at least one inline citation
  marker or equivalent source trace."
- The Executive Summary must include a "Critical Reality Check (for BSH)"
  evidence-summary callout.
- Investment Thesis bullets must make clear whether each point is a
  "present-state fact" or "upside-state thesis."

Those instructions push the model toward visible research scaffolding. The
prompt wrapper then asks for partner-level voice, but it does not override the
specific visible-components mandate strongly enough. The generated memo obeyed
the old structural rule and violated the desired finished-memo rule.

## Hand-Edited Comparator Lessons

The hand-edited memo is a better structural model than the generated memo, but
it should not be copied wholesale. It shows the right analytical moves while
still preserving some phrases that should be tightened in the next prompt pass.

What to preserve:

- It opens with the company, the network-side positioning claim, the stealth
  history, the $1B public mark, the Series A2 valuation, and the BSH vehicle.
  That is the right first-paragraph fact stack.
- It separates the technical claim from valuation proof. The memo explains
  that current revenue is not disclosed and then immediately shifts to
  commercial-traction modeling.
- It uses "Source class / treatment" and "Memo treatment" columns rather than
  raw internal source tokens in prose.
- It treats $500M contracts/MOUs, $5B pipeline, Kajima LOI, DoD contracts,
  carrier engagements, and ecosystem logos differently instead of collapsing
  them into one revenue story.
- It adds `Investment Risks and Model Treatment`, `Return Framework and Exit
  Scenarios`, and `Evidence Required for a Step-Up Case`. These are much closer
  to how an early-commercial, high-valuation private deal should be underwritten.

What still needs improvement:

- The opening still says "The investment case is not that..." and "would imply
  false precision." Those were already in the prior banned-phrase table and
  need to be replaced with a direct investment view.
- The `Investment View` paragraph still says "The memo therefore frames..."
  which is process language.
- Source IDs such as `[S1]`, `[S3, S11]`, and `[S12]` still appear in the Key
  Metrics table. The next version should move those IDs to the fact reference
  index and keep the main table clean.
- The hand-edited memo is stronger in the middle than at the end. It has
  evidence required for a step-up, but it does not close with a concise action:
  how much to invest, under what conditions, what would kill the deal, and what
  the next diligence call must resolve.

## Issue List

### 1. Inline Source Tokens Leak Into Finished Prose And Tables

Severity: P0

Examples from generated memo:

- "no battery cost [WV SPV memo]"
- "effective entry near $2.55B [WV SPV memo]"
- "Last priced valuation | ~$1.0B+ post-money (2026-02-19) [companies.yaml]"
- "Round in front of BSH | Series A2, ~$3.0B pre-money ... [WV]"
- "Replacement / coexistence | ~3 composite; 4 in GPS-denied industrial [internal]"
- "subject to claim-scope review [WV; companies.yaml]"

Why this fails:

- It makes the memo look like an internal research scratchpad.
- File names such as `companies.yaml` should never appear in the finished
  memo.
- The citation style interrupts executive prose and table scanning.

Fix plan:

- Replace "inline citation marker" with "source-class treatment in the body,
  source trace in a separate fact reference index."
- Allow bracketed IDs only inside a dedicated `Sources`, `Fact Reference
  Index`, or `Validation & Assumptions Log` section, never in body prose,
  Key Metrics Snapshot, Investment Thesis, Investment Risk, or normal tables.
- Convert body source proof into human language:
  - Bad: "120+ patents filed, 90+ issued [WV; companies.yaml]"
  - Better: "Company materials report 120+ filed patents and public patent
    sources support a broad issued estate; claim breadth still needs counsel
    review."
- Add a DOCX text/table linter that fails if source-like bracket patterns
  appear before the source appendix.

Acceptance:

- No `[` source markers in body prose or operating tables.
- No final memo text contains `companies.yaml`, `source_trace`, `WV`, `RP
  note`, `memo_packet`, or internal artifact names outside the source index.

### 2. The Source Strategy Is All-Or-Nothing Instead Of Reader-Calibrated

Severity: P0

Examples from generated memo:

- Body paragraphs use `[WV SPV memo]` as proof.
- Key Metrics cells append `[companies.yaml]` or `[internal]`.
- Sources and validation appendix also exist, creating duplicate and noisy
  provenance.

Useful comparator pattern:

- The hand-edited memo uses a `Source class / treatment` column and later a
  `Sources, Source Classes, and Disclosures` section.
- Example: "Revenue / ARR | Not disclosed | Model does not infer ARR from
  contract/MOU headline."
- Example: "$500M+ contracts + MOUs | Company public release; initial CEO
  meeting ... | Binding-vs-MOU split not disclosed. Treated as commercial
  momentum, not backlog or ARR."

What still needs improvement:

- Even the comparator keeps `[S1]` IDs in the Key Metrics table. The desired
  rule should be stricter: source IDs belong in the fact reference index, not
  in the main memo tables.

Fix plan:

- Define three source surfaces:
  1. Main body: source-class words only, such as "company-reported",
     "publicly disclosed", "management discussion", "internal model".
  2. Operating tables: "Treatment" columns, no bracket IDs.
  3. Fact Reference Index: fact IDs, source title, source class, date,
     confidence, and usage.
- Update `VI. Sources & References` into `Sources, Source Classes, and Fact
  Reference Index`.
- Keep detailed traceability in `analysis/claim_register.md` and the appendix,
  not in the IC narrative.

Acceptance:

- A reader can understand whether a claim is company-reported, independently
  supported, estimated, or unresolved without seeing internal citation tokens.
- The fact index can map every material claim back to source details.

### 3. "Critical Reality Check" Is A Scaffold, Not Executive Language

Severity: P0

Examples from generated memo:

- "CRITICAL REALITY CHECK (for BSH)"
- "Strongest independent support:"
- "Strongest disconfirming facts:"
- "Still unproven:"
- "Already true vs upside-only:"
- "What must be true for the bull case:"

Why this fails:

- It reads like a prompt checklist was pasted into the memo.
- It explains the analysis taxonomy instead of making the investment point.
- It flattens the memo into labels rather than judgment.

Fix plan:

- Remove the mandatory "Critical Reality Check" component from the skill.
- Replace with one of these investor-facing components, selected by deal
  context:
  - `Valuation Timing Warning`
  - `What BSH Is Underwriting`
  - `What Is Not Yet Underwritten`
  - `Evidence Required Before the Next Step-Up`
  - `Bear-Case Evidence`
- Convert taxonomy into sentence-level investment implications:
  - Bad: "Strongest disconfirming facts: No disclosed recognized revenue..."
  - Better: "The valuation is moving faster than the revenue proof. The hard
    commercial evidence today is DoD, a named industrial account, and
    management-reported contract/MOU figures."

Acceptance:

- The final memo contains no "Critical Reality Check", "Strongest independent
  support", "Still unproven", or "Already true vs upside-only" strings.

### 4. Disclosure Gaps Are Not Being Converted Into Model Treatment

Severity: P0

Examples from generated memo:

- "Recognized revenue / ARR | Not disclosed"
- "No disclosed recognized revenue"
- "Contract structure, average contract value, and retention are not
  disclosed."
- "ARR per customer | Not computable - revenue undisclosed"

Why this fails:

- Early-stage and early-commercial companies often have disclosure gaps.
  Stopping at "not disclosed" is not analysis.
- The memo should state the gap, classify the source, and decide how the model
  treats the gap.

Better comparator examples:

- "Model does not infer ARR from contract/MOU headline."
- "Pipeline is not contracted revenue. Treated with a 5-15% risk-adjusted
  conversion range for scenario construction."
- "MOUs | 15-35% | Apply to commercial intent signals without binding purchase
  obligations."
- "LOIs | 10-25% | Apply to named expansion plans ... before binding site
  contracts."

Fix plan:

- Add a mandatory `Disclosure Gap -> Model Treatment` rule:
  - State what is disclosed.
  - State what is not disclosed.
  - Classify the available data: signed, cancellable, MOU, LOI, pipeline,
    management target, public third-party, internal estimate.
  - Use conservative ranges or Fermi estimates where useful.
  - Explain what would change the model.
- Create a default conversion framework for private-company commercial claims:
  - binding signed: 80-100%
  - signed but cancellable/milestone-based: 50-75%
  - MOU: 15-35%
  - LOI: 10-25%
  - pipeline: 5-15%
  - unqualified ecosystem logo: 0% revenue credit unless contract status is
    disclosed
- Require at least one outside-in sanity bridge for revenue-disclosure gaps:
  customer count, site count, contract value, term length, employee count,
  implementation capacity, or comparable contract duration.

Acceptance:

- Every material "not disclosed" statement is paired with model treatment.
- "Not computable" appears only when followed by the proxy framework that will
  be used instead.

### 5. Investment Thesis Bullets Are Fuzzy And Over-Labeled

Severity: P0

Examples from generated memo:

- "A real technical asset behind a hard IP wall (present-state)."
- "Demand where nothing else works (present-state)."
- "Optionality across carrier and Physical-AI monetization (upside-state)."
- "A team that has built this category before (present-state)."

Why this fails:

- "real technical asset", "hard IP wall", and "where nothing else works" are
  broad phrases, not investment claims.
- Parenthetical labels expose the prompt taxonomy.
- The bullets use a repetitive adjective-noun pattern that reads generated.

Fix plan:

- Ban visible `(present-state)` and `(upside-state)` labels in the final memo.
- Force thesis bullets to follow this shape:
  - first sentence: crisp investor claim
  - second sentence: source/treatment and what must prove true
  - no parenthetical taxonomy
- Example target rewrite:
  - "ZaiNar has a credible technical wedge in GPS-denied environments. The
    near-term case rests on industrial and defense deployments where GPS,
    camera, UWB, and BLE are operationally weaker; carrier monetization and
    Physical-AI data should remain upside until production economics are
    disclosed."

Acceptance:

- Thesis bullets have no parenthetical state labels.
- Each bullet includes a concrete claim, proof point, and dependency.

### 6. Fuzzy Or Cute Phrases Replace Precise Deal Mechanics

Severity: P0

Examples from generated memo:

- "the moat narrows toward a licensing claim"
- "A soft instrument into an unclosed round."
- "a no-rights SAFE"
- "the price pays for the least-proven part of the story"
- "Demand where nothing else works"

Why this fails:

- The wording sounds clever but obscures the actual mechanics.
- "No-rights SAFE" is too casual and may be legally imprecise.
- The memo needs to describe the instrument, rights, conversion dependency,
  dilution, and preference stack plainly.

Fix plan:

- Add a banned/concerning phrase list:
  - "soft instrument"
  - "hard IP wall"
  - "moat narrows"
  - "where nothing else works"
  - "no-rights SAFE"
  - "least-proven part of the story"
  - "upside-only"
- Replace with concrete language:
  - "BSH would own an SPV interest whose economics depend on the SAFE
    converting in the A2 as described. Information, consent, transfer, and
    voting rights are governed by the SPV and subscription documents, not by a
    direct company shareholding."
  - "If standards-based positioning becomes good enough, ZaiNar's upside shifts
    from product margin to patent leverage and deployment relationships."

Acceptance:

- No banned fuzzy phrases appear in final memo text.
- SAFE/SPV wording describes rights and conversion mechanics without slang.

### 7. Em Dash Bridging And Long Run-On Sentences Hurt Executive Prose

Severity: P1

Examples from generated memo:

- "Series A2, ~$3.0B pre-money — closing imminent"
- "No honest contemporaneous revenue multiple exists — ARR is undisclosed."
- "If 3GPP standardizes native SRS positioning, the moat narrows toward a
  licensing claim — the company's own stated fallback."
- "GPS-denied industrial and defense settings — construction, logistics, a
  signed $36M DoD program — ZaiNar enables..."
- The generated document had 52 em dashes in extracted text.

Why this fails:

- The punctuation is being used to stitch together clauses the model has not
  resolved.
- In memo prose, short sentences and semicolons are usually clearer.

Fix plan:

- Ban em dashes in final English memo body and tables except when a source
  title legally contains one.
- Add a linter check for em dash count. Target: zero in body prose.
- Prompt rewrite instruction:
  - split the sentence,
  - use a colon for explanation,
  - use parentheses sparingly for definitions,
  - use semicolon only when both clauses are short.

Acceptance:

- Final English memo body and operating tables contain no em dash characters.

### 8. The Executive Summary Architecture Is Too Template-Driven

Severity: P1

Examples from generated memo:

- Five fixed subheads: Investment Opportunity, Investment Thesis, Investment
  Risk, Investment Recommendation, Open Questions.
- Mandatory callouts: Valuation Timing Warning, Critical Reality Check, Top 3
  Gating Questions.
- Repeated labels in bullets and callouts create a worksheet feel.

Better comparator direction:

- The hand-edited memo uses sections that match the transaction:
  - `Commercial Traction and Business Model`
  - `Technology, IP, and Competitive Position`
  - `Investment Risks and Model Treatment`
  - `Return Framework and Exit Scenarios`
  - `Evidence Required for a Step-Up Case`
  - `Sources, Source Classes, and Disclosures`

Fix plan:

- Keep a stable memo backbone but make the Executive Summary less rigid.
- For early-commercial or disclosure-light companies, prefer:
  - Investment Opportunity
  - Why This Could Matter
  - What Is Priced In
  - What Is Not Yet Underwritten
  - Investment View
  - Evidence Required Before Funding or Step-Up
- Allow callouts only when they add investor value. Do not require three
  callouts in every memo.

Acceptance:

- No mandatory worksheet labels in the Executive Summary.
- Callouts are deal-specific and investor-facing.

### 9. Tables Mix Metrics, Sources, And Methodology In The Same Cell

Severity: P1

Examples from generated memo:

- "Last priced valuation | ~$1.0B+ post-money (2026-02-19) [companies.yaml]"
- "Round in front of BSH | Series A2, ~$3.0B pre-money ... [WV]"
- "ARR per employee | ~$200-270K on proxy revenue; unproven [internal]"
- "Independent directors | Not disclosed | -"

Why this fails:

- Main tables should be readable first and auditable second.
- Source markers, methodology, and evidence state need their own table role.

Fix plan:

- Define table roles:
  - Snapshot table: metric and value only, optionally a short treatment phrase.
  - Model treatment table: claim, disclosure status, treatment, implication.
  - Fact reference index: fact, source class, source detail, confidence, usage.
- Ban source IDs and file names in snapshot tables.
- Avoid placeholder dashes; use "Not disclosed", "Not applicable", or omit the
  row.

Acceptance:

- Key Metrics Snapshot contains no bracketed references and no internal file
  names.
- Any table that includes source details is clearly labeled as a source or fact
  reference table.

### 10. The Memo Treats Early-Commercial Stage As A Problem Instead Of A Modeling Context

Severity: P1

Examples from generated memo:

- "early adoption" appears as a broad negative without conversion math.
- "no disclosed recognized revenue" is repeated without a structured bridge.
- "carrier monetization runs on 18-36 month cycles with zero live revenue" is
  true but not turned into a timing model.

Better comparator examples:

- "Model 18-36 month carrier sales cycles and 3-5 year contract duration."
- "Treat as LOI with 10-25% conversion until site-level contracts are
  disclosed."
- "A $20-30M recognized software revenue / ARR baseline would materially
  de-risk the step-up case."

Fix plan:

- Add an early-commercial underwriting mode inside the late-stage memo skill.
- When recognized revenue is unavailable, require:
  - disclosed commercial signals,
  - model treatment,
  - proxy range,
  - validation threshold,
  - what would change the recommendation.
- Make "Evidence Required for a Step-Up Case" a standard section for
  disclosure-light high-valuation companies.

Acceptance:

- The memo does not repeatedly complain that data is missing.
- It uses missing data to set conservative treatment and diligence thresholds.

### 11. Previous Voice Fix Is Directionally Right But Too Weak

Severity: P1

Examples from previous fix that still leaked or remain insufficient:

- Prior banned phrase: "The investment case is not that..."
- The hand-edited comparator still contains: "The investment case is not that
  ZaiNar is a conventional software company..."
- Prior banned phrase: "The memo therefore..."
- Comparator still contains: "The memo therefore does not present a precision
  financial forecast."
- Generated memo avoids some exact banned phrases but produces new variants:
  "present-state", "upside-state", "Critical Reality Check", "soft
  instrument".

Fix plan:

- Expand from a small banned phrase table to a category-based style linter:
  - internal-source leakage,
  - methodology labels,
  - prompt taxonomy labels,
  - cute finance phrases,
  - em dash bridges,
  - "memo/framework/analysis" meta language,
  - unresolved disclosure gaps without model treatment.
- Add positive rewrite exemplars specific to ZaiNar-style deals.

Acceptance:

- Tests cover both old and new style regressions.
- The prompt no longer relies only on exact phrase bans.

### 12. Memo Packet And Tool Artifacts Can Still Leak Into Final Prose

Severity: P1

Examples from generated or current artifacts:

- The final memo uses source labels like `[internal]` and `[WV]`.
- `memo_packet.md` explicitly carries "Strongest source-backed support",
  source traces, reviewer prompts, design prompts, no-go claims, and
  information gaps.
- The memo skill and packet both use labels that are useful internally but
  dangerous in final prose.

Fix plan:

- Strengthen `server/serena_analysis.py` memo packet handoff:
  - add "never copy source labels, artifact names, reviewer prompts, or
    bracket source tokens into body prose or operating tables."
  - add "convert to source-class and model-treatment language."
- Make source traces available to a fact index builder, not to normal prose.
- Keep optional tools opt-in in UI, but when their outputs are included in
  memo generation, label them as `analysis_input`, not `final_language`.

Acceptance:

- Generated final memo has no visible Memo Studio artifact labels.

### 13. No Hard Final-Output QA Gate Catches These Failures

Severity: P0

Observed failures:

- Bracket source tokens were present in body and tables.
- `companies.yaml` appeared in a finished table.
- "Critical Reality Check" appeared despite user-facing style goals.
- 52 em dashes appeared.
- "present-state", "upside-state", "soft instrument", and "no-rights SAFE"
  appeared.

Fix plan:

- Add a final memo quality linter that extracts text from DOCX paragraphs and
  table cells.
- Checks should include:
  - bracket source leakage outside source sections,
  - internal file/source names,
  - banned scaffold headings and labels,
  - banned fuzzy phrases,
  - em dash count,
  - meta language about "the memo" or "the analysis",
  - "not disclosed" without nearby model-treatment language,
  - operating tables with source IDs in cells.
- On failure, either:
  - run a focused repolish prompt before completion, or
  - mark the report as `failed_quality_gate` with a clear error and artifacts
    preserved.

Acceptance:

- A generated DOCX like the current ZaiNar output fails the linter.
- A cleaned memo with source references only in the fact index passes.

### 14. Opening Paragraphs Do Not Yet Carry The Full Investment Frame

Severity: P0

Examples from generated memo:

- "ZaiNar spent nine years in stealth solving one hard problem..." opens with
  the company story but leaks `[WV SPV memo]` and waits too long to state the
  valuation/proof tension.
- "The opportunity in front of BSH is a co-investment..." describes the
  instrument, but the paragraph does not state the investment judgment.
- The Key Metrics Snapshot arrives before the reader has a clean answer to:
  what are we being asked to buy, at what price, and what proof supports that
  price?

Comparator strengths:

- The hand-edited memo opens with founding year, product definition, stealth
  period, public emergence, $100M cumulative investment, $1B+ prior valuation,
  Series A2 valuation, and the BSH SPV.
- It then introduces the price/proof frame: ZaiNar is not priced on disclosed
  ARR; the case depends on converting reported commercial momentum into
  binding deployments.

Comparator weaknesses:

- "The investment case is not that..." is a weak negative construction.
- "would imply false precision" is model-like phrasing.
- The opening still does not state a clear recommendation posture.

Fix plan:

- Add a required `opening thesis` contract before any memo body is written:
  - sentence 1: what the company is and why it matters;
  - sentence 2: what BSH is being asked to buy and at what entry terms;
  - sentence 3: the central underwriting tension;
  - sentence 4: the current recommendation posture and the gates that can move
    it.
- The opening must include the price/proof frame when valuation has moved
  faster than disclosed revenue evidence.
- Ban negative-setup openings such as "The investment case is not..." and
  process phrases such as "The memo frames..."
- Provide a positive exemplar in the skill:
  - "ZaiNar is a scarce technical asset in network-side positioning, but the
    A2 asks BSH to pay today for commercial proof that is only partly visible.
    The right posture is a small conditional allocation, not a full-conviction
    growth-stage underwriting, unless the company can show that the reported
    contract/MOU base is binding, repeatable, and not concentrated in one or
    two accounts."

Acceptance:

- The first two body paragraphs state company, transaction, valuation, central
  underwriting tension, and recommendation posture.
- The introduction contains no source tokens, no "the memo" meta-language, and
  no negative throat-clearing.

### 15. Conclusions And Investment View Need A Harder Action Standard

Severity: P0

Examples from generated memo:

- "Recommendation: Conditional Yes - a small ticket at or near the $500K SPV
  minimum..." is directionally useful, but it is buried before the detailed
  analysis and not reinforced at the end.
- "If any of the first two fail, this is a Pass at this mark..." is a good
  kill criterion, but it should be carried into a final Investment View.

Examples from hand-edited memo:

- "This is a high-risk, high-upside infrastructure allocation at a premium
  valuation..." states posture but not a crisp invest/pass recommendation.
- `Evidence Required for a Step-Up Case` is strong, but it reads like a
  milestone list rather than a final decision close.
- The disclosures section is the final prose the reader sees; that is legally
  useful but narratively weak for an IC memo.

Fix plan:

- Add a mandatory final `Investment Decision` or `Closing View` before Sources
  and Disclosures.
- The final close must state:
  - recommendation: Yes, Conditional Yes, Need More Information, or Pass;
  - allocation posture: minimum ticket, full allocation, watchlist, or pass;
  - required pre-funding evidence;
  - kill criteria;
  - what changes the next-round/step-up case;
  - next diligence actions in priority order.
- Require the conclusion to mirror the opening frame. If the opening says
  "scarce technical asset priced ahead of proof", the conclusion must answer
  whether the proof is enough for BSH to act.
- Keep legal disclaimers after sources, but do not let disclosures serve as
  the memo's substantive ending.

Acceptance:

- The memo has a substantive final investment close before Sources.
- The close tells BSH what to do next, not only what evidence is missing.
- The final paragraph contains no "the memo", "the framework", or
  "method note" language.

### 16. The Memo Needs A Reusable Narrative Spine, Not Isolated Good Sections

Severity: P1

Observed in the comparator:

- The middle sections are strong because they classify commercial signals and
  model treatment.
- The opening, `Investment View`, return scenarios, and step-up evidence are
  related, but the prompt does not force them to use the same spine.
- As a result, one section can say "premium valuation", another says "high-risk
  high-upside", and another says "evidence required", without a final integrated
  decision.

Fix plan:

- Add a `memo spine` object to the final prompt and/or memo packet:
  - `core_bet`: what has to be true;
  - `entry_tension`: what the price already assumes;
  - `current_proof`: what is proven today;
  - `unproven_but_modelable`: what is missing but can be modeled;
  - `kill_criteria`: what makes BSH pass;
  - `action`: recommended check size and conditions.
- Require introduction, Investment View, risk section, scenario section, and
  final close to use this same spine.
- Add a linter or prompt test that the final memo includes a recommendation
  and at least two explicit gating conditions when the recommendation is
  Conditional Yes.

Acceptance:

- Opening and conclusion are consistent in recommendation, risk posture, and
  valuation framing.
- The final memo does not read as separate generated sections stitched
  together.

## Implementation Plan

### Phase 1: Resolve The Spec Conflict

Files:

- `server/skills/bsh_investment_memo_latestage.md`
- `server/claude_runner.py`
- `tests/test_memo_prep.py`

Tasks:

- Replace the claim-to-source traceability rule with a final-memo source
  strategy:
  - no inline source markers in final prose,
  - source-class language in the body,
  - fact reference index for traceability.
- Remove mandatory "Critical Reality Check" and visible
  present-state/upside-state labels.
- Add a stronger prompt-wrapper override that explicitly supersedes conflicting
  skill text.
- Add tests asserting the prompt contains the new ban and does not require
  inline citation markers or Critical Reality Check.

### Phase 2: Add Disclosure-Gap Modeling Rules

Files:

- `server/skills/bsh_investment_memo_latestage.md`
- `server/claude_runner.py`
- `tests/test_memo_prep.py`

Tasks:

- Add `Disclosure Gap -> Model Treatment` instructions.
- Add default commercial conversion ranges for signed, cancellable, MOU, LOI,
  and pipeline claims.
- Require Fermi/outside-in proxies when direct revenue metrics are unavailable.
- Add examples using ZaiNar-style signals: $500M contracts/MOUs, $5B pipeline,
  $36M DoD, Kajima LOI, 16 RAN vendors, 5+ telcos.

### Phase 3: Replace Scaffolded Sections With Investor-Facing Sections

Files:

- `server/skills/bsh_investment_memo_latestage.md`
- `server/serena_analysis.py`
- `tests/test_serena_analysis.py`

Tasks:

- Make callouts opt-in based on deal context.
- Add accepted callout types:
  - `Valuation Timing Warning`
  - `What Is Priced In`
  - `What Is Not Yet Underwritten`
  - `Bear-Case Evidence`
  - `Evidence Required Before the Next Step-Up`
- Update memo packet handoff so tool labels do not become final headings.

### Phase 3A: Strengthen Introduction, Investment View, And Closing

Files:

- `server/skills/bsh_investment_memo_latestage.md`
- `server/claude_runner.py`
- `server/serena_analysis.py`
- `tests/test_memo_prep.py`
- `tests/test_serena_analysis.py`

Tasks:

- Add an opening-thesis contract: company, transaction, valuation, central
  underwriting tension, recommendation posture.
- Add a final `Investment Decision` / `Closing View` section before Sources.
- Require Conditional Yes conclusions to include allocation posture, gates,
  kill criteria, and next diligence actions.
- Add a memo-spine handoff field or prompt block so the opening and conclusion
  use the same core frame.
- Add tests asserting the prompt includes the opening/conclusion contract and
  bans process-language endings.

### Phase 4: Add The DOCX Quality Linter

Files:

- New: `server/memo_quality_lint.py`
- `server/memo_analysis.py`
- `tests/test_memo_quality_lint.py`

Tasks:

- Extract DOCX paragraphs and tables with `python-docx`.
- Classify text by section so source IDs can appear only in source/fact-index
  sections.
- Return structured findings with severity, phrase, location, and suggested
  remediation.
- Wire the linter after DOCX generation and before report completion.
- Decide whether P0 linter findings trigger automatic repolish or report
  failure. Default recommendation: fail closed first, then add repolish once
  the quality gate is stable.

### Phase 5: Add Prompt And Output Regression Tests

Files:

- `tests/test_memo_prep.py`
- `tests/test_serena_analysis.py`
- `tests/test_memo_quality_lint.py`
- Optional fixture DOCX or synthetic DOCX builder in tests.

Tests:

- Prompt no longer requires inline citations.
- Prompt explicitly bans source token leakage in body and tables.
- Prompt bans "Critical Reality Check", "present-state", "upside-state",
  "soft instrument", "hard IP wall", and em dash bridging.
- Linter catches:
  - `[WV SPV memo]` in paragraph text,
  - `[companies.yaml]` in a table cell,
  - `Critical Reality Check`,
  - `present-state`,
  - `no-rights SAFE`,
  - em dash in body text,
  - repeated "not disclosed" without model treatment.
- Linter allows:
  - fact IDs inside a dedicated fact reference index,
  - source class text such as "company-reported" in normal tables.

### Phase 6: Re-Run ZaiNar End-To-End

Tasks:

- Generate a fresh ZaiNar memo after Phases 1-5.
- Run the DOCX linter.
- Render and inspect table-heavy pages.
- Compare against this issue list:
  - no bracket citations in body/tables,
  - no internal file names,
  - no scaffold callouts,
  - no em dash bridges,
  - introduction states company, deal, valuation, price/proof tension, and
    recommendation posture,
  - final close states allocation posture, gates, kill criteria, and next
    diligence actions,
  - disclosure gaps converted into model treatment,
  - SAFE/SPV mechanics stated plainly,
  - source index exists and is usable.

## Definition Of Done

The remediation is complete when:

- The final memo body reads as an investor memo, not as a research workflow.
- Main prose and operating tables contain no bracketed source tokens.
- Source traceability exists in a separate fact/source index.
- Disclosure gaps produce model treatment, ranges, or explicit diligence
  thresholds.
- The Executive Summary no longer includes analysis-scaffold labels.
- The introduction makes the investment frame clear in the first two body
  paragraphs.
- The final close states what BSH should do and what would change the decision.
- Generated DOCX output passes the memo quality linter.
- Focused tests pass, and a fresh ZaiNar memo regression is reviewed.
