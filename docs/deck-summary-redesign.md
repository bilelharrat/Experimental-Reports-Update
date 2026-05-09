# Deck-summary redesign — context transfer

This document is the handoff brief for a fresh session. The current
deck-summary pipeline is over-engineered, slow, expensive, and brittle. The
goal is to rebuild it around per-page atomic units with a rolling-window
context. Plus a side cleanup: the active-jobs UI belongs in the bottom of
the left sidebar, not the floating right rail.

Read sections 1–3 to understand the project. Sections 4–7 are the redesign.

---

## 1. Project orientation

**Name**: BSH Research Center (`bsh-research-center`).
**Stack**: FastAPI backend (Python, `uv`) + Vue 3 SPA (Vite, Tailwind).
**Auth**: none — local-only research dashboard.
**Run**: `./run.sh` — sources `.env` (loads `OPENAI_API_KEY`), runs `uv sync`,
builds the frontend if needed, launches uvicorn on `127.0.0.1:8010`.
**Data**: everything durable lives under `data/` (gitignored).

```
data/
  companies.yaml                    # company list (seed + AI-discovered)
  reports/<id>.yaml                 # generated agent reports (versioned)
  threads/<company>.yaml            # Q&A threads
  uploads/<company>/                # file uploads + summaries
    index.yaml                      # file metadata (incl. cached summary)
    <file_id>__<filename>           # the raw upload
    <file_id>__preview.pdf          # PowerPoint→PDF cache for .ppt previews
    <file_id>__summary.progress.jsonl   # per-job SSE event log (tail-able)
    <file_id>__job/                 # work dir for the running summary job
      <file_id>__<filename>         # staged copy Claude reads
      progress.md                   # human-readable progress trail
      summary.json                  # final structured output
  external/
    news/<id>.yaml                  # URL submissions w/ archived HTML
    external_research/<id>.yaml     # uploaded third-party research
    hormuz_research/<id>.yaml       # internal notes
  cache/
    companies_ai/<sha>.yaml         # OpenAI deep-search results, indefinite TTL
```

**Key endpoints** (FastAPI router at `/api`):

| Endpoint | Purpose |
|---|---|
| `GET /api/companies/...` | company list, autocomplete, deep-search |
| `POST /api/companies/{id}/refresh` | rerun AI deep search |
| `GET/POST /api/companies/{id}/files` | upload manager |
| `GET /api/companies/{id}/files/{fid}/preview` | PDF preview (PPT→PDF via PowerPoint) |
| `POST /api/companies/{id}/files/{fid}/summary` | **deck summary** (the redesign target) |
| `GET /api/companies/{id}/files/{fid}/summary/stream` | SSE feed for the above |
| `GET /api/jobs/active` | all in-flight summary jobs across the system |
| `GET /api/diagnostics/claude` | health-check the local `claude` CLI |
| `GET /api/external/news`, `/external/research`, `/external/hormuz` | external content surfaces |

**Frontend layout**:

- Left sidebar (`Sidebar.vue`) — Recent Reports / External Research and News /
  Hormuz Research.
- Main view — Home (search), Research page (per-company library + KB),
  detail pages for news / research / hormuz items.
- Top-right floating rail (`ActiveJobsRail.vue`) — **moves to bottom-left
  sidebar in this redesign.**
- Global modals — `DeckSummaryModal.vue` (the one being redesigned),
  `FilePreviewModal.vue`.

---

## 2. How deck summaries work today (the part being rewritten)

The user clicks the Sparkles icon on an uploaded file. The current flow:

1. **`POST /api/companies/{cid}/files/{fid}/summary?speed=...`** — kicks off
   a daemon thread, returns `{job_id, stream_url, status}`. Idempotent: if a
   job is already in flight, returns `status: "already_running"`.
2. **The thread** (`server/api.py::_run_summary_job`) calls
   `deck_summary.summarize_slides(...)` which:
   - Pre-extracts slide text via `pypdf` / `python-pptx` for an inventory
     pass that emits `slide_extracted` events. (We already have per-slide
     metadata at this point.)
   - **Spawns ONE `claude -p ... --output-format stream-json --json-schema`
     subprocess** in `server/claude_runner.py::run_summary` and tells it,
     in a single big prompt, to:
     - Read the deck (one page at a time in granular mode, or 20-page
       chunks in fast mode).
     - Append `- Slide N: <observation>` bullets to `progress.md` (Write
       on first, Edit on subsequent).
     - When done with all pages, compose a bilingual JSON summary
       conforming to a strict JSON schema, write it to `summary.json`,
       and return the same JSON as the model's final answer.
3. **The runner** (`claude_runner._process_event`) parses Claude's
   stream-json events one by one and translates them into our existing
   ProgressLog vocabulary:
   - `system.init` → `claude_action action=init`
   - `assistant.text` → `claude_action action=thinking`
   - `assistant.tool_use` → `claude_action action=tool_use` (Read / Write /
     Edit) — also parses `progress.md` writes for `- Slide N:` bullets to
     emit `slide_extracted` events and detect stage transitions
     (`analyzing` → `translating` once last slide is seen → `structuring`
     when `summary.json` is written).
   - `user.tool_result` → `claude_action action=tool_result`
   - `result` → cost / duration metadata.
4. **The frontend** (`DeckSummaryModal.vue`) opens an `EventSource` on the
   stream URL, replays the JSONL from byte 0 (so a reconnect after a refresh
   sees full history), then tails for new events. Renders a pipeline
   timeline, a slide-grid, a live-action feed, and finally the summary.

### What's wrong with this

- **One giant Claude session**, ~16 minutes for 42 slides, ~$5 per run
  (Anduril deck). Most of that cost is one giant accumulating context.
- **Brittle final JSON.** Claude wrote `"iOS/Android"` (unescaped emphasis
  quote) inside a Chinese string and the whole 16-min run came back unparseable.
  We worked around it with `_parse_json_tolerant` (regex that escapes
  ASCII `"` whose neighbors aren't JSON delimiters). Symptom of asking the
  model to do too much in one shot.
- **Claude ignores prompt subtleties.** In granular mode the prompt explicitly
  says "Read pages='1' then pages='2' …" but Claude saw the
  Read-tool error message ("This PDF has 26 pages, use the pages parameter")
  and grabbed the suggestion `pages="1-20"` from the error verbatim. We're
  fighting the tool's own affordances.
- **No exploitation of structure we already have.** The server already knows
  the page count, has per-page text extracts (where text exists), and
  could render per-page images cheaply. We hand all of that to one
  agentic-style call instead of using it.
- **Active-jobs visibility is in the wrong place.** Floating top-right rail
  is forgettable and detached from the main navigation. Belongs in the
  left sidebar bottom.
- **In-progress Sparkles button doesn't reflect job state.** After page
  refresh, the icon looks idle even when a job is running for that file.

---

## 3. The user's redesign

> *"Best is to say 'summarize one page' (and give it a rolling window of
> last page and next page) … take advantage of the work we did of
> identifying and breaking down the pages. This works especially well in
> the case that the pages are actually images."*

### 3.1 Per-page atomic summarization with rolling window

Instead of one giant Claude session, do **N small Claude calls** — one per
slide. Each call is **narrow, focused, fast, cheap, parallelizable**.

For slide N, the prompt is roughly:

```
You are summarizing one slide of a presentation deck.

Current slide: [slide N]   ← image and/or extracted text
Previous slide context: [slide N-1, summarized]   ← brief recap, ≤120 chars
Next slide context: [slide N+1, raw]   ← raw extract / image, just for continuity

Produce a JSON object:
{
  "slide_no": N,
  "title": "<one-line slide title or topic>",
  "observation_en": "<one specific factual sentence, 80-160 chars>",
  "observation_zh": "<simplified Chinese translation>",
  "key_terms": ["..."]    // proper nouns, numbers, dates worth surfacing
}
```

This is small, deterministic, and well-scoped. The model has zero
incentive to batch and zero ambiguity about what to produce.

**Rolling window**:
- Slide 1: no prev, has next.
- Slide N (middle): prev recap + current + next raw.
- Slide last: prev recap + current, no next.

The "prev recap" is the previous call's `observation_en` (or both
languages, but one is enough — Chinese is regenerated in synthesis).
The "next raw" is the page's extracted text (or, for image-only decks,
the image plus any OCR snippet we have).

### 3.2 Pre-computed inputs

The server has all the pieces already:

- **Page count**: `len(slides)` from `deck_summary.extract_slides`.
- **Per-page text** (text PDFs / pptx): already in `Slide.text` /
  `Slide.notes`.
- **Per-page images** (image PDFs): need to render. Use `pdf2image` or
  shell out to `pdftoppm -r 150 -f N -l N input.pdf out` to get one PNG
  per page on demand. Cache them under `<file_id>__job/pages/page_<N>.png`
  so retries / re-runs don't re-render.

For each Claude call, pass the rendered image as `--add-dir <job_dir>` +
filename reference, OR inline as a base64 image content block (the SDK
supports this — but `claude` CLI is what we're using; check whether
`-p` accepts attached images; if not, write the image into the work dir
and reference it by path in the prompt — Claude's `Read` tool reads
images natively).

### 3.3 Per-page concurrency

Page summaries are independent. Run a small pool (4–8 concurrent
subprocesses). For a 42-slide deck:
- Sequential: 42 × ~10s = ~7 min
- Concurrent (8-wide): ~6 min wall-clock, dramatically more cost-efficient
  per slide because each call is small.

The sequential dependency is only the rolling-window text: each call needs
the previous call's `observation_en`. Solve by either:
- Running sequentially but with smaller, much cheaper calls (still much
  faster than the current monolith), OR
- Running in two passes: pass 1 = "title + observation" with NO rolling
  context; pass 2 (optional) = "refine with rolling window" only for slides
  whose pass-1 observation was thin or ambiguous. Probably overkill.

**Recommendation**: start sequential. Concurrent is a v2 if needed.

### 3.4 Synthesis pass

After all per-page summaries are in, do **one final Claude call** with:

- The list of per-page summaries (`[{slide_no, title, observation_en, key_terms}]`).
- Instruction: produce the bilingual `exec_summary` (en + zh) plus 4–8
  `sections` each with `title.{en,zh}`, `body.{en,zh}`, `slide_refs`.

This is also small — input is ~42 short observations, not 42 slide images.
Output is structured JSON with our existing schema.

This pass is the only one where JSON-schema enforcement / strict mode
matters. Per-page calls can use simpler JSON (or even plain text parsed
on the server) since the structure is trivial.

### 3.5 What this buys us

- **Per-page progress is real.** Each Claude call corresponds to one
  `slide_extracted` event with the actual model output. No more parsing
  Claude's `Write progress.md` calls to figure out what slide it
  observed.
- **Failure is per-slide, not per-deck.** If slide 17 fails to summarize,
  retry just that slide. The other 41 are intact.
- **Cost shrinks.** Each call is ~5-10× smaller than today's monolith.
  Total cost should drop from ~$5 to ~$1-2.
- **Quality is more uniform.** Today the model gets fatigued / drifts as
  the conversation grows. Atomic calls don't have that problem.
- **Image-only decks just work.** Each call gets a single page image —
  much smaller token spend than a single 42-page vision call.
- **The synthesis pass produces clean JSON.** Smaller input + narrower
  output = far fewer JSON-escape bugs.

---

## 4. Session management — active-jobs in the LEFT sidebar

Today there's a `ActiveJobsRail.vue` component fixed to the top-right
corner. It works but it's not where the user looks.

**Move it into `Sidebar.vue` as a bottom section** — below
*Recent Reports* / *External Research and News* / *Hormuz Research*.

Layout sketch:

```
┌── Sidebar ────────────────┐
│  BSH Research Center      │
│  > Home                   │
│                           │
│  RECENT REPORTS           │
│  - …                      │
│                           │
│  EXTERNAL RESEARCH & NEWS │
│  - …                      │
│                           │
│  HORMUZ RESEARCH          │
│  - …                      │
│                           │
│  ─────────────────────    │
│  ACTIVE JOBS · 2          │ ← always visible at bottom when ≥1
│  ▸ ACME deck       42/42  │
│    Generating bilingual…  │
│  ▸ Stripe report   12/42  │
│    Analyzing slide 12     │
└───────────────────────────┘
```

- Click a job → opens `DeckSummaryModal` in reconnect mode (already works
  via the idempotent POST + SSE replay).
- The Sparkles icon on the file row in the Library should also reflect
  job state (spinning loader instead of the static icon when a job is
  running for that file). Click still opens the modal, just in
  reconnect mode.

**Implementation**:
- Move the active-jobs polling into `frontend/src/state.js` as a global
  ref (`activeJobs`) plus `startPolling()` / `refreshActiveJobs()` /
  `stopPolling()` helpers. App.vue starts polling on mount.
- `Sidebar.vue` consumes `activeJobs.value` directly.
- `closeSummary()` should call `refreshActiveJobs()` immediately so the
  user sees the running job appear in the sidebar the instant they
  dismiss the modal.
- `CompanyLibrary.vue` consumes `activeJobs.value` to render the Sparkles
  button as "in progress" when a job exists for the row's file.
- Delete `ActiveJobsRail.vue` after the move (or convert to a no-op).

---

## 5. What stays, what changes

### Stays as-is

These are good and shouldn't be touched in the redesign:

- All the company / report / external-research / hormuz scaffolding.
- File uploads + Library UI (`CompanyLibrary.vue`, `FilePreviewModal.vue`).
- PowerPoint→PDF preview pipeline (`server/files_store.py`).
- `pypdf` / `python-pptx` slide extraction (`deck_summary.extract_slides`)
  — this is the "inventory" pass and the redesign builds on top of it.
- `server/job_progress.py` ProgressLog (durable JSONL feed).
- `/summary/stream` SSE endpoint — the file-tailing replay+follow logic
  is solid.
- `DeckSummaryModal.vue` UI shell — header with EN/中文 toggle, exec-summary
  hero, supporting-detail expandos, watchdog. Just needs new event types
  (per-slide summary events instead of per-tool-call events).
- Inline summary preview line in Library row (`summaryPreview()`).
- `/api/jobs/active` + idempotent POST for survivable jobs.
- `_parse_json_tolerant` (still useful for the synthesis pass even if rarer).
- `/api/diagnostics/claude` health-check endpoint.

### Changes

- **`server/claude_runner.py`** — major refactor. Today it spawns one big
  Claude session and parses its tool calls. Replace with:
  - `summarize_one_page(slide_no, image_or_text, prev_recap, next_raw, hint_title) -> dict`
    — single small `claude -p` call with structured output for that page.
  - `synthesize_summary(per_page_summaries, hint_title, schema) -> dict`
    — final structured-output call.
  - The existing stream-json event translator still applies to each call;
    just one event stream per page rather than one per deck.
- **`server/deck_summary.py`** — new orchestrator that loops slides,
  calls `summarize_one_page` per slide, then calls `synthesize_summary`,
  emitting `slide_summarized`, `synthesizing`, `done` events to the
  ProgressLog. Vision fallback and OpenAI fallback can be deleted or
  trimmed — the new design works for both text and image PDFs uniformly.
- **PDF page rendering** — add `pdf2image` (uses `poppler`, which we'd
  need installed) OR shell out to `pdftoppm`. Cache in `<job_dir>/pages/`.
- **Frontend modal** — change the live-progress UI to render
  `slide_summarized` events with the actual title + observation, not the
  current "tool use" feed. The "BSH analyst — live actions" panel can
  become "Per-slide observations" with one row per slide as it lands,
  showing title + observation + slide number.
- **Active-jobs UI** — move to `Sidebar.vue` bottom; delete
  `ActiveJobsRail.vue`; globalize the poller in `state.js`.
- **In-progress Sparkles state** — `CompanyLibrary.vue` cross-references
  `activeJobs` to render the Sparkles button as a spinner for files
  with running summaries.

---

## 6. Concrete first actions for the next session

1. **Add `pdf2image` (or shell `pdftoppm`) integration.** Verify against
   the Anduril deck (`data/uploads/anduril-industries-inc/47a1ab54f7eb__Anduril_Deck.pdf`,
   42 pages, image-based — `pypdf` extracts no text). Render to
   `data/uploads/.../47a1ab54f7eb__job/pages/page_<N>.png` at ~150dpi.

2. **Write `claude_runner.summarize_one_page(...)`.** Spawn `claude -p`
   with a tight schema (slide_no, title, observation_en, observation_zh,
   key_terms). Pass the image filename and prev/next context in the
   prompt. Validate with `--json-schema`. Time + cost a single page
   against the Anduril deck before doing all 42.

3. **Write `claude_runner.synthesize_summary(...)`.** Takes
   `[{slide_no, title, observation_en, key_terms, ...}]` and produces
   the same `SUMMARY_SCHEMA` as today (exec_summary + sections). Keep
   `_parse_json_tolerant` as the safety net.

4. **Refactor `deck_summary.summarize_slides`** to be the orchestrator
   that walks slides and emits per-page progress events. Plumb `speed`
   to choose between sequential (granular) and a small concurrency pool
   (fast).

5. **Rewrite the modal's "Analyzing slides" UI** as a vertical list of
   slide cards as they arrive (`slide_no`, `title`, `observation`),
   replacing the current monospace tool-call feed.

6. **Move `ActiveJobsRail` into `Sidebar.vue`.** Delete the old
   component. Wire `state.js` as the polling source. Hook
   `closeSummary()` to `refreshActiveJobs()`.

7. **In-progress Sparkles**. In `CompanyLibrary.vue`, look up
   `activeJobs.value.find(j => j.company_id === companyId && j.file_id === f.id)`
   per row. If found, render `<Loader2 class="animate-spin">` instead of
   `<Sparkles>`. Title attr: "Open in-progress summary".

8. **Verify the watchdog still does its job.** With many small Claude
   calls, the SSE event cadence is high and the 90s no-event timeout
   becomes safer. But test it by killing a `claude` subprocess mid-deck
   and confirm the modal flips to error state.

9. **Cost telemetry.** Sum `claude_cost_usd` across all per-page calls
   plus the synthesis call. Surface the total in the modal header — same
   field name as today so the existing UI keeps rendering it.

---

## 7. Risks / open questions

- **Does `claude -p` accept image attachments inline?** If yes, we can
  send the page PNG directly; if no, we drop it in the work dir and rely
  on Claude's Read tool. Prefer inline (cheaper, no Read round-trip).
  Test this early.
- **Is `pdf2image`/`poppler` available everywhere we want this to run?**
  On the user's Mac yes (`brew install poppler`). Add it to the README.
- **Per-page rate limits / concurrency.** Anthropic's API has limits;
  going from 1 call/run to ~50 calls/run will hit them faster. Start
  sequential, add concurrency only if needed.
- **The rolling-window context is information that already exists in the
  server.** Don't wastefully re-summarize what we just summarized — pass
  the prior call's `observation_en` straight through.
- **PPTX (text) decks**: the rolling window can use extracted text
  directly, no rendering needed. PDF (image) decks need the rendering
  step. Branch on `kind` early.

---

## 8. Reference: current commit landscape

Recent commits relevant to this work (newest first):

```
dde0b2b  Salvage broken summary JSON when Claude leaves emphasis quotes unescaped
12c1809  Survivable summary jobs + reconnect rail + speed toggle
8fecb84  Granular pipeline + page-at-a-time + spinner watchdog
e80d5e1  Run deck summaries via Claude Code (subprocess) instead of OpenAI direct
ba5cdf1  Add GET /api/diagnostics/claude — quick Claude Code health check
f4e9005  Live SSE progress + inline summary preview
c41f5a6  Bilingual deck summary with slide-level citations
```

Read the diffs of the top three only if you need to understand the
existing event vocabulary. The redesign supersedes most of `e80d5e1` and
`8fecb84`.

`server/claude_runner.py` is the file most affected. `server/deck_summary.py`
is the second. `frontend/src/components/DeckSummaryModal.vue` is the
third.
