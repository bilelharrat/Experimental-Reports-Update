# Research Tools Improvement Plan

Last updated: 2026-06-11

This plan covers the research surfaces in the BSH Research Center:

- Company background documents under `data/research/<company>/`
- External research uploads under `data/external/external_research/`
- Memo Studio research tasks under `data/serena_analysis/<company>/<session>/`
- Active job rail entries, progress logs, summaries, translations, and retries

## Current Hardening Baseline

Implemented on 2026-06-11:

- External research uploads are bounded by the same 100 MB limit used by the
  company research library.
- External research analysis accepts only extractable files: PDF, PPTX, DOCX,
  TXT, and Markdown.
- Company research quick-summary launches are idempotent while a summary job is
  already active.
- Memo Studio research-task launches are idempotent while a task job is already
  active.
- Stale external research translation progress is superseded before a new
  translation job is queued.
- Deleting an external research item removes its analysis progress log,
  translation progress log, and translation work directory.

## Progress Log

Implemented on 2026-06-11:

- Added a shared progress lifecycle helper for terminal states, active-state
  detection, stale superseding, and cancellation markers.
- Added terminal `cancelled` and `recovered` progress events; SSE streams and
  the active-jobs rail now treat them the same way as `done` and `error`.
- Added cancel endpoints for company research quick summaries, external
  research analysis, external PDF translation, and Memo Studio research tasks.
- Wired cancellation into Claude subprocesses with live cancel events that
  terminate the process group with SIGTERM and SIGKILL fallback.
- Added stale-run recovery for company research quick summaries and external
  research analysis; recovered external-analysis jobs leave transient
  `queued` / `extracting` / `analyzing` state.
- Added regression coverage for cancelled jobs, stale recovery, duplicate
  launches, stale translation superseding, and deleted-item cleanup.
- Added PPTX support for external research uploads and analysis extraction,
  including slide and speaker-note text.

## P0 - Job Lifecycle Consistency

Goal: every long-running research job behaves the same way.

- [x] Add explicit cancel endpoints for research summaries, external research
  analysis, external PDF translation, and Memo Studio research tasks.
- [ ] Persist `queued`, `running`, `done`, `error`, `cancelled`, and
  `recovered` consistently across all research job families. Partial:
  terminal `cancelled` and `recovered` events are now shared.
- [x] Add stale-run recovery for external research analysis and research
  summaries, matching Memo Studio's recovery semantics.
- [ ] Use one shared helper for progress-log idempotency, stale superseding,
  and active-job descriptors. Partial: terminal scanning, active-state
  detection, stale superseding, and cancellation markers are shared.

## P1 - Evidence Quality

Goal: make each research output more decision-grade and source-backed.

- Store source traces for summaries and task results: file id, filename, page or
  section if available, quoted excerpt, and confidence.
- Add an evidence matrix per company that maps claims to supporting,
  contradicting, and missing evidence.
- Let Memo Studio research tasks select specific uploaded research files as
  inputs instead of always using the full research folder.
- Promote useful external research items into a company's background-docs folder
  with metadata preserved.

## P1 - Better Extraction

Goal: handle real research artifacts more reliably.

- Add OCR for image-only PDFs and screenshots.
- [x] Add PPTX extraction for external research analysis, not only company
  background-doc summaries.
- Detect scanned or low-text PDFs before sending them to analysis and show a
  clear "OCR needed" state.
- Preserve page-level text chunks so later tools can cite source pages.

## P1 - Research Task Effectiveness

Goal: make Memo Studio tasks answer the underwriting question directly.

- Generate task-specific search plans before running Claude.
- Return structured task results with `answer`, `supporting_evidence`,
  `contradicting_evidence`, `open_questions`, `sources_checked`, and
  `confidence`.
- Add "run all selected tasks" with concurrency limits and per-task retry.
- Let completed task results flow into readiness gates and memo packet
  sections with source traces.

## P2 - Evaluation And Observability

Goal: know when the research tools are improving.

- Add golden-fixture tests for quick summaries, external research analysis, and
  Memo Studio task outputs.
- Track per-job duration, Claude cost, source count, and evidence coverage.
- Add regression tests for duplicate launches, stale logs, cancelled jobs, and
  deleted-item cleanup across all research job types.
- Add a small analyst-review score to research outputs so future prompt changes
  can be compared against accepted results.

## Suggested Next Slice

Build a shared research job lifecycle helper and apply it to:

1. [x] Company research quick summaries
2. [x] External research analysis
3. [x] External PDF translation
4. [x] Memo Studio research tasks

Acceptance criteria:

- [x] Duplicate launch requests return `already_running`.
- [x] Stale non-terminal progress logs are marked and superseded or recovered.
- [x] Cancelled jobs emit a terminal progress event and stop appearing in the
  rail.
- [x] Deleted research items leave no active rail entries or orphaned progress
  logs.
- [x] Tests cover active, stale, cancelled, deleted, and completed states.
