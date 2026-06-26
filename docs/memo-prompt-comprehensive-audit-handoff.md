# Memo Prompt Comprehensive Audit Handoff

Last updated: 2026-06-26

## Purpose

This document is the starting context for a comprehensive memo-prompt audit and
remediation pass. The goal is not to patch one bad phrase at a time. The goal is
to read every prompt that can influence memo generation, correct the underlying
thinking and grammar directly, and verify through multiple independent paths
that the review covered the full prompt surface.

The immediate failure mode came from the ZaiNar memo. The generated memo used
awkward, draft-like, and internally oriented language such as:

- `We invest behind technical infrastructure...`
- `We back...`
- `The recommendation is...`
- `Closing Confirmations`
- `Investment conditions`
- `Confirm...`
- `wisdom should be able share`
- `this memo`, `our memo`, `the memo frames`

These are not isolated generation mistakes. They are symptoms of prompt language
that still mixes brainstorming notes, diligence scaffolding, internal workflow
labels, and final investor-facing memo instructions.

## Repository And Workflow Rules

- Work in `/Users/rparker/Documents/GitHub/bsh-research-center`.
- Work directly on `main`. Do not create branches or worktrees.
- Do not revert unrelated dirty files.
- Do not commit or push unless the user explicitly asks.
- Use `rg` first for prompt and phrase inventory.
- Use `apply_patch` for manual file edits.
- Keep a traceable record of what prompt surfaces were reviewed and changed.
- Do not run the full memo code path, Claude agent, Serena agent, or ZaiNar
  regeneration before the prompt review, prompt edits, re-read, scans, and
  focused tests have been completed.

## Objective

Make the memo-generation prompt stack produce polished, direct, sell-side
investment memo language from the beginning. The final memo should read like a
finished BSH investor memo, not an internal note, diligence checklist, prompt
fragment, or AI-generated draft.

The remediation must be expansive:

1. Read every memo-related prompt carefully, including prompts embedded in code,
   markdown skills, deterministic fallbacks, UI labels, packet handoffs, lint
   rules, and tests.
2. Fix root causes in the prompts, not just generated output.
3. Replace weak negative-only bans with positive, concrete writing rules.
4. Re-read the changed prompts after editing.
5. Verify coverage through multiple independent inventory methods.
6. Update lint/tests so the same failures are caught before another long memo
   run.

## Tracking Contract

Use this document as the live tracker for the comprehensive prompt pass. Update
the tracking tables while the work is happening, not after the fact.

### Status Values

Use these exact statuses in the ledgers:

| Status | Meaning |
|---|---|
| `TODO` | Known surface or task has not been reviewed yet. |
| `READ` | Surface was read in the stated scope, but no edit decision has been made. |
| `NEEDS_CHANGE` | Surface contains prompt language, labels, examples, or tests that must change. |
| `CHANGED` | Surface has been edited, but not yet re-read or verified. |
| `VERIFIED` | Surface was re-read after edits and passed the relevant scan/test. |
| `DEFERRED` | Surface was intentionally excluded with a concrete reason. |
| `BLOCKED` | Surface cannot be evaluated without missing artifacts, access, or user input. |

### Phase Tracker

| Phase | Status | Required Evidence Before Advancing |
|---|---|---|
| 1. Inventory prompt-bearing files | `VERIFIED` | File inventory command was run across `server`, `docs`, and `tests`; active memo surfaces, adjacent docs, tests, non-memo prompts, and generated caches were classified below. |
| 2. Inventory functions/constants | `VERIFIED` | Prompt builders, constants, wrappers, packet builders, deterministic fallbacks, visible labels, and lint/cleanup surfaces are listed in the surface and symbol ledgers. |
| 3. Classify bad-language hits | `VERIFIED` | Post-edit hits are classified as active prompt risk removed, internal-only workflow label, linter/cleanup pattern, intentional test fixture, historical doc, or audit-document example. |
| 4. Classify positive examples | `VERIFIED` | Positive examples in the voice contract, main memo prompt, English/bilingual package prompt, and memo skill were re-read and rewritten where they taught stale cadence. |
| 5. Trace call chain | `VERIFIED` | API/prep to memo analysis, Claude package creation, Serena packet inputs, DOCX rendering, linting, and resume recovery were traced through the listed surfaces. |
| 6. Review artifacts | `DEFERRED` | Reported ZaiNar failures were traced to likely prompt/fallback/lint gaps; no fresh ZaiNar run artifacts were inspected because the no-full-run gate remains active. |
| 7. Draft prompt change plan | `VERIFIED` | Decisions D01-D05 were applied file-by-file before the final verification pass. |
| 8. Apply prompt/lint/test edits | `VERIFIED` | Prompt, deterministic fallback, cleanup, renderer validation, lint, and test fixture changes were made with scoped patches. |
| 9. Re-read changed prompts | `VERIFIED` | Changed prompt blocks and adjacent deterministic/lint/test blocks were re-read after editing and before the final scan. |
| 10. Run focused tests and scans | `VERIFIED` | `PYTHONPATH=. pytest tests/test_memo_docx_renderer.py tests/test_memo_quality_lint.py tests/test_memo_prep.py tests/test_memo_analysis.py tests/test_serena_analysis.py -q` passed: 138 passed, 2 existing FastAPI deprecation warnings. `npm test -- MemoAnalysisDashboard.spec.js MemoPanels.spec.js` passed: 18 passed. Remaining high-risk scan hits are classified in `Re-Audit Resolution - 2026-06-26`. |
| 11. Decide on full agent/code run | `DEFERRED` | Full memo/agent run remains blocked until the user explicitly accepts this prompt-language pass and asks to run the full code path. |

### No-Full-Run Gate

Do not run the full memo-generation code path, Claude-backed agent, Serena
agent, or ZaiNar regeneration during the prompt rewrite phase. The next full
run is only allowed when all of these are true:

- every prompt-bearing surface in the surface ledger is `VERIFIED` or
  explicitly `DEFERRED`;
- every prompt change has a corresponding re-read entry;
- every remaining bad-language scan hit has an accepted reason;
- focused lint and prompt tests pass or have a documented non-prompt failure;
- the user explicitly agrees that the prompt language is ready to test through
  a full memo run.

## Current Re-Audit Override - 2026-06-26

The 2026-06-26 re-audit reopened the remediation pass. Several surfaces below
were previously marked `VERIFIED`, but line-by-line review found live prompt
contradictions, schema labels, deterministic fallbacks, and packet labels that
can still create internal/process/checklist prose. Treat this section as the
authoritative plan until every `R` item is `VERIFIED`.

Do not run the full memo code path, Claude agent, Serena agent, or ZaiNar
regeneration while any `R` item is `TODO`, `READ`, `NEEDS_CHANGE`, `CHANGED`, or
`BLOCKED`.

### Reopened Findings Ledger

| ID | Severity | Surface | Status | Current Risk | Required Remediation | Acceptance Criteria |
|---|---:|---|---|---|---|---|
| R01 | P0 | `server/memo_analysis.py::_MEMO_PACKAGE_VOICE_REWRITES` | `VERIFIED` | Cleanup rewrites `we want exposure to` into `BSH should participate in`, which the linter bans. | Change the replacement to first-person sponsor action language, preferably `we recommend participating in`, and scan all cleanup outputs for linter-banned replacements. | Cleanup never emits `BSH should`; cleanup tests cover the exact input phrase and pass linter-compatible output. |
| R02 | P0 | `server/skills/bsh_investment_memo_latestage.md` executive-summary callout rules | `VERIFIED` | The skill still requires `Valuation Timing Warning (for BSH)` while also banning `(for BSH)`. | Normalize every final-facing callout to `Valuation Timing Warning`; remove `(for BSH)` from English and Chinese translation guidance. | Active skill scan has no final-facing `(for BSH)` or `仅供 BSH` guidance except linter/test/audit examples. |
| R03 | P1 | `server/skills/bsh_investment_memo_latestage.md` Chinese cover instructions | `VERIFIED` | Chinese cover requires `编制人：Serena`, contradicting the no-`Prepared by` cover rule. | Remove Chinese author line and explicitly mirror the no-author rule across English and Chinese cover guidance. | Cover guidance has one consistent rule: internal authorship belongs only in run manifest, not deliverables. |
| R04 | P1 | `server/claude_runner.py::SERENA_THESIS_SPINE_SCHEMA` and parser validation | `VERIFIED` | Required names such as `top_gating_questions`, `support_threshold`, `confirmation_evidence`, and `stop_or_revisit_if_missing` steer generation toward gates/checklists. | Introduce final-neutral schema names such as `risk_valuation_sensitivities`, `support_evidence`, `downside_impact`, and `recommendation_sensitivity`; keep backward-compatible read aliases only at ingestion boundaries. | New Claude-facing schema and prompt do not require gate/question/confirmation/threshold fields; compatibility aliases are internal-only and not serialized into `memo_packet.md`. |
| R05 | P1 | `server/serena_analysis.py::_coerce_thesis_spine_payload` | `VERIFIED` | Coercer persists `top_gating_questions`, `support_threshold`, `confirmation_evidence`, and compatibility question fields into artifacts. | Normalize incoming legacy fields into neutral internal fields; avoid writing old names into newly generated artifacts except behind a clearly internal migration layer if required by existing clients. | New session artifacts use neutral field names; existing-session migration still reads legacy artifacts without changing final packet prose. |
| R06 | P1 | `server/serena_analysis.py::_refresh_memo_packet` thesis sections | `VERIFIED` | Packet reads and prints `top_gating_questions`, fallback says evidence would make us hold/pass/revisit, and strategic risks are rendered as questions. | Rewrite packet sections around `Risk And Valuation Sensitivities`, `Current Proof`, `Unproven But Modelable`, and `Downside Impact`; convert all question-shaped content before writing the packet. | `memo_packet.md` contains no `gating`, `question`, `support threshold`, `confirmation`, `hold/pass/revisit evidence`, or raw strategic-risk question labels. |
| R07 | P1 | `server/serena_analysis.py::_refresh_memo_packet` research/chart/narrative prompt sections | `VERIFIED` | Packet includes `Prompt:`, `Design prompt:`, `Reviewer prompts:`, and `Narrative reviewer prompts:` after telling the writer never to copy those labels. | Remove prompt text from the final memo packet or move it to a separate internal debug artifact not passed to memo generation; preserve only resolved decisions and evidence-backed consequences. | Memo packet contains no prompt/reviewer/design-prompt labels; tests assert prompt labels are absent from packet handoff. |
| R08 | P1 | `server/serena_analysis.py::_thesis_spine` deterministic fallback | `VERIFIED` | Fallback emits `central investment question`, `unless the evidence answers`, and instruction-like recommendation logic that can be copied. | Rewrite fallback output as investor-facing sensitivity/source-treatment language and direct recommendation placeholders. | Deterministic fallback packet reads as source material, not checklist instructions, and passes high-risk phrase scan. |
| R09 | P2 | `server/serena_analysis.py::MEMO_TOOL_DEFINITIONS` | `VERIFIED` | UI/tool labels still use `support-threshold checks`, `diligence queue`, and `threshold checks`. | Replace visible labels with `risk and valuation sensitivity review`, `source review queue`, or equivalent neutral terms. | UI labels no longer teach threshold/diligence-queue vocabulary; tests updated for new labels where applicable. |
| R10 | P2 | `server/claude_runner.py::SERENA_RESEARCH_TASK_SCHEMA` and research prompt wording | `VERIFIED` | `open_questions` and `gaps Serena still needs to close before memo generation` can leak planning voice into packet outputs. | Rename Claude-facing guidance toward `remaining_evidence_limits` and require investment implication/model treatment for each gap. | Research-task answers and packet summaries state evidence limits as valuation/source-treatment language, not open process work. |
| R11 | P2 | `server/claude_runner.py::HUMAN_EXEC_MEMO_VOICE_CONTRACT` replacement table | `VERIFIED` | `before we give full credit to...` remains process-adjacent and can sound like pre-underwriting workflow language. | Replace with direct valuation-support language such as `our base case credits... only where...` or `valuation support is strongest where...`. | Positive rewrite table contains no process-timing phrasing. |
| R12 | P2 | `server/claude_runner.py::run_serena_narrative_hooks` and deterministic narrative fallback | `VERIFIED` | `we would hold` / `we would pass` candidates may preserve conditional posture instead of final recommendation language. | Prefer `we recommend participating`, `we do not recommend participating`, and `we would not recommend participating unless...` only where explicitly needed. | Narrative candidates cannot become detached or conditional final recommendations without rewrite. |
| R13 | P2 | `server/skills/bsh_investment_memo_latestage.md` missing-information instruction | `VERIFIED` | `Information not available` can produce placeholder final prose instead of model/risk/valuation treatment. | Replace with instruction to state disclosed/undisclosed facts and their model treatment, risk implication, or valuation sensitivity. | Skill no longer permits standalone placeholder sections in final body prose. |
| R14 | P2 | `server/memo_quality_lint.py` packet/process label coverage | `VERIFIED` | Linter bans `reviewer_prompts?` with underscore but may miss copied labels such as `Reviewer prompts:` or `Design prompt:`. | Add final-body lint patterns for visible prompt labels and packet handoff labels with spaces/colons. | A generated DOCX containing prompt labels fails lint before delivery. |
| R15 | P1 | Tests covering Serena schema, packet, cleanup, skill prompt, and linter | `VERIFIED` | Current tests still assert legacy `top_gating_questions` and may not catch packet-label regressions. | Update tests after schema/packet changes; add explicit negative assertions for the reopened findings. | Focused suite passes and verifies neutral schema, packet, cleanup, and lint behavior. |
| R16 | P1 | This handoff document's older phase/surface/sign-off ledgers | `VERIFIED` | Large sections below this override still say `VERIFIED`, including rows now contradicted by R01-R15. A later pass can mistakenly treat stale verification as current truth. | Mark the old implementation record as superseded or update reopened surface rows to point to the current R items. Add an explicit "historical only" warning before stale verified ledgers. | No row below the override can be read as current sign-off for a reopened surface without also seeing the R-item blocker. |
| R17 | P1 | `server/serena_analysis.py::_refresh_memo_packet` metadata/review sections | `VERIFIED` | The memo packet emits additional copyable internal labels beyond prompts: `Confidence`, `needs_review`, `source_trace notes`, `No-go / prohibited visual claims`, `Benchmark gaps`, `Must-prove claims`, `Readiness Reviews And Waivers`, `draft`, `source_needed`, `Information gaps`, and selected-operator labels. | Treat the memo packet as a final-writer source brief. Remove or translate all metadata/review labels into investor-facing evidence, source-quality, model-treatment, or valuation-sensitivity prose; move debug metadata to a separate artifact excluded from memo generation. | `memo_packet.md` is safe if partially copied: no confidence/status/source-trace/no-go/readiness/waiver/must-prove/debug labels appear in the packet passed to memo generation. |
| R18 | P1 | Fast-path analysis schemas and markdown artifacts in `server/claude_runner.py` and `server/memo_analysis.py` | `VERIFIED` | The non-Serena fast path still feeds package synthesis with `open_questions`, `memo_uses`, `confidence`, `No ... returned`, `validation_log`, `pre_mortem`, `reverse_ic`, and other analysis-artifact labels. These can leak when no approved Serena packet exists. | Rename or box fast-pass fields as source material; rewrite markdown headings and empty-state fallbacks into source-treatment / evidence-limit language; keep `pre_mortem`, `reverse_ic`, and `validation_log` private unless converted to final risk/valuation prose. | Fast-path artifacts can guide package generation without adding copyable process labels; tests cover fallback markdown and package synthesis inputs. |
| R19 | P1 | `server/skills/bsh_investment_memo_latestage.md` IC/diligence/validation-artifact contradictions | `VERIFIED` | The skill says LP-facing sell-side memo, but also says "brief IC after live diligence", "natural IC prose", requires visible `Validation & Assumptions Log`, `Risk Register`, `Pre-Mortem`, and other working-artifact constructs. | Separate private analytical artifacts from final deliverable requirements. Final DOCX should not require validation logs, claim registers, pre-mortems, reverse IC, confidence/status labels, or audit scaffolding as visible narrative sections unless explicitly transformed into investor-facing risk/source/valuation treatment. | The full skill has one consistent deliverable model: LP-facing memo body plus source/fact reference index; private validation artifacts stay in run logs/analysis files. |
| R20 | P1 | Serena visual/chart schemas and prompts in `server/claude_runner.py` | `VERIFIED` | Chart/visual prompts require internal workflow fields such as `needs_human_choice`, `reviewer_prompts`, `design_prompt`, `prohibited_claims`, `diligence_needed`, `source_available`, and `final_memo_inclusion_state`; packet construction can surface them. | Keep visual planning metadata out of memo-generation packet, or convert it into final-safe inclusion decisions and source limitations. Rename `diligence_needed` and other process labels where they are Claude-facing. | Visual/chart artifacts may retain internal metadata for UI, but the memo packet only contains selected visual decisions, supported takeaway, source class, and model/claim limitations. |
| R21 | P2 | Memo grader schema, lessons, and future-run feedback | `VERIFIED` | `missing_diligence`, "matter at IC", "training artifact", and rewrite guidance can feed future memo lessons, creating a delayed prompt-regression path. | Rewrite grader schema and lesson serialization toward final-prose quality, source treatment, valuation sensitivity, and unsupported-claim handling. Keep internal grading labels from being reused as generation instructions. | Future memo lessons cannot reintroduce IC/diligence/process language into prompt context. |
| R22 | P1 | Linter allow/deny coverage for newly discovered packet and artifact labels | `VERIFIED` | Current lint coverage catches many internal names but permits or misses visible labels such as `Confidence`, `Source traces`, `Readiness Reviews`, `Waivers`, `No-go`, `Must-prove`, `Memo Uses`, `Pre-Mortem`, `Reverse IC`, and `Validation & Assumptions Log` in allowed sections. | Expand linter patterns and allowed-section logic so audit scaffolding is allowed only in logs/source index where intended, not in final body prose or operating tables. | A DOCX containing copied packet metadata or analysis-artifact labels fails lint unless it is in an explicitly permitted source/reference context. |
| R23 | P1 | `server/memo_prep.py` scope-warning reasons and `server/claude_runner.py` scope-warning prompt wrapper | `VERIFIED` | Scope exceptions tell the writer to proceed with "explicit caveats in the memo", "stage mismatch", "thin late-stage diligence base", and "confidence limits". Those phrases can turn source context into apologetic final prose. | Keep scope warnings in run context. Rewrite memo-facing instructions as stage calibration, source limits, model treatment, allocation sensitivity, and valuation sensitivity. | Scope-warning companies still produce investor-facing analysis without copying exception/caveat/confidence-limit language into the memo body. |
| R24 | P1 | `server/claude_runner.py::_build_resume_memo_package_prompt` and quality-gate repair tests | `VERIFIED` | Resume prompts call the prior package the "working draft" and "primary source" and ask for the "smallest substantive edits". If the prior draft contains unlinted prompt/process language, the repair pass can preserve it. | Reapply the full voice contract and high-risk scan during repair. Treat the prior draft as evidence and structure context, not authoritative prose. Tests should reject preservation-only instructions when quality failures are present. | A resume pass can fix renderer issues without locking in stale wording; bad prior prose is rewritten, not preserved by default. |
| R25 | P1 | Memo lesson ingestion across main, fast, resume, and Serena helper prompts | `VERIFIED` | Existing `memo_lessons` / `lessons_path` context is described as quality heuristics, but old lessons may contain banned labels or outdated style guidance and can be injected into future prompts. | Sanitize lessons before prompt injection with the current voice contract. Strip or quarantine internal labels, old headings, third-person recommendation voice, and stale examples. | A lesson containing banned phrases such as `Closing Confirmations`, `We back`, or `matter at IC` cannot appear unfiltered in a generation prompt. |
| R26 | P1 | Fast bilingual package prompt and Chinese translation guidance | `VERIFIED` | Translation parity asks for the "exact same structure" and "same English strings", while skill guidance still mentions faithful translation of decision questions. This can preserve internal English labels and literal Chinese equivalents. | Define parity as factual and analytical parity, not label parity. Add Chinese prompt-label bans and safe replacements for author lines, source traces, reviewer prompts, decision questions, and evidence placeholders. | English bad labels are not preserved in Chinese output; Chinese memo scans catch literal process labels such as `编制人`, `审阅者提示`, `源追踪`, `备忘录包`, `决策问题`, and `待补充证据`. |
| R27 | P1 | Prompt precedence language in `_build_investment_memo_prompt` | `VERIFIED` | The wrapper says the full skill text is included verbatim and to "Follow it exactly", even though the skill contains contradictory legacy instructions. | Replace with an explicit precedence ladder: current voice contract, renderer contract, source-boundary rules, and remediated final-output rules override any older skill text. | No active wrapper tells Claude to follow contradictory skill text exactly without a current-contract override. |
| R28 | P1 | BSH mandate/background language in `server/skills/bsh_investment_memo_latestage.md` | `VERIFIED` | The mandate context includes founder-background and ethnicity-preference language. If copied into memo guidance, it can make protected or sensitive traits sound like investment merit. | Separate mandate history from investment analysis. Instruct the writer not to treat protected characteristics as positive or negative investment criteria; founder background may be discussed only when sourced, relevant, and tied to company-building facts. | Final memo prompts do not ask for demographic preference language, and tests/scans cover sensitive mandate terms that should not appear as investment rationale. |
| R29 | P1 | Source intake instructions in `server/skills/bsh_investment_memo_latestage.md` | `VERIFIED` | The skill says to read every file inside the company folder and "Incorporate everything", which can cause overstuffed prose, source-process leakage, and irrelevant or sensitive detail transfer. | Replace with relevance-based source intake and data minimization. Incorporate only investment-relevant facts with source treatment, and keep raw excerpts/process metadata out of final prose. | The skill requires comprehensive review but selective use; no prompt tells the writer to incorporate every source detail into the memo. |
| R30 | P2 | Skill packaging quotas for tables, callouts, and artifacts | `VERIFIED` | Requirements such as at least 8 tables and at least 3 callouts can force filler, template-visible scaffolding, or unsupported formatting when the source base is thin. | Convert hard quotas into quality thresholds: use tables/callouts where they improve reader judgment, with required core sections only when evidence supports them. | The renderer can validate core deliverable completeness without forcing arbitrary table/callout counts or placeholder content. |
| R31 | P2 | Document/source-summary prompt excerpts and source-title handling | `VERIFIED` | Source analysis prompts preserve exact excerpts and titles for traceability. If those summaries feed memo generation, long quotes or source labels can be copied as final prose. | Mark excerpts as evidence-only, require paraphrase or short compliant quotation in the memo body, and prevent source titles/process labels from becoming section prose. | Memo prompts and packet builders treat excerpts as citation support, not copyable narrative text; scans/tests cover source-summary label leakage where applicable. |

### Re-Audit Resolution - 2026-06-26

The reopened pass is complete for prompt-language remediation. R01-R31 are
`VERIFIED` on the current codebase. The no-full-run gate remains active only
because a controlled full memo/agent run requires explicit user approval.

Applied changes:

- Cleanup rewrites now convert `we want exposure to` into first-person
  recommendation language and tests assert cleanup never emits `BSH should`.
- The active memo skill uses one final-output model: LP-facing memo body plus
  source/fact reference treatment. Chinese cover authorship, `(for BSH)`
  callouts, placeholder missing-information prose, sensitive-trait mandate
  language, read-everything/source-dump guidance, table/callout quotas, and
  visible validation-artifact requirements were removed or rewritten.
- The Claude-facing thesis schema now writes
  `risk_valuation_sensitivities`, `support_evidence`, `evidence_context`,
  `downside_impact`, and `recommendation_sensitivity`; legacy
  `top_gating_questions` and related names are read only as compatibility
  aliases.
- `memo_packet.md` is now a final-writer source brief. It no longer prints
  prompt labels, design-prompt text, reviewer-prompt text, raw strategic-risk
  questions, confidence/status/debug metadata, readiness waivers, source-trace
  note labels, no-go labels, benchmark-gap labels, or must-prove labels.
- Fast-path, resume, scope-warning, memo-lesson, source-summary, grader,
  visual/chart, bilingual, and precedence prompts were aligned to source
  treatment, model treatment, valuation sensitivity, and current voice-contract
  precedence.
- Final pre-agent pass found and removed remaining fast-path process-language
  fallbacks and schema names: `No ... returned` empty states were rewritten,
  and Claude-facing `pre_mortem_md`, `reverse_ic_md`, and `validation_log_md`
  became `downside_scenario_md`, `countercase_md`, and
  `source_treatment_assumptions_md`. Legacy names remain only as internal read
  aliases for old cached artifacts.
- Lint now blocks copied packet/process labels such as `Prompt:`,
  `Design prompt`, `Reviewer prompts`, `Confidence:`, `Source traces`,
  `Readiness Reviews`, `Waivers`, `Memo Uses`, `Pre-Mortem`, `Reverse IC`,
  and `Validation & Assumptions Log` in final body prose.
- The Memo Studio Vue dashboard now reads/writes neutral thesis sensitivity
  fields while still tolerating legacy session artifacts, and memo-tool visible
  labels now use source-evidence, operator-review, evidence-limit, and
  valuation-support language instead of reviewer-prompt/source-trace/no-go
  wording.

Verification completed:

- `PYTHONPATH=. pytest tests/test_memo_docx_renderer.py tests/test_memo_quality_lint.py tests/test_memo_prep.py tests/test_memo_analysis.py tests/test_serena_analysis.py -q`
  passed: 138 passed, 2 existing FastAPI deprecation warnings.
- `npm test -- MemoAnalysisDashboard.spec.js MemoPanels.spec.js` passed:
  2 files, 18 tests.
- `python -m py_compile server/claude_runner.py server/serena_analysis.py server/memo_analysis.py server/memo_prep.py server/memo_quality_lint.py server/memo_docx_renderer.py`
  passed.

Post-agent failure triage - 2026-06-26:

- ZaiNar run `2026-06-26__064012` completed all eight fast analysis passes but
  the English synthesis/package subprocess was interrupted by the 180-second
  silence watchdog after it read the artifacts and began drafting JSON.
- The failure was not a prompt-schema failure; all eight
  `analysis/fast/*.json` artifacts were present and marked `ok`, and the API
  reports the failed memo as resumable from analysis artifacts.
- Fixes applied: English package synthesis now uses a 600-second silence window,
  silence-watchdog interruptions are classified as retryable, retry UI wording
  says "retryable Claude interruption" rather than only "transport error", and
  the English synthesis prompt now instructs Claude to use `analysis/fast/*.json`
  as primary inputs and read markdown/source files only for targeted support.
- Verification after the triage fix: `tests/test_memo_prep.py
  tests/test_memo_analysis.py` passed 55 tests; `tests/test_memo_docx_renderer.py
  tests/test_memo_quality_lint.py tests/test_serena_analysis.py` passed 83 tests
  with the same two FastAPI deprecation warnings; memo Vue suites still passed
  18 tests.

Remaining required-scan hits are classified as follows:

- `lessons_path` / `memo_lessons`: internal variable and artifact names; lesson
  content is sanitized before writing and lesson-use prompts instruct the writer
  to strip stale labels before applying old files.
- `top_gating_questions`, `support_threshold`, `confirmation_evidence`,
  `stop_or_revisit_if_missing`, `diligence_needed`,
  `final_memo_inclusion_state`, and `needs_human_choice`: legacy read aliases
  and UI compatibility values. They are not required by new Claude-facing
  schemas and are not serialized into `memo_packet.md`.
- `missing_diligence`, `BSH should`, `reviewer prompts`, and `source traces`
  inside sanitizer/linter regexes: intentional cleanup or rejection patterns,
  not generated prompt instructions. The remaining active-code `source traces`
  hit in the voice contract is an explicit final-writing override that bans
  bracketed source-trace prose from final output.
- legacy aliases such as `pre_mortem_md`, `reverse_ic_md`,
  `validation_log_md`, `source_traces`, and compatibility catalog labels:
  internal artifact/schema compatibility paths excluded from memo-generation
  packet prose. New fast-path artifacts use `downside_scenario.md`,
  `countercase.md`, and `source_treatment_assumptions.md`.
- `source traces`, `reviewer prompts`, `open_questions`, and similar phrases in
  older planning docs, non-memo stock/research pages, browser smoke fixtures,
  and schema compatibility fixtures: historical or adjacent product surfaces
  outside the late-stage memo prompt path.
- `pre_mortem_md`, `reverse_ic_md`, and `validation_log_md`: internal read
  aliases only; the current Claude-facing schema and generated fast-path files
  use `downside_scenario_md`, `countercase_md`, and
  `source_treatment_assumptions_md`.
- Chinese process-label strings such as `源追踪`, `备忘录包`, and `审阅者提示`
  appear only in active bans that tell the writer not to use those labels.

### Remediation Workstreams

| Workstream | Scope | Owner Action | Depends On | Exit Criteria |
|---|---|---|---|---|
| W1. Source-of-truth language map | Voice contract, skill, linter, cleanup rewrites | Define canonical terms for mandate, recommendation, sensitivity, missing evidence, source treatment, and deal mechanics before editing scattered strings. | None | One canonical replacement table exists; no prompt surface contradicts it. |
| W2. Skill contradictions | Full memo skill English and Chinese instructions | Fix `(for BSH)`, Chinese author line, missing-information placeholders, and process-adjacent rewrite examples. | W1 | Full skill re-read shows no contradictory final-output instructions. |
| W3. Serena schema migration | Claude-facing schemas, parser/coercer, readiness, tests | Rename gate/question/threshold fields to neutral sensitivity fields; retain legacy read compatibility without writing legacy names into new packets. | W1 | New artifacts and packet use neutral names; legacy artifacts still load. |
| W4. Packet boundary hardening | `memo_packet.md` construction | Remove prompt labels and raw question labels from memo-generation packet; move debug/process material elsewhere or omit it. | W3 | Packet is safe source material if partially copied; packet tests prove prompt labels are absent. |
| W5. Deterministic fallback rewrite | Serena fallback artifacts and narrative fallback | Rewrite fallback text so degraded Claude paths do not reintroduce process/checklist prose. | W1, W3 | Fallback-only session passes phrase scan and packet tests. |
| W6. Guardrail alignment | Linter, cleanup, renderer validation, tests | Ensure cleanup cannot emit linter-banned phrases; linter catches visible prompt labels and internal-audience suffixes. | W1-W5 | Focused tests cover each reopened failure mode. |
| W7. Re-read and verification | Changed prompts, schemas, packets, tests | Re-read edited blocks as prose, run scans, run focused tests, and update ledgers from `CHANGED` to `VERIFIED`. | W1-W6 | Every `R` item is `VERIFIED` or explicitly `DEFERRED` with reason. |
| W8. Controlled full-run decision | Full memo/agent run | Only after user approval, run a controlled memo generation and inspect artifacts for regression. | W7 | No-full-run gate is explicitly lifted by user. |
| W9. Tracker cleanup | This handoff document | Mark stale `VERIFIED` ledgers as superseded by the current R ledger so future passes do not trust obsolete sign-off rows. | W1 | The document has one unambiguous current source of truth for prompt-readiness status. |
| W10. Recovery and stale-context hardening | Scope warnings, resume repair, lessons, and source summaries | Ensure every recovery/context path reapplies the current voice contract instead of preserving prior prose, stale lessons, or excerpt labels. | W1, W6 | Repair, scope-warning, lesson, and source-summary prompts cannot reintroduce rejected language. |
| W11. Precedence and bilingual parity | Main wrapper precedence plus English/Chinese output rules | Clarify which rules override old skill text and ensure Chinese output transforms, rather than translates, unsafe labels. | W1, W2 | Prompt hierarchy is explicit; bilingual scans cover English and Chinese process labels. |
| W12. Sensitive mandate and source minimization | BSH background, founder references, company-folder intake | Remove demographic preference framing from investment rationale and convert "incorporate everything" into selective, sourced investment analysis. | W1, W2 | Prompts handle founder background and source breadth without protected-trait rationale or raw-source dumping. |
| W13. Packaging pressure cleanup | Table/callout quotas and visible analytical artifacts | Replace arbitrary output quotas with evidence-backed completeness checks. | W1, W2, W6 | Memo completeness does not depend on filler tables, callouts, or placeholder artifact sections. |

### Implementation Sequence

1. Freeze full agent execution. Do not run memo generation or Serena/Claude
   agents while the reopened findings are unresolved.
2. Patch W1-W2 first so the main voice contract and full skill stop
   contradicting each other.
3. Patch W3 as a compatibility-aware schema migration:
   - change Claude-facing field names first;
   - update parser/coercer to accept legacy field names;
   - update packet construction to emit only neutral names;
   - update readiness/blocker labels away from `gating_questions`.
4. Patch W4-W5 so memo packets and deterministic fallbacks are safe even when
   Claude output is weak or a writer copies too much source material.
5. Patch W6 tests and lint:
   - cleanup rewrite tests for `we want exposure to`;
   - linter tests for `BSH should`, `(for BSH)`, `Reviewer prompts:`,
     `Design prompt:`, `Prompt:`, `support threshold`, and visible
     confirmation/gating labels;
   - linter and packet tests for `Confidence`, `Source traces`, `Readiness
     Reviews`, `Waivers`, `No-go`, `Must-prove`, `Memo Uses`, `Pre-Mortem`,
     `Reverse IC`, and `Validation & Assumptions Log`;
   - Serena packet tests for absence of prompt labels and legacy schema labels;
   - skill/prompt construction tests for no contradictory final-facing strings.
6. Patch W10 recovery paths so scope warnings, resume repairs, memo lessons,
   and source summaries are filtered through the same voice contract.
7. Patch W11 bilingual and precedence rules so the current contract overrides
   contradictory skill text and Chinese output does not preserve unsafe labels.
8. Patch W12-W13 for sensitive mandate language, source minimization, and
   quota-driven packaging pressure.
9. Patch W9 so stale `VERIFIED` rows cannot be mistaken for current sign-off.
10. Re-read changed blocks line by line and update the reopened findings
    ledger.
11. Run focused tests only. Do not run the full memo agent until user approval.

### Required Verification Commands

Run these after implementation, adapting only if test names move:

```bash
PYTHONPATH=. pytest \
  tests/test_memo_docx_renderer.py \
  tests/test_memo_quality_lint.py \
  tests/test_memo_prep.py \
  tests/test_memo_analysis.py \
  tests/test_serena_analysis.py \
  -q
```

```bash
rg -n -i \
  "BSH should|\\(for BSH\\)|仅供 BSH|top_gating_questions|support_threshold|confirmation_evidence|stop_or_revisit_if_missing|support-threshold|diligence queue|Prompt:|Design prompt|Reviewer prompts|Narrative reviewer prompts|central investment question|unless the evidence answers|Information not available|before we give full credit|we would hold|we would pass|Confidence:|Source traces?|source_trace notes?|No-go|prohibited visual|Must-prove|Benchmark gaps|Readiness Reviews|Waivers|Memo Uses|Pre-Mortem|Reverse IC|Validation & Assumptions Log|missing_diligence|diligence_needed|needs_human_choice|final_memo_inclusion_state|scope-warning|explicit caveats|stage mismatch|thin late-stage diligence|confidence limits|working draft|primary source for this repair pass|smallest substantive edits|memo_lessons|lessons_path|exact same structure|same English strings|decision questions?|编制人|审阅者提示|源追踪|备忘录包|决策问题|待补充证据|Follow it exactly|Asian ethnicity|ethnicity preferred|immigrant founders|Incorporate everything|read every file|at least (\\*\\*)?8(\\*\\*)? tables|at least (\\*\\*)?3(\\*\\*)? callout|Do not paraphrase excerpts|exact excerpt" \
  server/claude_runner.py server/serena_analysis.py server/memo_analysis.py server/memo_prep.py server/skills/bsh_investment_memo_latestage.md
```

```bash
git diff --check
```

Every remaining hit from the scan must be classified in the reopened findings
ledger as one of:

- intentional linter/test fixture;
- legacy compatibility read alias that is not written into new prompts or
  packets;
- audit-document example;
- internal-only debug artifact excluded from memo generation;
- false positive with a concrete reason.

### No-Full-Run Exit Criteria

The no-full-run gate can be lifted only after:

1. R01-R31 are `VERIFIED` or explicitly `DEFERRED` with a reason the user
   accepts.
2. The full memo skill and voice contract have been re-read after edits.
3. The Serena packet generated from deterministic fallbacks has been inspected
   or covered by tests for prompt/process-label absence.
4. Focused tests pass.
5. The high-risk phrase scan has no unclassified active prompt hits.
6. The user explicitly approves a controlled full memo/agent run.

## Historical Implementation Record Warning

Everything below this warning is retained for traceability from earlier audit
passes. The current source of truth is the **Current Re-Audit Override -
2026-06-26**, especially the `Re-Audit Resolution - 2026-06-26` section and
R01-R31 ledger above. Older `VERIFIED` rows in the phase tracker, prompt
surface ledger, file inventory, or sign-off notes must not be read as current
approval for any reopened surface unless they are consistent with the R-ledger
resolution above.

## Core Voice Principles

### Institutional Subject

Use `BSH` as the subject for mandate-level statements:

- Good: `BSH invests in foundational companies building Physical AI infrastructure.`
- Good: `BSH focuses on companies whose products make the physical world safer, healthier, and more productive.`

Do not use casual sponsor voice:

- Bad: `We back...`
- Bad: `We invest behind...`
- Bad: `we want exposure to...`
- Bad: `why we want to be in the room...`

### Active Investment Judgment

Use `we` only for direct investment judgment, recommendation,
investment-case treatment, and reader-facing conviction:

- Good: `We recommend participating in the SPV.`
- Good: `We evaluate the current case as an infrastructure-scarcity investment, not a current-ARR story.`
- Good: `We view the valuation as supported by technical scarcity, commercial pull, and defense relevance.`

Do not write in third-person situational voice:

- Bad: `The recommendation is...`
- Bad: `This memo recommends...`
- Bad: `The memo frames...`
- Bad: `Our memo argues...`
- Bad: `The analysis suggests...`
- Bad: `This section evaluates...`

### Final Memo, Not Internal Note

The finished memo is an offer to invest. It should advocate a recommendation
while presenting risks cleanly. It is not a diligence task list.

Do not put internal process labels in final prose:

- Bad: `Confirm...`
- Bad: `Closing Confirmations`
- Bad: `Investment conditions`
- Bad: `Conditions to proceed`
- Bad: `Must be met before BSH funds`
- Bad: `What Still Needs Confirmation`
- Bad: `Evidence Required Before the Next Step-Up`
- Bad: `Diligence priorities`

Use investor-facing alternatives:

- Good: `Valuation sensitivity`
- Good: `Evidence quality`
- Good: `Source treatment`
- Good: `Model treatment`
- Good: `Downside case`
- Good: `Risk factors`
- Good: `Open evidence`
- Good: `Deal mechanics`

### Clinical, Fact-Based Writing

Every sentence must be grammatical, idiomatic, and suitable for a finished
investment memo. A sentence cannot merely be directionally correct.

Avoid:

- prompt fragments;
- slogans;
- brainstorming language;
- passive speculation;
- awkward idioms;
- hedged filler;
- section-process narration;
- cute metaphors;
- dense fact piles that lose the investment point.

Prefer:

- direct claims;
- clean source qualification;
- quantified facts;
- clear investment judgment;
- explicit model treatment;
- concise risk language;
- natural executive prose.

## Canonical Opening Pattern

Use this as the positive model for the ZaiNar-style opener. Do not copy it
blindly into every memo, but preserve the grammar and institutional posture.

```text
BSH invests in foundational companies building Physical AI infrastructure:
systems that make the physical world safer, healthier, and more productive.
ZaiNar fits that mandate because precise network-side positioning is becoming
core infrastructure for defense PNT, industrial safety, healthcare logistics,
and autonomy.
```

Then move into company-specific facts:

```text
After nine years in stealth, ZaiNar emerged in February 2026 with a large
patent estate, disclosed strategic backing, and company-reported commercial
traction across defense, industrial, and carrier channels. The SPV gives BSH
access to the current financing through a SAFE with a 15% discount and a
$3.0B post-money cap.
```

The exact facts must always come from the current source packet. The tone and
structure should remain stable.

## Prompt Surfaces To Review

The review must not stop at one prompt wrapper. The memo language is affected by
several layers.

### Primary Prompt Files

- `server/claude_runner.py`
  - `HUMAN_EXEC_MEMO_VOICE_CONTRACT`
  - `_build_investment_memo_prompt`
  - `run_memo_fast_analysis_pass`
  - `run_memo_fast_english_package`
  - `run_memo_fast_bilingual_package`
  - `_build_resume_memo_package_prompt`
  - `_build_internal_diligence_memo_prompt`
  - Serena prompt helpers:
    - `run_serena_infographic_source_brief`
    - `run_serena_chart_spec_builder`
    - `run_serena_narrative_hooks`
    - `run_serena_strategic_risk_mapper`
    - `run_serena_thesis_spine_builder`
    - `run_serena_private_benchmark_dashboard`
    - `run_serena_memo_grader`
    - `run_serena_research_task`

- `server/skills/bsh_investment_memo_latestage.md`
  - global memo-writing contract;
  - section-by-section instructions;
  - examples and rewrite tables;
  - headings;
  - quality checklist;
  - translation guidance;
  - finalization checklist.

- `server/serena_analysis.py`
  - deterministic fallbacks;
  - UI labels and task descriptions;
  - memo packet construction;
  - selected guidance labels;
  - field names or visible text that can leak into generated prose.

### Quality Gates And Rewrite Layers

- `server/memo_quality_lint.py`
  - banned phrase patterns;
  - P0/P1 classification;
  - section/table scanning;
  - false-positive exceptions.

- `server/memo_analysis.py`
  - deterministic text cleanup;
  - package generation;
  - memo metadata and report state handling.

- Tests under `tests/`
  - prompt-construction tests;
  - packet tests;
  - linter tests;
  - regression tests for banned phrases and positive prompt rules.

### Adjacent Documentation

Review these for prior intent and to avoid reintroducing older language:

- `docs/investment-memo-style-upgrade-plan.md`
- `docs/zainar-memo-quality-remediation-plan.md`
- `docs/zainar-memo-quality-implementation-context.md`
- `docs/memo-generation-latency-plan.md`
- `docs/memo-pipeline.md`

## Required Audit Method

Use multiple paths. No single `rg` scan is enough.

Maintain a review ledger while doing the work. Do not reconstruct it from
memory at the end. The ledger should include every prompt-bearing surface found
by the inventory paths below.

For each surface, `Reviewed Scope` must be specific. `searched matching lines`
is not enough. Use entries such as `full function`, `full constant`, `full
markdown section`, `full file`, or `all deterministic fallbacks in file`.

### Prompt Surface Ledger

Update this table as surfaces are discovered, read, changed, and verified. Add
rows rather than collapsing multiple unrelated prompt surfaces into one entry.

| ID | Surface | Category | How Found | Reviewed Scope | Status | Prompt Risk | Planned Action | Verification | Notes |
|---|---|---|---|---|---|---|---|---|---|
| P01 | `server/claude_runner.py::HUMAN_EXEC_MEMO_VOICE_CONTRACT` | primary prompt | seed list / function inventory / bad-language scan | full constant | `VERIFIED` | voice rules could teach sponsor voice, third-person recommendations, or internal labels | rewritten to use `BSH` for mandate statements, `we recommend` for action, polished positive examples, and category-level rejected-language rules | re-read constant; `tests/test_memo_prep.py`; scoped high-risk scan clean | Removed exact copyable bad examples from positive guidance. |
| P02 | `server/claude_runner.py::_build_investment_memo_prompt` | primary prompt | seed list / function inventory | full function and assembled helper text | `VERIFIED` | main memo wrapper can override or contradict the voice contract | aligned final-output prohibitions, source treatment, recommendation posture, renderer contract, and memo-package requirements | re-read function; `tests/test_memo_prep.py`; scoped high-risk scan clean | Kept internal tool names where they describe workflow, not final prose. |
| P03 | `server/claude_runner.py::run_memo_fast_analysis_pass` | analysis prompt | seed list / function inventory | full function | `VERIFIED` | analysis prompt may produce packet language later copied into final prose | boxed analysis as source material and shifted pass/revisit wording toward downside sensitivity and evidence treatment | re-read function; `tests/test_memo_analysis.py`; phrase scan classification | Internal artifact names remain acceptable in analysis outputs. |
| P04 | `server/claude_runner.py::run_memo_fast_english_package` | package prompt | seed list / function inventory | full function and schema descriptions | `VERIFIED` | package prompt may normalize draft memo phrasing before final generation | marked package output as source-grounded final content, replaced conditional/gate vocabulary, and aligned schema descriptions | re-read function; `tests/test_memo_prep.py`; focused suite | Positive examples now use `BSH invests...` and `We recommend participating...`. |
| P05 | `server/claude_runner.py::run_memo_fast_bilingual_package` | package prompt | seed list / function inventory | full function and translation guidance | `VERIFIED` | bilingual guidance may preserve awkward English or literal translation artifacts | aligned English and Chinese guidance with final memo voice and source-treatment vocabulary | re-read function; focused suite; phrase scan classification | Translation parity still preserves facts without preserving bad English phrasing. |
| P06 | `server/claude_runner.py::_build_resume_memo_package_prompt` | recovery prompt | seed list / function inventory / call-chain review | full function | `VERIFIED` | stale-run recovery can reintroduce older packet language | required current voice contract and source-material boundaries on resume | re-read function; `tests/test_memo_analysis.py`; phrase scan classification | No full resume run was executed. |
| P07 | `server/claude_runner.py::_build_internal_diligence_memo_prompt` | internal prompt | seed list / function inventory | full function | `VERIFIED` | internal diligence labels can leak into final memo if not boxed | kept it explicitly internal and instructed economic/risk translation for anything that reaches final prose | re-read function; phrase scan classification | Internal memo can still use internal concepts inside its own boundary. |
| P08 | `server/claude_runner.py::run_serena_infographic_source_brief` | Serena prompt | seed list / function inventory | full function | `VERIFIED` | infographic briefing language may become copyable memo prose | kept labels source-only and separated design metadata from final prose | re-read function; `tests/test_serena_analysis.py`; scoped high-risk scan clean | Reviewer/design prompts remain internal packet fields. |
| P09 | `server/claude_runner.py::run_serena_chart_spec_builder` | Serena prompt | seed list / function inventory | full function | `VERIFIED` | chart captions or labels may carry internal framework terms into memo | separated chart metadata from final memo prose and emphasized insight/source treatment | re-read function; `tests/test_serena_analysis.py`; scoped high-risk scan clean | Chart field names remain internal. |
| P10 | `server/claude_runner.py::run_serena_narrative_hooks` | Serena prompt | seed list / bad-language scan | full function | `VERIFIED` | "narrative hooks" can encourage slogans or memo-moment language | boxed hooks as source-backed planning and replaced `memo moments` style language with factual thesis passages | re-read function; `tests/test_serena_analysis.py`; scoped high-risk scan clean | Tool name remains `narrative_hooks` for compatibility. |
| P11 | `server/claude_runner.py::run_serena_strategic_risk_mapper` | Serena prompt | seed list / function inventory | full function | `VERIFIED` | risk mapper may emit confirmation-gate or diligence-checklist language | translated open items into risk, source quality, model treatment, and valuation sensitivity | re-read function; `tests/test_serena_analysis.py`; scoped high-risk scan clean | `confirmation_evidence` remains an internal schema key. |
| P12 | `server/claude_runner.py::run_serena_thesis_spine_builder` | Serena prompt | seed list / bad-language scan | full function | `VERIFIED` | `thesis_spine` can produce framework/process prose | required direct investment judgments and source-grounded claims; sensitivities are not questions or conditions | re-read function; `tests/test_serena_analysis.py`; scoped high-risk scan clean | Tool name remains `thesis_spine` for compatibility. |
| P13 | `server/claude_runner.py::run_serena_private_benchmark_dashboard` | Serena prompt | seed list / function inventory | full function | `VERIFIED` | benchmark text may produce unsupported valuation or peer claims | required source qualification, model treatment, and valuation-support language instead of proof-gate wording | re-read function; `tests/test_serena_analysis.py`; scoped high-risk scan clean | Benchmark labels are internal analysis labels. |
| P14 | `server/claude_runner.py::run_serena_memo_grader` | Serena prompt / quality gate | seed list / function inventory | full function | `VERIFIED` | grader criteria may miss process-language failures or reward weak phrasing | updated rubric to penalize draft/internal memo language and evaluate evidence gaps/model treatment | re-read function; `tests/test_serena_analysis.py`; scoped high-risk scan clean | Aligns with linter. |
| P15 | `server/claude_runner.py::run_serena_research_task` | Serena prompt | seed list / function inventory | full function | `VERIFIED` | generic research task may generate source packets copied into memo | marked outputs as source material and forbade final-prose labels in packet handoff | re-read function; `tests/test_serena_analysis.py`; phrase scan classification | Generic research prompt wording remains internal. |
| P16 | `server/skills/bsh_investment_memo_latestage.md` | memo skill | seed list / file inventory / positive-guidance scan | full file | `VERIFIED` | global skill can dominate memo voice, headings, examples, and final checks | rewrote voice contract, examples, heading rules, evidence language, QA checklist, and translation guidance | re-read full file; `tests/test_memo_prep.py`; scoped high-risk scan clean | Exact bad headings are now described as categories, not copyable examples. |
| P17 | `server/serena_analysis.py` deterministic fallbacks | deterministic text | seed list / file inventory / bad-language scan | all memo-related fallback strings | `VERIFIED` | fallback text can become visible memo source material | rewrote copyable recommendation, risk, and grader fallback text | re-read fallback blocks; `tests/test_serena_analysis.py`; scoped high-risk scan clean | `risk_sensitivity` replaces `stop_or_revisit` in packet text. |
| P18 | `server/serena_analysis.py` packet builders | packet construction | seed list / call-chain review | all memo packet construction functions | `VERIFIED` | packet handoff can present internal notes as final prose | strengthened source-material boundary and kept internal labels out of final prose guidance | re-read packet builders; `tests/test_serena_analysis.py`; phrase scan classification | Internal schema keys remain for compatibility. |
| P19 | `server/serena_analysis.py` UI labels/task descriptions | visible labels | seed list / file inventory | all memo-related labels and task descriptions | `VERIFIED` | visible strings can leak into prompt packets or user-facing artifacts | classified UI/tool labels as internal; changed memo-packet labels that were copyable | re-read label blocks; `tests/test_serena_analysis.py`; phrase scan classification | `Thesis Spine` and `Narrative Hook Planner` remain UI tool names. |
| P20 | `server/memo_quality_lint.py` | quality gate | seed list / file inventory | full memo lint rules | `VERIFIED` | linter may miss known bad phrases or allow section/table leaks | added sponsor-voice/process-language patterns and shifted disclosure treatment away from diligence-threshold wording | re-read rules; `tests/test_memo_quality_lint.py`; expanded focused suite | Remaining bad phrases are linter patterns by design. |
| P21 | `server/memo_analysis.py` | orchestration / cleanup | seed list / file inventory / call-chain review | memo package cleanup, metadata, report-state, fast/resume paths | `VERIFIED` | cleanup and package construction may normalize bad language or hide failed quality gates | rewrote deterministic cleanup replacements, fallback labels, and fast-pass wording | re-read relevant functions; `tests/test_memo_analysis.py`; phrase scan classification | Remaining bad phrases are cleanup regex inputs. |
| P22 | `server/memo_docx_renderer.py` | renderer | dirty-file list / file inventory | valuation content terms, generic content patterns, validation messages | `VERIFIED` | renderer headings/messages can surface internal labels in final DOCX | changed valuation validation from diligence-threshold language to valuation-sensitivity language | re-read validation block; `tests/test_memo_docx_renderer.py`; targeted scan clean | Generic rejection of `More diligence is needed` remains intentional. |
| P23 | `tests/test_memo_quality_lint.py` | tests | seed list / test inventory | full file | `VERIFIED` | tests may encode old acceptable language or miss regressions | added bad sponsor voice fixtures and updated disclosure treatment examples | focused suite passed | Bad phrases in this file are intentional fixtures/assertions. |
| P24 | `tests/test_memo_prep.py` | tests | seed list / test inventory | full file | `VERIFIED` | prep tests may validate packet labels that leak into prompts | updated prompt expectations for positive guidance and exact-bad-phrase absence | focused suite passed | Now asserts `We back...` and `we want exposure` are absent. |
| P25 | `tests/test_memo_analysis.py` | tests | seed list / test inventory | full file | `VERIFIED` | analysis tests may normalize stale package language | updated cleanup fixtures and assertions for BSH institutional voice and mandate language | focused suite passed | Bad input strings are intentional cleanup fixtures. |
| P26 | `tests/test_serena_analysis.py` | tests | verification checklist / test inventory | full file | `VERIFIED` | Serena tests may miss packet-label regressions | updated packet-label and support-threshold assertions | focused suite passed | Internal tool-name assertions remain acceptable. |
| P27 | `tests/test_memo_docx_renderer.py` | tests | file inventory / broad scan | full file | `VERIFIED` | renderer fixtures can normalize stale final prose | rewrote conditional/diligence-gate fixture language to recommendation and valuation-sensitivity language | `tests/test_memo_docx_renderer.py`; targeted scan clean | Added to expanded focused suite. |
| P28 | `server/memo_prep.py` | prep/orchestration | file inventory | targeted scan of memo warning/manifest strings | `VERIFIED` | prep warning text may enter memo context | classified scope-warning text as prep metadata; no final-output prompt edits required | targeted scan; focused prep tests | Remaining `Proceed with the memo anyway` is an internal run instruction. |
| P29 | `server/memo_chinese_parity.py` | quality gate | file inventory | targeted scan of parity findings | `VERIFIED` | parity messages can teach literal prompt-scaffold wording | classified as linter/finding text that rejects prompt scaffolding, not final memo prose | targeted scan; renderer tests | `literal_prompt_scaffold` is an intentional finding code. |
| P30 | `docs/investment-memo-style-upgrade-plan.md` | adjacent docs | seed list / docs inventory | historical memo-style sections by scan | `DEFERRED` | prior style guidance may be copied back into prompts | classify as historical context; do not edit during prompt-code pass | broad phrase scan classification | Not an active prompt source. |
| P31 | `docs/zainar-memo-quality-remediation-plan.md` | adjacent docs | seed list / docs inventory | historical remediation sections by scan | `DEFERRED` | old remediation notes preserve failure phrasing | classify as historical context and failure examples | broad phrase scan classification | Not an active prompt source. |
| P32 | `docs/zainar-memo-quality-implementation-context.md` | adjacent docs | seed list / docs inventory | historical implementation sections by scan | `DEFERRED` | implementation context may contain old prompt instructions | classify live vs historical through scan; no active behavior edit | broad phrase scan classification | Not an active prompt source. |
| P33 | `docs/memo-generation-latency-plan.md` | adjacent docs | seed list / docs inventory | latency/resume sections by scan | `DEFERRED` | latency plan may describe resume/stale-run behavior | classify as context; no direct prompt behavior | broad phrase scan classification | Not an active prompt source. |
| P34 | `docs/memo-pipeline.md` | adjacent docs | seed list / docs inventory | memo pipeline sections by scan | `DEFERRED` | pipeline docs can reveal hidden prompt surfaces | used for call-chain orientation only | broad phrase scan classification | Not an active prompt source. |
| P35 | `docs/serena-agent-*.md` and `docs/phase-8-outstanding-work-plan.md` | adjacent docs | file inventory / broad scan | scan classification only | `DEFERRED` | docs contain `thesis spine` and `narrative hooks` terms | classify as historical/product documentation | broad phrase scan classification | Not active memo-generation prompts. |
| P36 | `server/skills/bsh_company_console*.md`, `server/skills/bsh_hormuz*.md`, `server/hormuz_*`, `server/weekly_stocks.py`, `server/stock_research*`, `server/companies_ai*`, `server/text_analysis.py` | non-memo prompts | file/function inventory | prompt-looking file classification | `DEFERRED` | non-memo prompt surfaces do not feed late-stage investment memo generation | exclude from this memo-prompt pass | file/function inventory classification | Separate workflows. |
| P37 | Latest ZaiNar generated memo text | artifact | artifact review | reported failure snippets in this handoff, not full artifact | `DEFERRED` | direct evidence of generated failures | mapped reported phrases to likely upstream prompt/fallback/linter gaps | artifact trace ledger | Fresh artifact review waits for the next approved full run. |
| P38 | `logs/memo_package.json` | artifact | artifact review | no fresh run artifact inspected | `DEFERRED` | package may contain copyable bad language | no full run during prompt-language phase | no-full-run gate | Path is run-specific. |
| P39 | `logs/memo_quality_lint.md` | artifact | artifact review | no fresh run artifact inspected | `DEFERRED` | lint report may show missed/hidden failures | no full run during prompt-language phase | no-full-run gate | Path is run-specific. |
| P40 | `logs/validation.txt` | artifact | artifact review | no fresh run artifact inspected | `DEFERRED` | validation may reveal hidden failed quality gate | no full run during prompt-language phase | no-full-run gate | Path is run-specific. |
| P41 | `analysis/memo_packet.md` or equivalent packet files | artifact | artifact review | no fresh run artifact inspected | `DEFERRED` | packet may contain upstream language copied into final memo | no full run during prompt-language phase | no-full-run gate | Path is run-specific. |

### File Inventory Ledger

After running Path 1, record every prompt-looking file. This catches files that
are easy to miss because they are outside the seed list above.

| File | Included In Surface ID | Classification | Reason |
|---|---|---|---|
| `server/claude_runner.py` | P01-P15 | `review` | Primary prompt constants, memo prompt builder, fast package prompts, resume prompt, internal memo prompt, and Serena task wrappers. |
| `server/skills/bsh_investment_memo_latestage.md` | P16 | `review` | Global late-stage memo skill controls final memo voice, examples, headings, QA, and translation guidance. |
| `server/serena_analysis.py` | P17-P19 | `review` | Deterministic fallbacks, packet builders, UI labels, and Memo Studio handoff text can feed the memo packet. |
| `server/memo_quality_lint.py` | P20 | `review` | Final DOCX lint gate and banned-phrase source of truth. |
| `server/memo_analysis.py` | P21 | `review` | Memo package orchestration, cleanup rewrites, fast path, quality failure handling, and resume recovery. |
| `server/memo_docx_renderer.py` | P22 | `review` | Renderer validation and visible failure messages can shape final DOCX quality gates. |
| `tests/test_memo_quality_lint.py` | P23 | `test` | Linter fixtures and assertions for rejected language. |
| `tests/test_memo_prep.py` | P24 | `test` | Prompt construction assertions for the main memo wrapper and fast package prompts. |
| `tests/test_memo_analysis.py` | P25 | `test` | Cleanup, package, quality-gate, and memo-analysis behavior assertions. |
| `tests/test_serena_analysis.py` | P26 | `test` | Serena packet, fallback, and tool-label assertions. |
| `tests/test_memo_docx_renderer.py` | P27 | `test` | Renderer package fixtures and DOCX lint integration. |
| `server/memo_prep.py` | P28 | `review` | Prep metadata and scope-warning text can enter the run context; no final-output prompt edits required. |
| `server/memo_chinese_parity.py` | P29 | `review` | Chinese parity finding text rejects prompt scaffolding; not final memo prose. |
| `docs/investment-memo-style-upgrade-plan.md` | P30 | `historical-doc` | Prior memo-style intent and examples; not an active prompt source in this pass. |
| `docs/zainar-memo-quality-remediation-plan.md` | P31 | `historical-doc` | Historical remediation notes and failure examples; not active behavior. |
| `docs/zainar-memo-quality-implementation-context.md` | P32 | `historical-doc` | Historical implementation context; useful for traceability, not active prompt text. |
| `docs/memo-generation-latency-plan.md` | P33 | `historical-doc` | Pipeline/latency context only. |
| `docs/memo-pipeline.md` | P34 | `historical-doc` | Call-chain orientation only. |
| `docs/serena-agent-analysis-tools.md`, `docs/serena-agent-handoff.md`, `docs/serena-agent-completion-handoff.md`, `docs/serena-risk-prioritization-context-transfer.md`, `docs/phase-8-outstanding-work-plan.md`, `docs/memo-tools-next-implementation-plan.md` | P35 | `historical-doc` | Product/implementation history with internal tool names such as `thesis spine` and `narrative hooks`; not active final-memo prompts. |
| `server/skills/bsh_company_console.md`, `server/skills/bsh_company_console_public.md`, `server/skills/bsh_hormuz_console.md`, `server/skills/bsh_hormuz_appendix.md`, `server/hormuz_prep.py`, `server/hormuz_analysis.py`, `server/weekly_stocks.py`, `server/stock_research.py`, `server/stock_research_tracker_designs.py`, `server/companies_ai.py`, `server/companies_ai_public.py`, `server/text_analysis.py`, `server/internal_memo_renderer.py` | P36 | `exclude` | Prompt-looking files from console, Hormuz, public equity, stock research, company AI, or internal-memo workflows; they do not feed the late-stage investment memo run. |
| `server/__pycache__/**`, `tests/__pycache__/**` | none | `exclude` | Generated bytecode caches from prior test runs. |
| `logs/memo_package.json`, `logs/memo_quality_lint.md`, `logs/validation.txt`, `analysis/memo_packet.md` or run-specific equivalents | P38-P41 | `blocked` | No fresh ZaiNar run was allowed or inspected during this prompt-language pass. |

Use these classifications:

- `review`: prompt-bearing or can influence memo prose;
- `test`: validates prompt, packet, lint, or memo output behavior;
- `artifact`: generated run evidence to inspect;
- `historical-doc`: useful context but not an active behavior source;
- `exclude`: unrelated to memo generation, with reason;
- `blocked`: should be reviewed but artifact/file is missing.

### Function And Constant Ledger

After running Path 2, record every memo-related function, constant, prompt
builder, wrapper, schema, fallback, or visible label source.

| Symbol | File | Included In Surface ID | Read Scope | Status | Notes |
|---|---|---|---|---|---|
| `HUMAN_EXEC_MEMO_VOICE_CONTRACT` | `server/claude_runner.py` | P01 | full constant | `VERIFIED` | Rewritten as the central positive/negative voice contract. |
| `_build_investment_memo_prompt` | `server/claude_runner.py` | P02 | full function | `VERIFIED` | Main late-stage memo prompt wrapper and source boundary. |
| `run_memo_fast_analysis_pass` | `server/claude_runner.py` | P03 | full function | `VERIFIED` | Analysis packet generation prompt. |
| `run_memo_fast_english_package` | `server/claude_runner.py` | P04 | full function and schema text | `VERIFIED` | English memo package prompt and JSON schema guidance. |
| `run_memo_fast_bilingual_package` | `server/claude_runner.py` | P05 | full function and schema text | `VERIFIED` | Bilingual package prompt and Chinese memo treatment. |
| `_build_resume_memo_package_prompt`, `run_resume_memo_package` | `server/claude_runner.py` | P06 | full function pair | `VERIFIED` | Resume/stale-run prompt path. |
| `_build_internal_diligence_memo_prompt`, `run_internal_diligence_memo` | `server/claude_runner.py` | P07 | full prompt builder and runner boundary | `VERIFIED` | Internal-only diligence memo path. |
| `run_serena_infographic_source_brief` | `server/claude_runner.py` | P08 | full function | `VERIFIED` | Serena source brief prompt. |
| `run_serena_chart_spec_builder` | `server/claude_runner.py` | P09 | full function | `VERIFIED` | Serena chart/infographic planning prompt. |
| `run_serena_narrative_hooks` | `server/claude_runner.py` | P10 | full function | `VERIFIED` | Source-backed narrative planning prompt; tool name retained. |
| `run_serena_strategic_risk_mapper` | `server/claude_runner.py` | P11 | full function | `VERIFIED` | Strategic risk prompt and evidence-treatment guidance. |
| `run_serena_thesis_spine_builder` | `server/claude_runner.py` | P12 | full function | `VERIFIED` | Thesis-spine prompt; tool name retained as internal label. |
| `run_serena_private_benchmark_dashboard` | `server/claude_runner.py` | P13 | full function | `VERIFIED` | Benchmark dashboard prompt and valuation-support guidance. |
| `run_serena_memo_grader` | `server/claude_runner.py` | P14 | full function | `VERIFIED` | Memo grading prompt and rubric. |
| `run_serena_research_task` | `server/claude_runner.py` | P15 | full function | `VERIFIED` | Selected research task prompt; source-material boundary. |
| Global memo contract, section instructions, examples, QA, translation guidance | `server/skills/bsh_investment_memo_latestage.md` | P16 | full file | `VERIFIED` | Skill text updated across voice, headings, examples, and finalization checklist. |
| `_run_*_job` memo tool runners | `server/serena_analysis.py` | P17-P19 | memo-related fallback/error/summary strings | `VERIFIED` | Rewrote copyable deterministic fallbacks and grader labels. |
| `_build_memo_packet_markdown`, `_refresh_memo_packet`, packet coercers | `server/serena_analysis.py` | P18 | packet construction and source-material sections | `VERIFIED` | Internal schema keys remain; final packet labels changed where copyable. |
| `MEMO_TOOL_DEFINITIONS`, UI labels/task descriptions | `server/serena_analysis.py` | P19 | memo tool label blocks | `VERIFIED` | UI labels classified as internal compatibility labels. |
| `_SELL_SIDE_BANNED_PATTERNS`, `_MODEL_TREATMENT_TERMS`, `_lint_blocks`, `_unresolved_disclosure_gap` | `server/memo_quality_lint.py` | P20 | memo lint rules and disclosure-gap handling | `VERIFIED` | Added sponsor voice/process bans and revised treatment vocabulary. |
| `_MEMO_PACKAGE_TEXT_REWRITES`, `_rewrite_memo_package_voice_text`, `_clean_memo_package_voice` | `server/memo_analysis.py` | P21 | cleanup regexes and rewrite logic | `VERIFIED` | Cleanup maps old voice to BSH institutional language. |
| Fast/resume package paths and quality failure handling | `server/memo_analysis.py` | P21 | relevant orchestration blocks | `VERIFIED` | Ensures quality failures remain surfaced; no full run executed. |
| `VALUATION_CONTENT_TERMS`, `_validate_section_content_floor` | `server/memo_docx_renderer.py` | P22 | validation constants/messages | `VERIFIED` | Diligence-threshold terminology replaced with valuation-sensitivity terminology. |
| Prompt/lint/renderer tests | `tests/test_memo_quality_lint.py`, `tests/test_memo_prep.py`, `tests/test_memo_analysis.py`, `tests/test_serena_analysis.py`, `tests/test_memo_docx_renderer.py` | P23-P27 | full files or changed fixture/assertion blocks | `VERIFIED` | Expanded focused suite now covers 136 tests. |
| `_validate_analysis_session_for_memo`, `bootstrap_memo_run`, manifest helpers | `server/memo_prep.py` | P28 | targeted prompt-like metadata strings | `VERIFIED` | Internal prep instructions classified; no prompt edits required. |
| Chinese parity finding strings | `server/memo_chinese_parity.py` | P29 | targeted parity finding blocks | `VERIFIED` | Finding text rejects literal prompt scaffolding. |

### Bad-Language Hit Ledger

Every hit from Path 3 must be classified. Do not delete the row just because a
patch removes the phrase; mark it as changed and verified.

| Phrase Or Pattern | Location | Classification | Upstream Cause | Required Change | Status | Verification |
|---|---|---|---|---|---|---|
| `We invest behind` | P01, P16 positive examples; P20/P21 guardrails; P23/P25 test fixtures | final-output risk removed from prompts; fixture/pattern retained | sponsor voice prompt and cleanup gap | replace with `BSH invests in...` for mandate and cleanup rewrite; add linter coverage | `VERIFIED` | scoped active scan clean; focused suite passed |
| `We back` | P01, P16 positive examples; P20/P21 guardrails; P23/P25 test fixtures | final-output risk removed from prompts; fixture/pattern retained | casual sponsor voice copied from examples | replace with `BSH invests in...` or `We recommend...`; add linter and cleanup rewrite | `VERIFIED` | scoped active scan clean; focused suite passed |
| `want exposure` / `why we want exposure` | P01, P16, P20/P21, P23-P25 | final-output risk removed from prompts; fixture/pattern retained | self-referential sponsor rationale | replace with `why the opportunity fits BSH's mandate` and direct recommendation language | `VERIFIED` | scoped active scan clean; focused suite passed |
| `The recommendation is` | P01/P16 negative examples, P20/P23 fixtures | final-output risk removed from prompts; fixture/pattern retained | third-person recommendation framing | require `We recommend...`; keep linter/test gate | `VERIFIED` | scoped active scan clean; focused suite passed |
| `this memo` / `our memo` / `the memo frames` | P01/P16 rules, P20/P23 fixtures, broad historical docs | final-output risk removed from copyable examples; fixture/pattern retained | process narration and memo-as-object voice | state the judgment directly; linter blocks meta-process language | `VERIFIED` | scoped active scan clean; broad scan hits accepted as tests/docs/internal rules |
| `Closing Confirmations`, `Closing Confirmation Bars`, `What Still Needs Confirmation`, `Evidence Required Before...` | P01/P16 headings, P20/P21 patterns, P23 fixtures | final-output risk removed from prompts; fixture/pattern retained | diligence checklist headings leaked into final prose | translate to risk, source treatment, model treatment, deal mechanics, or valuation sensitivity | `VERIFIED` | scoped active scan clean; focused suite passed |
| `Investment conditions`, `conditions to proceed`, `must be met before BSH funds`, `proceed only after` | P01/P16 rules, P20/P23 fixtures | final-output risk removed from prompts; fixture/pattern retained | conditions-to-proceed framing | replace with valuation/allocation sensitivity or deal-mechanics risk | `VERIFIED` | scoped active scan clean; focused suite passed |
| `Confirm...`, `confirmation...`, `confirmed...` | P07/P11/P17/P18/P20/P21/P23/P28 and historical docs | mixed; accepted only when internal, linter pattern, cleanup pattern, fixture, or historical | internal evidence-planning labels can leak if not boxed | keep internal-only fields boxed; translate final prose into risk/model/source treatment; linter blocks final output | `VERIFIED` | broad scan classified; focused suite passed |
| `Diligence Thresholds`, `Next Diligence Actions`, `support threshold` | P01/P14/P16/P17/P20/P21/P23/P27 | final-output risk removed from prompts/fixtures; pattern retained | threshold/checklist vocabulary invited process language | use evidence gaps, model treatment, valuation sensitivity, and proof that strengthens/weakens valuation support | `VERIFIED` | scoped active scan clean; focused suite passed |
| `soft instrument`, `hard IP wall`, `moat narrows`, `memo moments` | P01/P10/P16 | final-output risk removed from copyable prompt examples | fuzzy finance metaphor/slogan drift | replaced with category-level bans and factual thesis-passage language | `VERIFIED` | scoped active scan clean |
| `should be able` / `would be able` / `could be able` | P01/P16/P20/P23 fixtures | final-output risk removed from prompts; fixture/pattern retained | speculative counterparty capability phrasing | state a sourced fact, describe model treatment, or remove | `VERIFIED` | scoped active scan clean; focused suite passed |
| `thesis spine`, `narrative hook(s)`, `confirmation_evidence`, `reviewer_prompts` | P10-P12/P17-P19/P26/P35 | internal-only label accepted | compatibility tool/schema labels and historical docs | keep as internal fields/UI labels; do not copy into final prose; source-material boundary added | `VERIFIED` | broad scan classified; active high-risk exact scan clean |

### Positive Example Ledger

Every positive example, rewrite table, opening pattern, conclusion pattern, or
style example must be strong enough to appear in a final memo.

| Example Location | Current Example Summary | Decision | Replacement Needed | Status | Verification |
|---|---|---|---|---|---|
| P01 `HUMAN_EXEC_MEMO_VOICE_CONTRACT` opening pattern | Previously taught casual sponsor voice such as `We back...` / `we want exposure...` | Rewrite | `BSH invests in physical-world infrastructure...` plus company-specific mandate fit | `VERIFIED` | re-read constant; `tests/test_memo_prep.py`; scoped scan clean |
| P01/P04 recommendation examples | Needed direct first-person recommendation without `The recommendation is...` | Keep and strengthen | `We recommend participating in the SPV because...` | `VERIFIED` | prompt-construction tests assert presence and bad-phrase absence |
| P01/P16 evidence-gap examples | Some examples leaned on `confirm`, `diligence`, or checklist gates | Rewrite | `Revenue is not disclosed; our base case uses...`, `model treatment`, `source quality`, `valuation sensitivity` | `VERIFIED` | focused suite and broad scan classification |
| P01/P16 rejected-language table | Exact bad phrases were too copyable as negative examples | Rewrite | category-level bans: detached recommendation framing, closing checklists, funding-gate phrases, fuzzy finance metaphors, passive capability speculation | `VERIFIED` | `tests/test_memo_prep.py` asserts exact bad examples are absent |
| P16 canonical opener and finalization checklist | Skill examples and QA headings included stale BSH-should / confirmation wording | Rewrite | polished institutional subject, direct recommendation, and `Open Evidence` / `Evidence That Would Change the Model` | `VERIFIED` | full skill re-read; scoped scan clean |
| P17 deterministic fallback recommendation | Fallback said exposure/threshold-style language | Rewrite | `We recommend participating in {name} when...`; weakness described as valuation support, not a stop/revisit threshold | `VERIFIED` | `tests/test_serena_analysis.py` |
| P27 renderer test package | Sample package normalized conditional/diligence-gate prose | Rewrite | `We recommend evaluating... investment case`, `Valuation Sensitivity`, deployment/margin sizing language | `VERIFIED` | `tests/test_memo_docx_renderer.py`; targeted fixture scan clean |

### Prompt Change Decision Ledger

Draft the actual changes before editing prompts. This prevents a patch from
becoming a series of disconnected phrase swaps.

| Decision ID | Problem | Decision | Surfaces Affected | Tests/Lint Needed | Status |
|---|---|---|---|---|---|
| D01 | Sponsor voice sounds casual and self-referential. | Use `BSH` for mandate statements and `we` only for direct recommendation, investment-case judgment, or conviction. | P01, P02, P16, P20, P23-P25 | positive prompt tests; linter phrase tests; cleanup tests | `VERIFIED` |
| D02 | Final memo uses internal process labels. | Allow internal diligence labels only in boxed source material; translate final prose into risk, source quality, model treatment, deal mechanics, or valuation sensitivity. | P02, P06, P07, P11, P16-P22, P23-P27 | linter phrase tests; packet boundary tests; renderer tests | `VERIFIED` |
| D03 | Third-person process narration weakens recommendation. | Require direct investment judgment and ban `this memo`, `the memo frames`, and `the recommendation is` in final prose. | P01, P02, P14, P16, P20, P23, P25 | linter tests; prompt-construction tests | `VERIFIED` |
| D04 | Serena helper outputs can be copied into final prose. | Mark Serena outputs as source material, not finished memo language, and rewrite labels that invite slogans or framework prose. | P08-P15, P17-P19, P24, P26 | packet tests; phrase scan | `VERIFIED` |
| D05 | Prompt examples may teach bad cadence even when bans exist. | Rewrite positive examples into grammatical, investor-facing prose and pair each ban with a replacement. | P01, P02, P16, P27 | prompt tests; renderer tests; re-read | `VERIFIED` |

### Re-Read And Verification Ledger

Every changed prompt-bearing block gets a separate re-read row.

| Surface ID | Changed Block | Re-Read By Scope | Contradictions Found | Remaining Hits Accepted | Tests/Scans Run | Status |
|---|---|---|---|---|---|---|
| P01 | `HUMAN_EXEC_MEMO_VOICE_CONTRACT` | full constant and adjacent prompt insertion sites | None after final pass | none in scoped active high-risk scan | `tests/test_memo_prep.py`; scoped scan | `VERIFIED` |
| P02-P06 | main memo, fast package, bilingual package, and resume prompt blocks | full prompt-builder functions | None after replacing conditional/checklist wording | internal run instructions and artifact paths only | focused suite; scoped scan | `VERIFIED` |
| P07 | internal diligence memo prompt | full prompt-builder function | None; boundary remains explicitly internal | `confirm`-style terms only inside internal memo/economic-treatment boundary | phrase scan classification | `VERIFIED` |
| P08-P15 | Serena Claude prompt wrappers | full functions for infographic, chart, narrative, risk, thesis, benchmark, grader, and research task | None after source-material and valuation-support wording pass | tool names such as `thesis_spine` and `narrative_hooks` are accepted internal labels | `tests/test_serena_analysis.py`; scoped scan | `VERIFIED` |
| P16 | `server/skills/bsh_investment_memo_latestage.md` | full file, including global contract, section instructions, examples, QA, and translation guidance | None after final skill patch | generic "memo" references in skill instructions; no scoped high-risk exact hits | `tests/test_memo_prep.py`; scoped scan | `VERIFIED` |
| P17-P19 | `server/serena_analysis.py` fallback/packet/UI blocks | memo-related fallback strings, packet construction, tool labels | None after `risk_sensitivity` and valuation-support rewrites | internal schema keys (`confirmation_evidence`) and UI tool names | `tests/test_serena_analysis.py`; broad scan classification | `VERIFIED` |
| P20 | `server/memo_quality_lint.py` rules | banned patterns, disclosure-gap treatment, scaffold handling | None | banned phrase regexes intentionally remain | `tests/test_memo_quality_lint.py`; broad scan classification | `VERIFIED` |
| P21 | `server/memo_analysis.py` cleanup/orchestration | cleanup rewrite patterns, fast pass, resume/quality handling | None | cleanup regex inputs intentionally quote old phrases | `tests/test_memo_analysis.py`; broad scan classification | `VERIFIED` |
| P22 | `server/memo_docx_renderer.py` validation terms | valuation content terms and validation message | None | generic rejection pattern for `More diligence is needed` remains a negative quality gate | `tests/test_memo_docx_renderer.py`; targeted scan | `VERIFIED` |
| P23-P27 | memo test files | changed fixtures/assertions and prompt/renderer fixtures | None | bad phrases remain only as linter/cleanup fixtures or negative assertions | expanded focused suite | `VERIFIED` |
| P28-P29 | `server/memo_prep.py`, `server/memo_chinese_parity.py` | targeted prompt-like strings and finding text | None | internal prep instruction and parity finding code text | targeted scan; focused tests | `VERIFIED` |
| P30-P36 | adjacent docs and excluded non-memo prompts | scan classification | None for active memo path | historical docs and non-memo prompts | file/function inventory; broad scan classification | `DEFERRED` |
| P37-P41 | ZaiNar artifacts/logs/packets | reported snippets only | Fresh artifact review intentionally not performed | all run artifacts blocked by no-full-run gate | no full run executed | `DEFERRED` |

### Artifact Trace Ledger

Use this to connect generated ZaiNar failures to upstream causes. At least one
bad phrase must be traced before the implementation pass is considered
complete.

| Generated Failure | Artifact Location | Likely Upstream Source | Evidence | Prompt/Lint/Test Fix | Status |
|---|---|---|---|---|---|
| `We invest behind technical infrastructure...` | reported ZaiNar failure in this handoff | P01/P16 positive voice examples and P21 cleanup gap | phrase matches old sponsor-voice examples and was not rewritten by cleanup | rewrote mandate voice examples to `BSH invests...`; added linter patterns and cleanup rewrites for `We invest behind`, `We back`, and `want exposure` | `VERIFIED` |
| `Closing Confirmations` | reported ZaiNar failure in this handoff | P01/P16 final-output headings and P20/P21 guardrail gap | heading appears as an internal diligence/checklist label | rewrote final-output prompt rules to use risk/source/model/deal-mechanics/valuation language; linter and cleanup patterns now block/rewrite confirmation headings | `VERIFIED` |
| `wisdom should be able share` | reported ZaiNar failure in this handoff | P01/P16 grammar and passive capability speculation gap | grammar failure combines weak prompt grammar with speculative counterparty ability phrasing | added positive grammar rules; banned passive sponsor/counterparty capability speculation; linter fixture catches `should be able` phrasing | `VERIFIED` |
| Fresh `logs/memo_package.json`, `logs/memo_quality_lint.md`, `logs/validation.txt`, `analysis/memo_packet.md` | not inspected | no-full-run gate | user asked to re-evaluate prompt language before running code/agent | defer full artifact regression until user approves a full run | `DEFERRED` |

### Path 1: File Inventory

List all likely prompt-bearing files:

```bash
rg --files \
  -g 'server/**' \
  -g 'docs/**' \
  -g 'tests/**' \
  | rg '(claude|memo|serena|skill|prompt|lint|analysis|prep|quality|test)'
```

Record the files that were reviewed and explain why any prompt-looking file was
excluded.

### Path 2: Function And Constant Inventory

Search for prompt builders, prompt constants, and LLM task wrappers:

```bash
rg -n "prompt|Prompt|PROMPT|system|System|user_prompt|HUMAN_EXEC|run_serena|run_memo|memo_package|skill" server tests
```

For every hit that influences memo generation, read the surrounding function,
not just the matching line.

### Path 3: Bad-Language Inventory

Search for current and likely variants of known failures:

```bash
rg -n -i \
  "we back|we invest behind|want exposure|the recommendation is|this memo|our memo|the memo|the analysis suggests|the framework|this section|confirm|confirmation|conditions?|diligence|gate|must be met|before bsh funds|proceed only|revisit|hold|pass|framed|as framed|support threshold|operator|narrative hook|thesis spine|memo moments|control layer underneath|only scaled platform|should be able|would be able|could be able" \
  server docs tests
```

Classify each hit as:

- final-output instruction that must change;
- internal workflow label that is safe only if clearly boxed away;
- test fixture that should be updated to the new target language;
- linter banned phrase that should remain;
- historical docs that should not drive current behavior.

### Path 4: Positive-Guidance Inventory

Search not only for bad phrases but for weak examples. Bad examples can be more
dangerous than missing bans because the model copies them.

```bash
rg -n -i \
  "good:|bad:|avoid|prefer|example|rewrite|opening|conclusion|recommend|investment view|executive summary|voice|tone|style" \
  server/claude_runner.py server/skills/bsh_investment_memo_latestage.md server/serena_analysis.py tests docs
```

Every positive example must be polished enough to appear in a finished memo.
If a positive example sounds like a placeholder, rewrite it.

### Path 5: Call-Chain Review

Trace the memo-generation path from API entry to final DOCX:

1. report creation and memo bootstrap;
2. memo analysis orchestration;
3. Claude prompt construction;
4. Serena analysis packets;
5. package generation;
6. DOCX rendering;
7. quality linting;
8. resume/stale-run recovery.

The purpose is to catch prompt text introduced outside the obvious main prompt.

### Path 6: Artifact Review

Review the latest failed and repaired ZaiNar artifacts:

- generated memo DOCX text;
- `logs/memo_package.json`;
- `logs/memo_quality_lint.md`;
- `logs/validation.txt`;
- `analysis/memo_packet.md` or equivalent packet files.

Map each bad generated phrase back to the upstream prompt or packet language
that likely caused it.

### Path 7: Post-Edit Re-Read

After edits, re-open the changed files and read the relevant prompt blocks from
top to bottom. Do not rely only on diff hunks.

Check for:

- contradictory instructions;
- old terms left in neighboring paragraphs;
- examples that violate the new rule;
- headings that still imply internal process;
- schema descriptions that invite bad language;
- deterministic fallbacks that use old wording;
- linter/test fixtures that normalize rejected phrasing.

## Remediation Rules

### Do Not Just Ban Phrases

Every bad phrase should produce three changes where applicable:

1. remove or rewrite the upstream prompt text that invites it;
2. add a clear positive alternative;
3. add or update a lint/test assertion if the failure is likely to recur.

Example:

- Bad symptom: `The recommendation is Proceed if confirmed...`
- Upstream fix: forbid third-person recommendation voice and remove
  `confirmed` / `conditions` framing from final-output instructions.
- Positive rule: `Write "We recommend participating..." and discuss valuation
  sensitivities separately.`
- Gate: linter fails `the recommendation is`, `if confirmed`, and visible
  `conditions to proceed` in final memo sections.

### Separate Internal Work From Final Output

It is acceptable for internal tools to ask diligence questions. It is not
acceptable for those labels to leak into finished investor prose.

Use explicit boundaries:

- `Internal evidence planning only. Do not copy this label into the memo.`
- `This packet is source material, not final prose.`
- `Translate open items into risk, source treatment, model treatment, or
  valuation sensitivity.`

### Replace Conditions With Investment Analysis

Finished memo language should not say BSH will invest only if some checklist is
met. The memo is advocating a transaction while identifying risks.

Replace:

- `conditions`;
- `confirmation gates`;
- `must be met`;
- `before BSH funds`;
- `closing confirmations`;
- `proceed only after`.

With:

- `valuation sensitivity`;
- `allocation sensitivity`;
- `deal-mechanics risk`;
- `source-quality risk`;
- `model treatment`;
- `downside case`;
- `evidence that would change sizing`.

### Rewrite Prompt Grammar Directly

Prompt grammar matters. The model learns the cadence of the instruction text.

Fix awkward prompt language even when it is not a banned phrase:

- remove run-on bullets;
- remove nested hedges;
- turn fragments into complete sentences;
- remove analyst shorthand;
- replace vague nouns with concrete subjects;
- keep examples natural and grammatical;
- avoid using internal labels as if they were prose.

### Keep Positive And Negative Guidance Paired

Every important ban should have a preferred replacement. Without a replacement,
the model will find another awkward construction.

Example:

| Ban | Replace With |
|---|---|
| `We back...` | `BSH invests in...` for mandate; `we recommend...` for action |
| `The recommendation is...` | `We recommend...` |
| `Confirm...` | `The model gives no revenue credit until...` |
| `conditions to proceed` | `valuation sensitivities` or `deal-mechanics risks` |
| `the memo frames` | state the judgment directly |
| `as framed` | remove or replace with the actual term being described |
| `diligence needed` | `evidence gap` or `source treatment` |
| `should be able to` | make the factual claim or remove the speculation |

## Implementation Order

1. Build the complete prompt inventory.
2. Populate the file inventory ledger and classify every prompt-looking file.
3. Populate the function and constant ledger from the function inventory scan.
4. Read `server/claude_runner.py` prompt blocks in full.
5. Read `server/skills/bsh_investment_memo_latestage.md` in full.
6. Read `server/serena_analysis.py` memo-related labels, fallbacks, and packet
   builders in full.
7. Read `server/memo_quality_lint.py` and the related tests.
8. Review prior docs for stale language that may be copied forward.
9. Classify bad-language hits and positive examples in their ledgers.
10. Trace at least one failed ZaiNar phrase to a likely upstream source.
11. Draft the prompt change decisions before editing.
12. Apply prompt remediations with `apply_patch`.
13. Update lint and tests.
14. Re-read every changed prompt block and update the re-read ledger.
15. Re-evaluate prompt language as prose before running code:
    - read the changed prompt text aloud enough to catch awkward grammar;
    - verify every positive example could appear in a final investor memo;
    - verify every internal label is boxed as source material or removed;
    - verify final-output instructions state the desired prose directly.
16. Run focused tests.
17. Run phrase scans again and classify every remaining hit.
18. Decide whether the no-full-run gate is satisfied.
19. Only after the user agrees, run the full memo code path or agent.
20. Summarize every changed file and why it changed.

## Verification Checklist

The work is not complete until all of the following are true.

### Coverage

- All prompt-bearing files were inventoried.
- Every memo-related prompt function in `server/claude_runner.py` was read.
- The full memo skill markdown was read, not just search hits.
- Serena packet and fallback text was reviewed.
- Linter and tests were reviewed.
- Prior memo-quality docs were checked for stale instructions.

### Language

- No positive example uses `We back`, `we invest behind`, or `we want exposure`.
- No final-output instruction asks for `Confirm`, `Closing Confirmations`,
  `Investment conditions`, or `conditions to proceed`.
- No final-output instruction uses third-person situational voice.
- Internal labels are clearly marked as non-final source material.
- Positive examples are polished and grammatical.
- Disclosure gaps are handled as model treatment, risk, source quality, or
  valuation sensitivity.

### Tests And Scans

Run the relevant focused tests:

```bash
PYTHONPATH=. pytest tests/test_memo_docx_renderer.py tests/test_memo_quality_lint.py tests/test_memo_prep.py tests/test_memo_analysis.py tests/test_serena_analysis.py -q
```

Run phrase scans after edits and inspect every remaining hit:

```bash
rg -n -i \
  "we back|we invest behind|want exposure|the recommendation is|this memo|our memo|the memo|confirm|confirmation|conditions?|must be met|before bsh funds|proceed only|as framed|support threshold|narrative hook|thesis spine|memo moments|should be able|would be able|could be able" \
  server docs tests
```

Remaining hits are acceptable only if they are:

- banned-phrase tests;
- historical documentation explicitly marked as old behavior;
- this audit document quoting bad language as examples;
- internal-only workflow labels that cannot reach final prose;
- linter patterns.

### Artifact Regression

After prompt remediation, the next ZaiNar run should be reviewed for:

- intro grammar and naturalness;
- BSH institutional voice;
- direct first-person recommendation;
- no third-person memo/process voice;
- no internal confirmations or conditions;
- no speculative/passive language;
- no hidden report on failed quality gate;
- complete telemetry for run timing and intra-task timing.

### Prompt Language Sign-Off

Complete this before any full code or agent run.

| Check | Status | Evidence |
|---|---|---|
| Institutional subject is stable: `BSH` for mandate, `we` only for direct recommendation or investment-case judgment. | `VERIFIED` | P01/P16 examples now use `BSH invests...`; tests assert old sponsor voice is absent. |
| Recommendation voice is direct and first person where appropriate. | `VERIFIED` | Prompt tests require `We recommend participating...` and linter blocks detached recommendation framing. |
| No final-output instruction asks for confirmations, conditions, gates, or diligence checklists. | `VERIFIED` | Scoped active scan is clean for exact high-risk phrases; final-output rules use risk/source/model/deal-mechanics/valuation language. |
| Internal Serena/research/packet labels are marked as source material or kept out of final prose. | `VERIFIED` | P08-P19 source-material boundaries re-read; remaining `thesis_spine`, `narrative_hooks`, `confirmation_evidence`, and `reviewer_prompts` hits are internal schema/UI labels. |
| Positive examples are grammatical, specific, and investor-facing. | `VERIFIED` | P01/P16/P27 examples rewritten; prompt and renderer tests pass. |
| Prompt text has been re-read as prose after editing, not only inspected through diffs. | `VERIFIED` | Re-read ledger documents full constants/functions/skill sections and changed deterministic/lint/test blocks. |
| Remaining scan hits are documented and acceptable. | `VERIFIED` | Remaining broad hits are audit examples, historical docs, linter patterns, cleanup regexes, intentional test fixtures, non-memo prompts, or internal compatibility labels. |
| Focused tests pass or failures are documented as unrelated to prompt language. | `VERIFIED` | Expanded focused suite passed: 138 passed, 2 existing FastAPI deprecation warnings. |

### Implementation Pass Record - 2026-06-26

Inventory check:
- Files classified: active prompt/code surfaces P01-P29; historical or adjacent docs P30-P35; non-memo prompt systems P36; artifacts P37-P41.
- Exclusions: non-memo console, Hormuz, public-company, stock-research, company-AI, and bytecode-cache files do not feed the late-stage investment memo run.
- Blocked artifacts: fresh ZaiNar `memo_package.json`, lint, validation, and packet artifacts were not inspected because the no-full-run gate stayed active.

Function check:
- Prompt functions/constants read in full: `HUMAN_EXEC_MEMO_VOICE_CONTRACT`, `_build_investment_memo_prompt`, fast analysis/package prompts, bilingual package prompt, resume prompt, internal diligence prompt, and all memo-related Serena Claude wrappers.
- Prompt surfaces changed: `server/claude_runner.py`, `server/skills/bsh_investment_memo_latestage.md`, `server/serena_analysis.py`, `server/memo_analysis.py`, `server/memo_quality_lint.py`, `server/memo_docx_renderer.py`, `tests/test_memo_prep.py`, `tests/test_memo_quality_lint.py`, `tests/test_memo_analysis.py`, `tests/test_serena_analysis.py`, and `tests/test_memo_docx_renderer.py`.

Language check:
- Bad-language hits removed from active prompt examples and final-output instructions: casual sponsor voice, detached recommendation framing, confirmation/checklist headings, conditions-to-proceed framing, fuzzy finance metaphors, passive capability speculation, and support-threshold phrasing.
- Remaining hits accepted: linter patterns, cleanup regex inputs, intentional negative test fixtures, audit-document examples, historical docs, non-memo prompts, and internal compatibility labels such as `thesis_spine`, `narrative_hooks`, `confirmation_evidence`, and `reviewer_prompts`.
- Positive examples rewritten: institutional BSH mandate opener, direct `We recommend participating...` recommendation examples, evidence-gap/model-treatment examples, skill QA examples, Serena deterministic fallback recommendation, and renderer sample package prose.

Artifact check:
- Generated failures traced: `We invest behind technical infrastructure...`, `Closing Confirmations`, and `wisdom should be able share`.
- Upstream source: prompt positive examples, final-output heading guidance, deterministic cleanup/lint gaps, and weak grammar/capability-speculation rules.
- Fix: rewritten voice contract and skill guidance, cleanup rewrites, linter coverage, fixture coverage, and source-material boundaries.

Verification:
- Tests: `PYTHONPATH=. pytest tests/test_memo_docx_renderer.py tests/test_memo_quality_lint.py tests/test_memo_prep.py tests/test_memo_analysis.py tests/test_serena_analysis.py -q` -> 138 passed, 2 existing FastAPI deprecation warnings.
- Phrase scans: scoped high-risk active prompt scan over `server/claude_runner.py`, `server/skills/bsh_investment_memo_latestage.md`, and `server/serena_analysis.py` found no copyable final-output instructions using the banned language; broad scan hits were classified by accepted-hit category.
- Whitespace: `git diff --check` passed.
- Re-read ledger status: P01-P29 verified; P30-P41 deferred with reasons.

Run gate:
- Full agent/code run allowed: no.
- Reason: prompt language and focused guardrails are verified, but fresh artifact regression is intentionally deferred until the user explicitly approves a full memo or agent run.

### Final Summary Template

Use this structure for the implementation-pass summary:

```text
Inventory check:
- Files classified:
- Exclusions:
- Blocked artifacts:

Function check:
- Prompt functions/constants read in full:
- Prompt surfaces changed:

Language check:
- Bad-language hits removed:
- Remaining hits accepted:
- Positive examples rewritten:

Artifact check:
- Generated failure traced:
- Upstream source:
- Fix:

Verification:
- Tests:
- Phrase scans:
- Re-read ledger status:

Run gate:
- Full agent/code run allowed: yes/no
- Reason:
```

## Expected Output Of The Remediation Pass

The implementation pass should produce:

1. a file-by-file change summary;
2. the completed prompt surface ledger;
3. the completed bad-language hit ledger;
4. the completed positive example ledger;
5. the completed prompt change decision ledger;
6. the completed re-read and verification ledger;
7. a list of remaining phrase-scan hits and why each is acceptable;
8. tests run and results;
9. a clear yes/no on whether the no-full-run gate has been satisfied;
10. any residual risks before the next full ZaiNar memo run.

## Evidence Of Complete Review

The final implementation summary should include a compact coverage statement
with four independent checks:

1. `Inventory check`: every file found by the file inventory was classified.
2. `Function check`: every memo-related prompt function or constant was read in
   full.
3. `Language check`: every bad-language scan hit was classified after edits.
4. `Artifact check`: at least one generated memo failure phrase was traced back
   to the upstream prompt, packet, fallback, or linter gap that allowed it.

The summary should also state what was intentionally not reviewed. For example,
non-memo Hormuz prompts or public-equity prompts can be excluded only if they do
not feed the investment memo run. The exclusion must be explicit so later work
does not mistake an unreviewed surface for a clean one.

The summary should be specific enough that a later context can tell whether the
audit really covered the prompt stack or only patched the latest visible phrase.
