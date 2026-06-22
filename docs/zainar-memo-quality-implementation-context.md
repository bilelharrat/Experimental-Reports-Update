# New Context: Implement ZaiNar Memo Quality Remediation

Use this document as the starting context for a fresh implementation thread.

## Repository Rules

- Work in `/Users/rparker/Documents/GitHub/bsh-research-center`.
- Work directly on `main`. Do not create branches or worktrees.
- Do not revert unrelated dirty files. The working tree may already include
  Memo Tools UI/progress changes plus the remediation plan.
- Do not commit or push unless the user explicitly asks.

## Objective

Implement the memo-quality remediation described in:

- `docs/zainar-memo-quality-remediation-plan.md`

The current generated ZaiNar memo exposed internal research scaffolding and
source tokens in the finished DOCX. The implementation should make the final
memo read like a serious investor memo while preserving source traceability in
analysis artifacts and a separate fact/source index.

## Source Documents Reviewed

- Generated memo:
  `/Users/rparker/Downloads/ZaiNar, Inc. - Investment Memo - 2026-06-22__093627.docx`
- Hand-edited comparator:
  `/Users/rparker/Downloads/Seline0617BSH_ZaiNar_Investment_Memo_Final_Exec_Ready_2026-06-16.docx`
- Plan:
  `docs/zainar-memo-quality-remediation-plan.md`
- Existing style plan:
  `docs/investment-memo-style-upgrade-plan.md`
- Pipeline:
  `docs/memo-pipeline.md`
- Research tools hardening:
  `docs/research-tools-improvement-plan.md`

If you re-open the DOCX files, use the Documents skill and the bundled
workspace Python runtime. Text extraction with `python-docx` is enough for
content analysis; render/visual QA is required only if generating or editing a
DOCX deliverable.

## User-Visible Problem

The generated memo included output such as:

- `no battery cost [WV SPV memo]`
- `effective entry near $2.55B [WV SPV memo]`
- `Last priced valuation | ~$1.0B+ post-money (2026-02-19) [companies.yaml]`
- `Round in front of BSH | Series A2, ~$3.0B pre-money ... [WV]`
- `A real technical asset behind a hard IP wall (present-state).`
- `Optionality across carrier and Physical-AI monetization (upside-state).`
- `the moat narrows toward a licensing claim`
- `A soft instrument into an unclosed round.`
- `CRITICAL REALITY CHECK (for BSH)`
- `Strongest independent support:`
- `Still unproven:`
- 52 em dashes in extracted generated memo text.

These are not acceptable in the final memo body or operating tables.

## Root Cause

The current prompt stack has a spec conflict:

- `server/claude_runner.py` injects `HUMAN_EXEC_MEMO_VOICE_CONTRACT`, which
  says the finished memo should avoid process language and methodology leakage.
- `server/skills/bsh_investment_memo_latestage.md` still requires inline
  citation markers or equivalent traces in material body paragraphs.
- The skill also mandates `Critical Reality Check (for BSH)` and visible
  present-state/upside-state distinctions in the Executive Summary.
- `server/serena_analysis.py` memo packets still contain useful internal
  labels, source traces, reviewer prompts, no-go claims, and source-backed
  support labels that can leak if the final prompt is too permissive.
- There is no hard DOCX quality linter after generation.

Fix the conflict at the spec/prompt level and add an output gate.

## Comparator Lessons

The hand-edited memo is better because it:

- opens with company, product, stealth period, public emergence, prior public
  valuation, Series A2 valuation, and BSH SPV vehicle;
- frames the case as a scarce infrastructure asset priced ahead of fully
  disclosed revenue proof;
- uses source-class/model-treatment columns instead of raw internal source
  tokens in prose;
- treats contracts, MOUs, LOIs, pipeline, ecosystem logos, and DoD contracts
  differently;
- includes `Investment Risks and Model Treatment`, `Return Framework and Exit
  Scenarios`, and `Evidence Required for a Step-Up Case`.

But do not copy its remaining weak phrases:

- `The investment case is not that...`
- `would imply false precision`
- `The memo therefore...`
- source IDs like `[S1]` in the Key Metrics table.

The next version must make the introduction and conclusion stronger:

- First two body paragraphs must state company, transaction, valuation, central
  price/proof tension, and recommendation posture.
- The final close must state what BSH should do, allocation posture, funding
  gates, kill criteria, and next diligence actions.
- Legal disclosures should not be the memo's substantive ending.

## Target Behavior

Main memo body and operating tables:

- No bracketed source tokens.
- No internal file names such as `companies.yaml`, `memo_packet`, `source_trace`,
  or `WV`.
- No prompt scaffolding such as `Critical Reality Check`, `present-state`,
  `upside-state`, `Strongest independent support`, or `Still unproven`.
- No cute/fuzzy phrases such as `soft instrument`, `hard IP wall`, `moat
  narrows`, `no-rights SAFE`, or `where nothing else works`.
- No em dash bridging in English final body/tables.
- Disclosure gaps must be translated into model treatment, conversion ranges,
  Fermi estimates, or explicit diligence thresholds.

Allowed traceability:

- Source-class language in body/tables, e.g. `company-reported`,
  `management discussion`, `public third-party`, `internal model`.
- A dedicated `Sources, Source Classes, and Fact Reference Index` section can
  carry detailed source IDs and source titles.
- Analysis artifacts such as `analysis/claim_register.md` may retain detailed
  traceability.

## Prioritized Implementation

### 1. Update The Memo Skill Contract

File:

- `server/skills/bsh_investment_memo_latestage.md`

Changes:

- Replace the current claim-to-source traceability rule with:
  - no inline source markers in final body prose or operating tables;
  - source-class language in body;
  - separate fact/source index for detailed traceability.
- Remove the mandatory `Critical Reality Check` component.
- Remove visible `present-state` / `upside-state` labels. Keep the analytical
  distinction private and translate it into normal language.
- Add the disclosure-gap modeling rule:
  - disclosed / not disclosed / source class / model treatment / what would
    change the model.
- Add default private-company conversion ranges:
  - binding signed: 80-100%;
  - signed but cancellable or milestone-based: 50-75%;
  - MOU: 15-35%;
  - LOI: 10-25%;
  - pipeline: 5-15%;
  - unqualified ecosystem logo: 0% revenue credit without contract status.
- Add opening-thesis contract:
  - company;
  - transaction;
  - valuation/entry terms;
  - central underwriting tension;
  - recommendation posture.
- Add final `Investment Decision` / `Closing View` requirement before Sources:
  recommendation, allocation posture, gates, kill criteria, next diligence.

### 2. Strengthen The Prompt Wrapper Override

File:

- `server/claude_runner.py`

Changes:

- Expand `HUMAN_EXEC_MEMO_VOICE_CONTRACT` so it explicitly supersedes any
  older skill instruction that asks for inline source markers or scaffolded
  labels in final prose.
- Add explicit bans for:
  - bracketed source tokens in body/tables;
  - internal artifact names;
  - `Critical Reality Check`;
  - `present-state`, `upside-state`, `upside-only`;
  - `soft instrument`, `hard IP wall`, `moat narrows`, `no-rights SAFE`;
  - em dash bridging;
  - `the memo`, `the analysis`, `the framework`, `this section`.
- Add positive examples for ZaiNar-style early-commercial infrastructure deals.
- Require opening/conclusion consistency through a `memo spine`:
  `core_bet`, `entry_tension`, `current_proof`, `unproven_but_modelable`,
  `kill_criteria`, and `action`.

### 3. Harden Memo Packet Handoff

File:

- `server/serena_analysis.py`

Changes:

- Update `_refresh_memo_packet()` final handoff guidance:
  - analysis packet is evidence, not copy;
  - never copy source labels, reviewer prompts, artifact names, bracketed source
    tokens, or scaffold labels into final body prose or operating tables;
  - convert source traces into source-class/model-treatment language;
  - use detailed source traces only for the fact reference index or validation
    appendix.
- If appropriate, add a compact memo-spine section to `memo_packet.md` so the
  final memo can align intro, risk, scenario, and close.

### 4. Add DOCX Memo Quality Linter

New file:

- `server/memo_quality_lint.py`

Likely tests:

- `tests/test_memo_quality_lint.py`

Design:

- Extract paragraphs and table cells from DOCX.
- Classify content as main body vs source/fact-index/validation appendix.
- Return structured findings: severity, code, location, snippet, suggestion.
- P0 findings should include:
  - source-like brackets outside source/fact-index sections;
  - internal file/artifact names outside allowed sections;
  - `Critical Reality Check`;
  - prompt taxonomy labels;
  - banned fuzzy phrases;
  - em dash in English body/table text;
  - `not disclosed` repeated without nearby model-treatment terms;
  - source IDs in Key Metrics / operating tables.
- The linter should allow:
  - source IDs inside a dedicated source/fact-index section;
  - source-class words such as `company-reported` in main tables;
  - appendix validation logs with detailed traceability if clearly separated
    from body.

Dependency note:

- Check whether `python-docx` is available in the app/runtime environment before
  importing it in server code. If adding a hard dependency is risky, implement a
  fallback using `zipfile` + OOXML text extraction for tests and runtime.

### 5. Wire The Linter Into Memo Completion

Files:

- `server/memo_analysis.py`
- Possibly `server/api.py` or report metadata storage if exposing findings in
  the UI.

Changes:

- Run the linter after Claude creates the English DOCX and before marking the
  report complete.
- Recommendation: fail closed on P0 findings first. Mark the report as a
  quality-gate failure with artifacts preserved and findings written under
  `logs/memo_quality_lint.json`.
- Optional later improvement: automatic focused repolish when linter findings
  are narrow and repairable.
- Do not let a memo with bracketed source leakage or scaffold headings be marked
  complete.

### 6. Add Focused Tests

Files:

- `tests/test_memo_prep.py`
- `tests/test_serena_analysis.py`
- `tests/test_memo_quality_lint.py`
- Possibly `tests/test_memo_analysis.py` for completion-gate behavior.

Required assertions:

- `_build_investment_memo_prompt()` contains the final source strategy and
  explicit bans.
- Prompt no longer requires inline citation markers in final body paragraphs.
- Prompt no longer mandates `Critical Reality Check`.
- Prompt includes opening-thesis and final-closing requirements.
- `_refresh_memo_packet()` includes the stronger source/scaffold leakage warning.
- Quality linter catches:
  - `[WV SPV memo]` in paragraph text;
  - `[companies.yaml]` in table cells;
  - `Critical Reality Check`;
  - `present-state`;
  - `upside-state` / `upside-only`;
  - `soft instrument`;
  - `no-rights SAFE`;
  - em dash body text;
  - repeated `not disclosed` without model treatment.
- Quality linter allows:
  - source IDs inside source/fact-index section;
  - source-class terms in body tables.

## Suggested Patch Order

1. Update `server/skills/bsh_investment_memo_latestage.md`.
2. Update `server/claude_runner.py` prompt wrapper.
3. Update `server/serena_analysis.py` memo packet handoff.
4. Add `server/memo_quality_lint.py`.
5. Add linter unit tests.
6. Wire linter into `server/memo_analysis.py`.
7. Add memo-analysis completion-gate test.
8. Run focused tests.
9. Optionally run frontend tests only if UI/report status payload changes.

## Verification Commands

Use the repo's existing test style. Likely commands:

```bash
PYTHONPATH=. pytest tests/test_memo_prep.py tests/test_serena_analysis.py tests/test_memo_quality_lint.py tests/test_memo_analysis.py
npm test
npm run lint
```

If no frontend files change, the npm commands are optional.

## Acceptance Criteria

Implementation is done when:

- Generated final memo prompts no longer ask for inline citation markers in
  body prose.
- Final memo contract requires separate source/fact index traceability.
- Introduction contract is explicit and strong.
- Final Investment Decision / Closing View contract is explicit and strong.
- Disclosure gaps must produce model treatment.
- Memo packet handoff cannot leak tool/source scaffolding into final prose.
- DOCX quality linter fails the current generated ZaiNar-style defects.
- Memo completion does not mark a P0-linted memo complete.
- Focused tests pass.

## Do Not Do

- Do not weaken evidence discipline.
- Do not remove analysis artifacts such as claim registers or validation logs.
- Do not hide uncertainty. Convert it into source class, model treatment,
  ranges, and decision gates.
- Do not copy the hand-edited memo's remaining weak phrases into the prompt as
  exemplars.
- Do not make source references disappear entirely. Move them to the right
  surface.

