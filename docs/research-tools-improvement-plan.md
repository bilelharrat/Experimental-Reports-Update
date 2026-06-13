# Research Tools Improvement Plan

Last updated: 2026-06-13

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
- Added bounded source chunks and source traces for external research analysis,
  including document, page, slide, and speaker-note locators.

Implemented on 2026-06-13:

- Added the shared `queued` / `running` / `done` / `error` / `cancelled` /
  `recovered` status contract to progress events.
- Added source chunks and source traces to company research quick summaries,
  including PDF page, PPTX slide, speaker-note, document, and OCR locators.
- Added Memo Studio selected source ids, selected-source Claude work folders,
  structured research-task results, source evidence, and sources-checked
  persistence.
- Added a run-all-selected research-task endpoint with per-task retry semantics
  and a shared concurrency gate.
- Added a per-company evidence matrix endpoint.
- Added promotion from external research uploads into company background
  documents with metadata preservation and idempotency.
- Added low-text PDF OCR-needed detection plus OCR extraction for image PDFs
  and screenshot/image research files using local `pdftoppm` + `tesseract`.
- Fed structured research-task evidence and open questions into readiness
  gates, memo packet output, and explicit gap/caveat reporting.
- Added research output observability helpers, analyst-review score fields,
  evidence coverage metrics, and fixture-style output-shape regression tests.

## P0 - Job Lifecycle Consistency

Goal: every long-running research job behaves the same way.

- [x] Add explicit cancel endpoints for research summaries, external research
  analysis, external PDF translation, and Memo Studio research tasks.
- [x] Persist `queued`, `running`, `done`, `error`, `cancelled`, and
  `recovered` consistently across all research job families.
- [x] Add stale-run recovery for external research analysis and research
  summaries, matching Memo Studio's recovery semantics.
- [x] Use one shared helper for progress-log idempotency, stale superseding,
  and active-job descriptors.

## P1 - Evidence Quality

Goal: make each research output more decision-grade and source-backed.

- [x] Store source traces for summaries and task results: file id, filename,
  page or section if available, quoted excerpt, and confidence.
- [x] Add an evidence matrix per company that maps claims to supporting,
  contradicting, and missing evidence.
- [x] Let Memo Studio research tasks select specific uploaded research files as
  inputs instead of always using the full research folder.
- [x] Promote useful external research items into a company's background-docs
  folder with metadata preserved.

## P1 - Better Extraction

Goal: handle real research artifacts more reliably.

- [x] Add OCR for image-only PDFs and screenshots.
- [x] Add PPTX extraction for external research analysis, not only company
  background-doc summaries.
- [x] Detect scanned or low-text PDFs before sending them to analysis and show a
  clear "OCR needed" state.
- [x] Preserve page-level text chunks so later tools can cite source pages.

## P1 - Research Task Effectiveness

Goal: make Memo Studio tasks answer the underwriting question directly.

- [x] Generate task-specific search plans before running Claude.
- [x] Return structured task results with `answer`, `supporting_evidence`,
  `contradicting_evidence`, `open_questions`, `sources_checked`, and
  `confidence`.
- [x] Add "run all selected tasks" with concurrency limits and per-task retry.
- [x] Let completed task results flow into readiness gates and memo packet
  sections with source traces.

## P2 - Evaluation And Observability

Goal: know when the research tools are improving.

- [x] Add golden-fixture tests for quick summaries, external research analysis, and
  Memo Studio task outputs.
- [x] Track per-job duration, Claude cost, source count, and evidence coverage.
- [x] Add regression tests for duplicate launches, stale logs, cancelled jobs, and
  deleted-item cleanup across all research job types.
- [x] Add a small analyst-review score to research outputs so future prompt
  changes can be compared against accepted results.

## Implementation Checklist

Use this section as the working checklist. Mark items complete only after the
implementation and listed verification both pass.

### Slice 1 - Finish Job Lifecycle Consistency

Implementation:

- [x] Define one shared research-job state contract for `queued`, `running`,
  `done`, `error`, `cancelled`, and `recovered`.
- [x] Persist the state contract consistently on company quick summaries,
  external research analysis, external PDF translation, and Memo Studio
  research tasks.
- [x] Move duplicate idempotency checks into a shared helper.
- [x] Move stale superseding/recovery decisions into a shared helper.
- [x] Move active-job descriptor generation into a shared helper or adapter
  registry so each job family exposes the same core fields.

Verification:

- [x] Add/extend tests that each job family records the same terminal and
  non-terminal state shape.
- [x] Add/extend tests that active, stale, cancelled, recovered, completed, and
  deleted states do not appear incorrectly in `/api/jobs/active`.
- [x] Run `python -m pytest tests/test_external_research_jobs.py
  tests/test_serena_analysis.py tests/test_memo_analysis.py`.
- [x] Run full `python -m pytest`.

### Slice 2 - Source Traces For Company Quick Summaries

Implementation:

- [x] Reuse the source chunk model for company background documents under
  `data/research/<company>/`.
- [x] Preserve page/slide/document locators for quick-summary inputs.
- [x] Update quick-summary structured output to request source-backed traces.
- [x] Persist `source_chunks`, `source_chunk_count`, `source_traces`, and
  `source_trace_count` on the research file record or its `quick_summary`
  block.

Verification:

- [x] Add tests for TXT/Markdown document traces.
- [x] Add tests for PDF page traces.
- [x] Add tests for PPTX slide and speaker-note traces.
- [x] Add a fallback-trace test when Claude returns no valid trace.
- [x] Run `python -m pytest tests/test_external_research_jobs.py
  tests/test_library_files.py`.

### Slice 3 - Memo Studio Research Task Source Selection

Implementation:

- [x] Add task-level selected source ids for company background documents and,
  if useful, promoted external research items.
- [x] Add API support to save selected source ids per task.
- [x] Update task prompt assembly so Claude receives only selected sources
  when a selection exists, otherwise the existing full-folder fallback.
- [x] Include `sources_checked` metadata on task results.

Verification:

- [x] Add tests that selected source ids persist on task patch/update.
- [x] Add tests that task runs pass only selected source content to Claude.
- [x] Add tests that the no-selection fallback preserves current behavior.
- [x] Run `python -m pytest tests/test_serena_analysis.py`.

### Slice 4 - Structured Memo Studio Research Results

Implementation:

- [x] Replace free-form task result payloads with structured fields:
  `answer`, `supporting_evidence`, `contradicting_evidence`,
  `open_questions`, `sources_checked`, and `confidence`.
- [x] Normalize legacy/free-form outputs into the structured shape when
  possible.
- [x] Persist evidence entries with file id, filename, locator, excerpt, and
  confidence.
- [x] Surface structured summaries in existing task result views without
  breaking older sessions.

Verification:

- [x] Add tests for successful structured task output.
- [x] Add tests for malformed Claude output fallback.
- [x] Add tests that previous task results are preserved on errors.
- [x] Run `python -m pytest tests/test_serena_analysis.py`.

### Slice 5 - Run All Selected Tasks

Implementation:

- [x] Add a run-all-selected endpoint for Memo Studio research tasks.
- [x] Apply a concurrency limit so multiple Claude jobs cannot swamp the local
  environment.
- [x] Add per-task retry semantics for failed/cancelled tasks.
- [x] Make the active-jobs rail show each task independently while the batch is
  running.

Verification:

- [x] Add tests for batch launch, concurrency limit behavior, retry, and
  already-running tasks.
- [x] Add tests that partial failures do not block successful tasks.
- [x] Run `python -m pytest tests/test_serena_analysis.py`.

### Slice 6 - Evidence Matrix

Implementation:

- [x] Define the per-company evidence matrix data model: claim, status,
  supporting evidence, contradicting evidence, missing evidence, confidence,
  and source coverage.
- [x] Build/update the matrix from external research traces, quick-summary
  traces, and Memo Studio research-task evidence.
- [x] Add an API endpoint to read the company evidence matrix.
- [x] Add update/rebuild behavior when new evidence-bearing outputs are saved.

Verification:

- [x] Add unit tests for matrix construction from mixed source types.
- [x] Add tests for supporting, contradicting, and missing evidence buckets.
- [x] Add tests that stale/replaced evidence is not duplicated.
- [x] Run `python -m pytest tests/test_external_research_jobs.py
  tests/test_serena_analysis.py`.

### Slice 7 - Promote External Research To Company Background Docs

Implementation:

- [x] Add an API endpoint to promote an external research item into
  `data/research/<company>/`.
- [x] Copy the original file bytes into the company background-docs folder.
- [x] Preserve source metadata: title, source company, contact, notes,
  original external item id, summary, key points, source chunks, and traces.
- [x] Make promotion idempotent so the same external item is not duplicated
  accidentally.

Verification:

- [x] Add tests for successful promotion.
- [x] Add tests for idempotent repeat promotion.
- [x] Add tests for missing/deleted source file behavior.
- [x] Add tests that promoted files can run quick summaries without losing
  metadata.
- [x] Run `python -m pytest tests/test_external_research_jobs.py
  tests/test_library_files.py`.

### Slice 8 - OCR Needed Detection

Implementation:

- [x] Detect low-text or image-only PDFs during extraction.
- [x] Persist an `ocr_needed` or equivalent state on affected research items.
- [x] Show a clear analysis error/state instead of sending empty content to
  Claude.
- [x] Add a small OCR abstraction point so real OCR can be added behind the
  same interface later.

Verification:

- [x] Add tests for empty/low-text PDFs.
- [x] Add tests that normal text PDFs still analyze normally.
- [x] Add tests that `ocr_needed` jobs do not appear active after termination.
- [x] Run `python -m pytest tests/test_external_research_jobs.py`.

### Slice 9 - OCR For Image PDFs And Screenshots

Implementation:

- [x] Choose and wire the OCR runtime available in this local app environment.
- [x] Add OCR extraction for image-only PDFs.
- [x] Add OCR extraction for image uploads/screenshots in company background
  docs.
- [x] Preserve OCR-derived page/image locators in source chunks and traces.

Verification:

- [x] Add fixture tests with a small image-only PDF or generated image.
- [x] Add tests for OCR failure fallback.
- [x] Run focused extraction tests and full `python -m pytest`.

### Slice 10 - Readiness Gates And Memo Packet Integration

Implementation:

- [x] Feed completed structured research-task results into readiness gates.
- [x] Feed high-confidence supporting/contradicting evidence into memo packet
  sections.
- [x] Flag open questions and missing evidence as readiness blockers or
  explicit caveats.
- [x] Preserve source traces through memo packet handoff.

Verification:

- [x] Add tests that readiness gates change after task completion.
- [x] Add tests that open questions/missing evidence are represented as gaps.
- [x] Add tests that memo prep receives evidence-bearing context.
- [x] Run `python -m pytest tests/test_serena_analysis.py
  tests/test_memo_prep.py tests/test_memo_analysis.py`.

### Slice 11 - Evaluation And Observability

Implementation:

- [x] Add golden fixtures for quick summaries, external research analysis, and
  Memo Studio research-task outputs.
- [x] Track per-job duration, Claude cost, source count, and evidence coverage.
- [x] Add analyst-review score fields to research outputs.
- [x] Add comparison helpers so prompt changes can be evaluated against accepted
  outputs.

Verification:

- [x] Add fixture-based regression tests for output shape and important
  evidence fields.
- [x] Add tests that metrics persist for success, error, cancel, and recovery.
- [x] Run full `python -m pytest` and `npm --prefix frontend test` when UI
  surfaces are touched.

## Completed Slice - Shared Research Job Lifecycle Baseline

Applied to:

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
