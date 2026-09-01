# Memo Studio Risk Loop Plan

> **SUPERSEDED (2026-09-01)** by the Memo Studio process flow on branch
> `memo-studio`: instead of seeding cards from a finished report, the
> pipeline detaches at the Phase 2 → Phase 3 seam — "Start Deep
> Investigate" runs the analysis passes + a standalone spine that seeds
> the cards, the user edits, and "Generate Report" composes the cards
> back into the spine as enforced pins. See
> `docs/memo-pipeline-structure.md` §1 "The Memo Studio seam". This
> document stays for the design history (the studio↔document
> disconnection analysis remains accurate for the pre-studio state).

Last updated: 2026-08-20

Plan for connecting the Memo Studio "Risks and Mitigations" section to
report generation in both directions: generated reports seed the studio,
human edits in the studio refine the report. Narrows the scope of
`docs/risk-tool-improvement-plan.md` Phase 3 to one concrete loop. The
Risk Workbench under Advanced tools is explicitly out of scope for now.

## Current state (verified against code, 2026-08-20)

The studio risk section is a finished editing shell wired into nothing:

- **Studio → document: no connection.** `server/claude_runner.py` never
  reads `server/memo_editor_store.py`. Card ranking, include/exclude, and
  edits only feed the in-app export projection
  (`memo_editor_store.py:1341`), a source-coverage preview.
- **Document → studio: no connection.** Generated reports never write
  back. The only inbound data is a one-time seed at first open
  (`get_state`, `memo_editor_store.py:972`): it tries the Serena analysis
  session's `thesis_spine.investment_risks`, else falls back to three
  generic placeholder cards (`_fallback_risk_cards`,
  `memo_editor_store.py:560`) that look real but are company-neutral
  boilerplate. Once the state YAML exists it is never re-seeded.
- **"Rerun" is a stub.** `request_section_rerun`
  (`memo_editor_store.py:1261`) records the request; its own status note
  says regeneration is not connected.
- **The report side is already structured.** Since the risk-register
  redesign (commit `e13cd2d`), `memo_package.json` carries each risk as a
  `heading` ("Risk N: <one-line summary>") plus a `key_value` table with
  rows Risk Type / Why it matters / What we watch / Risk Rating
  ("N/10: reason"), ordered by rating descending and enforced by a
  generation gate (`_risk_card_format_errors`,
  `server/memo_docx_renderer.py`).

## The loop

### 1. Empty state

A company with no completed report shows no risk cards — just a notice:
"Run a detailed report to gather the data needed." No more silent
placeholder seeding. Requires a migration or "reset from report" action
for companies whose state file already holds the three placeholder cards
(they will never re-seed on their own).

### 2. Seed from report (parse, don't prompt)

When a completed report exists and the studio risk section is empty,
seed cards directly from the stored `memo_package.json`:

- card title ← the "Risk N" heading's one-line summary
- category ← Risk Type row
- severity/rating ← Risk Rating row (`N/10` is machine-readable)
- bullets ← Why it matters + What we watch rows
- initial rank ← the register's rating order

Because the register format is validated at generation time, this is
deterministic parsing — no LLM call, no cost, no hallucination surface.
The "smart ranking" comes for free: the register is already ordered by
rating. Store provenance on the section (report id + generated_at) so
the UI can say which document the cards came from.

### 3. Human editing

Unchanged from today's UI: re-rank with the arrows, include/exclude with
the checkbox, edit bullets. After the first seed, the studio state is
authoritative — a newer report never overwrites a non-empty section
(no clobbering loop). Refreshing from a newer report is an explicit
user action, not automatic.

### 4. Refine the report

New action: regenerate the document's risk section from the user's
edits **without re-running research**. Mechanics:

- Edit the stored `memo_package.json`, never the DOCX. The renderer
  rebuilds the full bilingual DOCX from a package deterministically,
  and all gates (card format, quality lint, Chinese parity) run on the
  package. This mirrors the existing resume pipeline's artifact-reuse
  pattern.
- One targeted Claude call rewrites only the `investment_risk` section
  (and, if needed, risk mentions in the executive summary), taking the
  user's ranking, exclusions, and text edits as input.
- Re-render and re-lint. Cost is minutes and cents versus the ~1 hour /
  ~$2 full pipeline.

## Design decision: user rank vs. rating order

The generation gate enforces rating-descending order in the register.
If the user drags a 6/10 above an 8/10, a naive regeneration violates
the gate. Resolution chosen: treat the user's ranking as a **judgment
signal, not a display order**. The refine prompt tells Claude "the user
considers X more important than Y — re-score and re-justify the ratings
accordingly," so ratings and order stay consistent and the document
reflects the user's view with reasons. The gate stays as-is.

## Open items

- **Likelihood / probability of occurrence** is missing from the risk
  cards (both register and studio). Once this loop exists it is one more
  row in the register contract plus one more field on the studio card,
  riding the same seed/refine pipeline. Deferred to its own task.
- Report ↔ company linkage: seeding needs a "latest completed report for
  this company" lookup against `data/reports/*.yaml`; confirm the key at
  implementation time.
- Bilingual: studio cards seed from the `en` values; the refine pass
  must maintain `zh` parity (existing parity gate already enforces this
  on the package).
- Suggested split: studio UI states (empty notice, seed button, refine
  button, provenance display) are frontend-shaped and hand off cleanly;
  package parsing, seeding endpoint, and the refine generation pass are
  the backend half.

No implementation has started; this document records the agreed shape.
