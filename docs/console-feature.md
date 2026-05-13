# Company Console — design & build plan

Per-company conversational pane backed by a persistent Claude Code
session. The user picks which existing documents to hydrate the session
with, then asks follow-up questions (text + images) and reads streamed
responses. Token usage and cost are tracked per session. Multiple
simultaneous sessions per company are supported; within a single session
turn submissions are serialized to preserve conversation continuity.

This doc is the spec for implementation. Three phases at the bottom.

---

## 1. UX

Lives as the third tab on the company Research view:

```
Overview · Documents · [Console]
```

### Empty state (no sessions yet)

```
┌─ Console ───────────────────────────────────────────────────┐
│ Ask follow-up questions about this company. Claude reads    │
│ the documents you select once, then keeps them in context   │
│ for the rest of the session.                                │
│                                                             │
│  ☑ Include background documents (3 files)                   │
│  ☑ Include library documents (2 files)                      │
│                                                             │
│           [ Create console ]                                │
└─────────────────────────────────────────────────────────────┘
```

Both checkboxes default to checked. The file counts come from the
existing `listResearchFiles` / `listFiles` endpoints so the user knows
what they're hydrating.

### Active state

```
┌─ Console ──────────────────────────────────────────────────────┐
│ [● Pitchdeck Q&A] [○ Market sizing] [+ New]   Archived (3) ▾   │
├────────────────────────────────────────────────────────────────┤
│ Tokens: 342K / 1M used  ████░░░░░░ 66% free  ·  $0.412         │
│                                                                │
│ ▶ You (12:04)                                                  │
│   What's AMI Labs' burn rate based on the pitch deck?          │
│                                                                │
│ ▶ Claude (12:04, 4.2s, $0.018)                                 │
│   Per Slide 18: monthly opex of $14.2M …                       │
│                                                                │
│ ▶ You (12:07) [📎 chart.png]                                   │
│   Reconcile this chart with what Slide 22 shows.               │
│                                                                │
│ ▶ Claude (queued — position 2)                                 │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────────┐   │
│ │ Type or paste a question, drop images here…              │   │
│ └──────────────────────────────────────────────────────────┘   │
│  [📎 attach]   [⟶ Send]    [End session]                       │
└────────────────────────────────────────────────────────────────┘
```

- **Tab strip** at the top: one tab per active session.
  - `+ New` opens the create-console modal.
  - `Archived (n) ▾` is a dropdown of archived sessions with their
    summaries; click to open a read-only transcript view.
- **Token bar** updates after each completed turn.
  - Green < 75%, yellow 75–90% with a banner "Session getting full —
    consider starting a new one", red ≥ 90% with the input disabled
    and a prominent "Archive & start new" CTA.
- **Transcript** auto-tails the latest response. Earlier turns stay
  expanded; the scroller auto-anchors to the bottom while streaming.
- **Input area** accepts text, drag/drop image files, clipboard paste.
  Send button submits. Submissions are queued per session (see
  Concurrency below).
- **End session** archives the active session (triggers an automatic
  summary) without opening a new one.

### Create-console modal

Triggered by `+ New` or the empty-state button. Shows:

- Both checkboxes (Include background / Include library)
- The exact file list each checkbox covers, so the user can see what
  Claude will read
- An estimate: `~$X.XX, ~Ns to read` (computed from staged file sizes
  / page counts using the same heuristics as quick-summary)
- A "Confirm" and "Cancel"

After confirm, the inline area on the tab shows a one-line
status ("Reading 3 of 5 docs…"), and the existing `ActiveJobsRail`
picks up the hydration job by `job_init` event (same plumbing as deep
search and quick-summary).

---

## 2. Data model & on-disk layout

```
data/consoles/<company_id>/
  sessions/
    <session_id>/
      meta.json
      turns.jsonl
      attachments/
        <sha256>.<ext>
      workdir/            ← Claude's --add-dir target; hard-links or
                            copies of staged docs + an attachments/
                            subdir for user-uploaded images
      hydrate.progress.jsonl
      ask.progress.jsonl   ← appended-to per turn (one job per turn)
```

There is **no `current.json`** — each session has independent status.
Listing iterates `sessions/` directly.

### `meta.json`

```json
{
  "id": "<uuid>",
  "company_id": "...",
  "claude_session_id": "<uuid passed to --session-id>",
  "model": "claude-opus-4-7-1m",
  "status": "active" | "archived",
  "title": "Pitchdeck Q&A",
  "created_at": "...", "last_used_at": "...",
  "archived_at": null | "...",
  "include_background_docs": true,
  "include_library_docs": true,
  "included_file_ids": ["...", "..."],
  "tokens": {
    "input": 342000, "output": 18400,
    "cache_read": 312000, "cache_creation": 30000,
    "total_cost_usd": 0.412
  },
  "summary": null | {
    "headline": "Pitchdeck Q&A on AMI Labs",
    "bullets": ["Burn rate analysis…", "Slide-22 chart reconciliation…"],
    "generated_at": "..."
  }
}
```

- `claude_session_id` is the UUID we pass to `claude -p --session-id`
  on hydration and `--resume` on every subsequent turn.
- `title` is initially `"Session · HH:MM"`; auto-replaced with a
  3–6-word LLM-derived label after the first Q&A turn lands.
- `summary` is populated on archive only.

### `turns.jsonl`

Append-only, one event per line. Roles:

```json
{"ts": "...", "id": "<turn-id>", "role": "user",
 "text": "…", "attachments": [{"id":"sha256…", "name":"chart.png"}]}

{"ts": "...", "id": "<turn-id>", "role": "assistant",
 "text": "…", "cost_usd": 0.018, "duration_ms": 4210,
 "tokens": {"input":…, "output":…, "cache_read":…, "cache_creation":…},
 "subtype": "success" | "error"}
```

Each user turn has a matching assistant turn with the same `id`. While
a turn is in flight the `id` lives only in memory (no assistant record
written yet) — the live stream is on
`/console/sessions/<sid>/ask/stream/<turn_id>`.

---

## 3. Backend API surface

All endpoints sit under `/api/companies/{company_id}/console`. The
existing `require_api_token` dependency on the api_router covers
auth — no Console-specific auth changes.

Note the deployment context: the app is served under `root_path="/research"`
(nginx upstream). Frontend code uses paths like `/api/...`; the SPA
prepends the base via `withBase()`/`withApiToken()` automatically. The
Console reuses these helpers, so no path-prefix concerns at the Console
layer.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/console/sessions` | List ALL sessions (active + archived). |
| `POST` | `/console/sessions` | Create a new session. Body: `{include_background_docs, include_library_docs}`. Async — returns `{id, claude_session_id, hydrate_job_id, stream_url}` immediately; hydration streams on `stream_url`. |
| `GET` | `/console/sessions/{sid}` | One session's metadata + token meter. |
| `GET` | `/console/sessions/{sid}/turns` | Full transcript. |
| `POST` | `/console/sessions/{sid}/ask` | Submit a question. `multipart/form-data` with `prompt` text + zero or more image files. Returns `{turn_id, stream_url, queue_position}`. |
| `GET` | `/console/sessions/{sid}/ask/stream/{turn_id}` | SSE stream for one turn's claude_action / result events. |
| `GET` | `/console/sessions/{sid}/attachments/{img_id}` | Serve a user-uploaded image attachment (with the existing token-in-query mechanism). |
| `POST` | `/console/sessions/{sid}/archive` | Archive a session. Triggers a summarize subprocess and writes `meta.summary`. |
| `DELETE` | `/console/sessions/{sid}` | Hard delete (for cleanup, rarely used). |

All endpoints inherit the api_router auth dependency. The SSE stream
endpoints accept `?token=` for EventSource compatibility (same pattern
as `searchStreamUrl`).

### Job-rail integration

Hydration, each ask, and the archive-summary all emit a `job_init`
event to a `ProgressLog`. The `ActiveJobsRail` polls
`/api/jobs/active`, so they show up automatically. Job kinds:

- `console_hydrate` — title: "Hydrating console: {company}"
- `console_ask` — title: "Q&A: {first 40 chars of prompt}…"
- `console_summary` — title: "Summarizing session: {session.title}"

---

## 4. Claude subprocess strategy

The Console is the **first** subprocess flow in the codebase that needs
session persistence. Existing call sites in `server/claude_runner.py`
all pass `--no-session-persistence`; the Console paths must drop that.

### Hydration call (one per session, on create)

```
claude -p
  --output-format stream-json --verbose
  --session-id <UUID we generate>
  --add-dir <workdir>
  --permission-mode bypassPermissions
  --dangerously-skip-permissions
  --allowedTools "Read,WebSearch,WebFetch,Bash"
  --append-system-prompt <bsh_company_console.md skill>
  "<hydration prompt: 'Read these N docs into context. Then await
   follow-up questions.'>"
```

We do not require Claude to produce a substantive reply here — the
prompt instructs it to confirm with a one-line acknowledgement. The
goal is to populate the on-disk session state with the documents
loaded as cached context.

### Ask call (one per user turn)

```
claude -p
  --output-format stream-json --verbose
  --resume <claude_session_id from meta.json>
  --add-dir <workdir>          ← attachments/ now contains the new uploads
  --permission-mode bypassPermissions
  --dangerously-skip-permissions
  --allowedTools "Read,WebSearch,WebFetch,Bash"
  "<user prompt; references attached image filenames>"
```

Augmentation: when the user attaches `chart.png`, the prompt sent to
Claude becomes:

> {user text}
>
> (Attached: `attachments/chart.png`. Use the Read tool to view it.)

Claude Code's `-p / --print` mode doesn't take inline base64 image
parts — Read on a file path is how it sees multimodal content.

### Summarize call (on archive)

```
claude -p
  --output-format json
  --permission-mode bypassPermissions
  --dangerously-skip-permissions
  --no-session-persistence
  --allowedTools "Read"
  "<prompt with the full turns.jsonl as a quoted block>"
```

Short single-shot run, no streaming needed. Returns the
`{headline, bullets}` summary, written into `meta.summary`.

### New helpers in `server/claude_runner.py`

- `run_console_hydrate(*, claude_session_id, work_dir, file_list,
   skill_path, progress)` → `{ok, tokens, cost_usd, error?}`
- `run_console_ask(*, claude_session_id, work_dir, user_prompt,
   skill_path, progress)` → `{ok, text, tokens, cost_usd, error?}`
- `run_console_summary(*, turns, progress)` → `{headline, bullets,
   error?}`

All three follow the existing stream-json processing pattern. The
StructuredOutput preference logic from `run_company_search` is not
needed here — these are free-form text outputs, not schema-constrained.

### Skill

New file `server/skills/bsh_company_console.md`:

- Persona: senior research analyst, terse and citation-heavy.
- Document-discipline: when answering, ground claims in the staged
  files using Read; cite by filename and (where possible) page.
- Style: Markdown bullets for lists; tables for comparative data;
  no apologetic preamble.
- Bilingual: respect the user's question language; reply in the same.

Loaded via `--append-system-prompt` reading the file.

---

## 5. Token / cost accounting

### Budget

Model is `claude-opus-4-7[1m]` ⇒ 1,000,000 input-token context window.
The meter compares cumulative `input_tokens` (which grows with each
turn since the whole history is resent and shows up as either
`cache_creation` on first send or `cache_read` thereafter) against
that budget.

`%free = max(0, (1_000_000 - cumulative_input_tokens) / 1_000_000)`

### Thresholds

| Range | UI state | Behavior |
|---|---|---|
| <75% used | Green | Normal operation |
| 75–90% used | Yellow banner | Banner: "Session getting full — consider starting a new one." Input still works. |
| ≥90% used | Red banner | Input disabled. Primary CTA: "Archive & start new." Send button hides. |

The thresholds are constants in the frontend; backend doesn't enforce
them (it's a UX guardrail, not a security one).

### Per-turn accounting

Each `result` event from `stream-json` gives:

```json
{ "type": "result", "subtype": "success",
  "total_cost_usd": 0.0185,
  "duration_ms": 4210,
  "usage": {"input_tokens":…, "output_tokens":…,
            "cache_read_input_tokens":…, "cache_creation_input_tokens":…} }
```

On turn completion we (a) append the assistant turn to `turns.jsonl`
with these numbers, (b) atomically update `meta.json.tokens` with the
deltas. UI re-fetches meta after each completed turn.

---

## 6. Session lifecycle

1. **Create** — `POST /console/sessions` with checkbox flags. Server:
   1. Generates `session_id` (UUID) and `claude_session_id` (UUID).
   2. Lays out `data/consoles/<co>/sessions/<sid>/` and a `workdir/`
      with hard-linked copies of selected docs.
   3. Writes initial `meta.json` with `status: "active"`.
   4. Emits `job_init` for `console_hydrate`.
   5. Spawns the hydration subprocess in a background thread.
   6. Returns the descriptor immediately (200 OK, hydrating).

2. **Ask** — `POST /console/sessions/<sid>/ask` with multipart body:
   1. Stage uploaded images into `workdir/attachments/<sha>.<ext>`.
   2. Append a user-role record to `turns.jsonl` with `turn_id`.
   3. Acquire the per-session queue lock (see Concurrency).
   4. Emit `job_init` for `console_ask`; spawn ask subprocess.
   5. Return `{turn_id, stream_url, queue_position}` immediately.

3. **Archive** — `POST /console/sessions/<sid>/archive`:
   1. Set `status: "archived"`, `archived_at`.
   2. Emit `job_init` for `console_summary`; spawn summarize.
   3. On completion, write `meta.summary` and persist.
   - From here the session is read-only: ask endpoint returns 409.

4. **Hard delete** — `DELETE /console/sessions/<sid>` removes the
   directory entirely. The Claude Code on-disk session is left to
   garbage-collect naturally (it's keyed by UUID and unreachable).

There is **no auto-archive when a new session is created.** Multiple
active sessions per company is normal.

---

## 7. Concurrency

### Within one session

Each session has a small in-process queue. `/ask` always succeeds and
returns a `queue_position`. The dispatcher runs one ask subprocess at
a time per session, releasing the next from the queue when the prior
finishes (success or error).

Rationale: `claude -p --resume <id>` mutates the on-disk session file.
Two concurrent runs on the same session id corrupt that file.

### Across sessions

Different sessions hold different `claude_session_id`s and therefore
write to different on-disk Claude session files. Multiple ask
subprocesses across different sessions run truly in parallel — no
queuing.

### UI

Within a session: queued turns appear in the transcript with a "queued
— position N" badge. The position decrements as prior turns complete.

Across sessions: each session tab has its own streaming state; tabs
update independently.

---

## 8. Auth

The Console inherits all auth from existing primitives:

- `apiFetch()` automatically adds the `Authorization: Bearer …` header.
  The token source is, in order: a session token stored in
  `localStorage` (set by future login UI via `POST /api/auth/token`),
  falling back to the `BSH_RESEARCH_API_TOKEN` `<meta>` tag the server
  injects into the SPA HTML when configured. No Console-specific code.
- `withApiToken()` appends `?token=…` to raw URLs for SSE streams and
  `<img src>`/`<a href>` downloads. The Console uses it for the ask
  stream URL and for attachment image src URLs.
- `withBase()` prepends `root_path` (e.g. `/research`) when the server
  is mounted under a prefix by nginx. Already used inside `apiFetch`
  and `withApiToken`; transparent to Console code.

---

## 9. i18n

Every user-visible string gets an EN + ZH pair in
`frontend/src/i18n.js`. Key namespace: `console.*`. Notable strings:

- `console.tab_label`, `console.create_console`, `console.empty_help`
- `console.include_background_docs`, `console.include_library_docs`
- `console.token_meter` (interpolated `{used}` / `{free_pct}` / `{cost}`)
- `console.warning_threshold`, `console.lock_threshold`
- `console.queued_position`, `console.archive_session`
- `console.archive_confirm`, `console.session_full_cta`

---

## 10. Implementation phases

Each phase is its own commit on `main` (per `CLAUDE.md`). The app
stays runnable between phases.

### Phase 1 — Backend

- `server/console_store.py` — file-based session/turn/attachment
  storage. Pure-Python, no DB.
- `server/console_session.py` — orchestration. Owns the per-session
  queue dispatcher. Imports `claude_runner` helpers.
- `server/claude_runner.py` — add `run_console_hydrate`,
  `run_console_ask`, `run_console_summary`.
- `server/skills/bsh_company_console.md` — analyst persona prompt.
- `server/api.py` — 9 endpoints under the existing api_router. SSE
  endpoint accepts `?token=` for EventSource.
- Minimal smoke test: a script that exercises create → ask → archive
  end-to-end without going through the UI.

### Phase 2 — Frontend

- `frontend/src/components/CompanyConsole.vue` — tab strip + active
  session pane (token meter, transcript scroller, input area).
- `frontend/src/components/ConsoleSessions.vue` — archived sessions
  dropdown + read-only transcript modal.
- `frontend/src/views/ResearchView.vue` — wrap existing content in a
  three-tab shell (Overview, Documents, Console).
- `frontend/src/api.js` — `console.*` methods. All routed through
  `request` / `apiFetch` / `withApiToken`, inheriting auth + root_path.
- `frontend/src/i18n.js` — EN + ZH keys.

### Phase 3 — Polish

- Token thresholds (75/90) with banner and lock behavior.
- Queued-turn UI: pending cards with position badge.
- Confirm-create modal with file list and cost estimate (estimate is
  a server-side helper that walks `included_file_ids` and sums page
  counts / sizes, returns `{tokens_est, cost_usd_est, duration_est_s}`).
- AI-rail polish: titles, click-to-tail behavior, end-of-job cost
  display.
- Auto-rename of session tab after first turn (LLM call against the
  first Q&A pair, cheap; uses `run_simple_structured` style).

Total effort estimate: 4–6 hours of focused work.

---

## 11. Out of scope (for v1)

These are deliberate omissions; revisit later if needed.

- **Editing past turns.** Once submitted, a turn is immutable. Resend
  to retry.
- **Branching the conversation.** No git-like "fork from turn N".
- **Cross-company sessions.** Each session is bound to one company.
- **Exporting the transcript.** Easy follow-up: "Download as .md".
- **Sharing sessions between users.** When per-user auth is wired,
  sessions stay private to the creating user.
- **Voice or audio inputs.** Text + image only.

---

## 12. Open questions resolved

These were settled in design discussion before this doc was written.
Recording here so they're not relitigated.

- Placement: third tab on Research view (vs. inline section). Tab.
- Tool surface for hydrate/ask: `Read + WebSearch + WebFetch + Bash`.
  Bash is allowed because the machine will be sandboxed at the OS
  level — caller's policy.
- Archived-session browsing: yes, full read-only transcripts visible.
  New session triggers an auto-summary on the archived one.
- Hydration cost: confirm dialog at create time with file list +
  estimate. Full progress in the AI Tasks rail (right sidebar).
- Token budget enforcement: 75% warn, 90% hard-lock. Frontend only;
  backend doesn't enforce.
- Concurrency: in-session = client queue + sequential `--resume`;
  cross-session = truly parallel (separate session files).
