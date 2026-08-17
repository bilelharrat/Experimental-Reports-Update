# Risk Tool Improvement Plan

Last updated: 2026-07-31

Plan for making the strategic risk tools (a) genuinely human-in-the-loop,
(b) richer in content, and (c) actually wired into the memo workflow.
Builds on the shipped slice in
`docs/serena-risk-prioritization-context-transfer.md`.

## Current state (verified against code)

- `strategic_risk_mapper` (`server/claude_runner.py:7465`) is the only LLM
  step. Schema (`SERENA_STRATEGIC_RISK_SCHEMA`, `claude_runner.py:6120`):
  `title`, `decision_question`, `why_it_matters`, `bull_case_answer`,
  `bear_case_answer`, `evidence_needed`, `best_sources`, `research_prompt`,
  `memo_section`, `status`. No severity, likelihood, mitigation, or posture.
- `priority_prompt_harness` ("Risk Prioritizer") is deterministic: initial
  rank = LLM output order, `selected: i < 3`, rationale is a hardcoded
  string (`server/serena_analysis.py:2408-2425`).
- The Strategic Risk Board (`frontend/src/components/memo/MemoRiskPriorityPanel.vue`)
  shows only `title`, `status`, `decision_question`, `why_it_matters`, and
  rank. Interactions: move up/down, "Research" checkbox, save.
- Gaps found:
  1. Bull/bear answers, `evidence_needed`, `best_sources`, `memo_section`,
     and `rationale` are stored but never rendered anywhere.
  2. No per-risk edit, dismiss, or accept. Deselecting only removes the
     risk from the research queue; it still flows into `memo_packet.md`
     (`serena_analysis.py:5394-5399`) and the final memo prompt.
  3. Human rank order is ignored by the packet — `_refresh_memo_packet`
     iterates risks in source order.
  4. The DOCX contract requires a `risk_register` with severity ×
     likelihood (`memo_docx_renderer.py:167-171`) and the deterministic
     `chart-risk-register` spec demands "risk severity, likelihood,
     disconfirming evidence, monitoring approach" — data the pipeline
     never produces. The memo LLM free-texts the register today.
  5. Memo editor risk cards (`memo_editor_store.py:355-440`) have a
     severity field + severity-colored UI that never fires because
     `thesis_spine.investment_risks` carries no severity.
  6. Deterministic-fallback risks (`generated_by: "deterministic_fallback"`,
     `serena_analysis.py:1261-1281`) are indistinguishable from
     Claude-researched risks in the UI.
  7. Completed research task results reach the packet but never update
     risk `status` or the thesis spine (open item 5 from the 2026-06-03
     handoff).
  8. The board is buried in the collapsed "Advanced tools" `<details>`
     (`ResearchView.vue:1634-1646`) and has no i18n.
  9. The mapper prompt already asks for risks that let an operator choose
     a posture ("lead risk, downside trigger, valuation sensitivity, or
     monitoring item") but no posture field or UI exists.

## Phase 1 — Make risks decidable (HIL core)

Goal: a human can see everything the mapper produced, correct it, and make
a real per-risk decision that downstream stages respect.

1. **Per-risk disposition.** Add `disposition` to each priority row in
   `risk_priorities`: one of `lead_risk | downside_trigger |
   valuation_sensitivity | monitoring | dismissed` (default `monitoring`,
   or seeded from a new mapper `suggested_posture` field in Phase 2).
   - `_normalize_priorities` validates/preserves it.
   - `dismissed` risks are excluded from `memo_packet.md`, the final memo
     prompt context, and the memo editor seed — the missing "reject"
     lever. They stay visible in the board (struck through / collapsed)
     and in the artifact for audit.
2. **Expand the board card.** Collapsible detail per risk showing
   `bull_case_answer`, `bear_case_answer`, `evidence_needed`,
   `best_sources`, `memo_section`, and the priority `rationale`.
   Disposition picker on the card header.
3. **Inline editing.** Editable `title`, `why_it_matters`, and `rationale`
   (same interaction pattern as the thesis-spine inline editors). Backend:
   extend `patch_artifact` with a per-risk merge path for
   `strategic_risks` (patch by `risk_id`, preserve unedited fields, stamp
   `edited_by_human: true`).
4. **Provenance badge.** Surface `generated_by` — a visible "template
   fallback" badge when risks came from `_strategic_risks`, plus the
   `claude_error` in a tooltip/expander, with a one-click "re-run mapper"
   affordance.
5. **i18n.** Move all panel strings into `frontend/src/i18n.js`
   (`memo.risk_board.*`), matching the other memo panels.

Tests: extend `tests/test_serena_analysis.py` (disposition normalization,
dismissed-risk exclusion from packet, per-risk patch merge) and frontend
vitest for the panel.

## Phase 2 — Better content

Goal: risks carry the structured fields the rest of the pipeline already
demands, and the prioritizer earns its name.

1. **Extend `SERENA_STRATEGIC_RISK_SCHEMA`** with:
   - `severity`: `high | medium | low` (downside magnitude if it hits)
   - `likelihood`: `high | medium | low`
   - `downside_impact`: one sentence, concrete (ties to the audit's
     "Downside Impact" framing in
     `docs/memo-prompt-comprehensive-audit-handoff.md` R06/P11)
   - `mitigation_or_monitoring`: what would reduce or flag the risk
   - `suggested_posture`: the enum from Phase 1 (LLM proposes, human
     disposes)
   Update the mapper prompt accordingly; `_coerce_strategic_risks`
   back-fills defaults; the deterministic fallback generator sets sane
   values.
2. **Real default prioritization.** `_run_tool_impl` ranks by
   severity × likelihood (with source-order tiebreak) instead of raw
   output order, and writes a per-risk rationale derived from those
   fields instead of the hardcoded string. Still deterministic — no new
   LLM call.
3. **Evidence linkage.** Show per-risk evidence-matrix signal on the card:
   count of contradicted/mixed matrix rows whose claims match the risk's
   `memo_section`/keywords, linking to `MemoEvidenceMatrixPanel`. (Keyword
   match first; anything smarter is out of scope.)

Migration note: existing sessions' `strategic_risks.yaml` lack the new
fields — coercion must default them without forcing a re-run.

## Phase 3 — Workflow integration

Goal: human decisions actually shape the memo, and the research loop
closes.

1. **Packet respects the human.** `_refresh_memo_packet` emits the
   Strategic Risks section in saved rank order, grouped by disposition
   (lead risk first, then downside triggers, valuation sensitivities,
   monitoring), excluding dismissed risks, and including
   severity/likelihood/downside_impact/mitigation per risk. Add a compact
   structured "Risk Register (data)" block so the final memo's
   `risk_register` table is grounded in reviewed fields instead of
   improvised.
2. **Close the research loop.** When a research task completes, flip the
   parent risk's `status` `unresearched → researched` (or `needs_review`
   if the result contradicts the thesis) and surface the task
   `result_summary` inside the risk card. This finishes item 5 of the
   2026-06-03 handoff. (Automatic thesis-spine rewrites stay out of
   scope; a "thesis may need update" flag on the readiness panel is
   enough.)
3. **Seed memo editor severity.** Pass strategic-risk severity through to
   the memo editor risk cards (match by title/section when seeding from
   `thesis_spine`), so `cardTone` severity styling finally works for
   LLM-derived cards.
4. **Readiness gate.** Add a readiness blocker: any `high` severity risk
   still `unresearched` and not dismissed/waived blocks approval (waivable
   with rationale, like existing gates).
5. **Un-bury the board.** Promote a compact risk summary strip (top 3
   risks by rank, disposition + status chips, "n unreviewed" count) onto
   the main memo tab above the advanced-tools disclosure, linking down to
   the full board. Extract the board into
   `memo/StrategicRiskBoard.vue` per the deferred split in
   `docs/memo-tools-next-implementation-plan.md:500-509`.

## Out of scope (explicitly deferred)

- The cross-surface Risk Register page (`docs/research-pages-visual-tools-plan.md`
  Page 8: heat map, waterfall, hypothesis links). Phases 1–3 produce the
  structured fields it needs, so it becomes buildable later.
- LLM-based re-prioritization or auto-rewriting of risks from task
  results.
- Memo editor projection consumption by the memo run (tracked separately
  in the v2 PRD plan M2 exit criteria).

## Sequencing and verification

Order: Phase 1 → 2 → 3; each phase ships independently on `main`.
Phase 1 items 1–2 are the highest-leverage slice (dismissal + full
content display) and can ship alone.

Per the standard gate:

```sh
uv run python -m pytest
npm --prefix frontend test
npm --prefix frontend run lint
uv run ruff check server scripts tests
```

Browser smoke: `http://127.0.0.1:8010/research/research/<slug>?tab=analysis`
— board renders detail expansion, disposition picker, dismissal excluded
from a regenerated packet. Remember the dev server on port 8010 has no
reload; restart uvicorn before UI-triggered runs.
