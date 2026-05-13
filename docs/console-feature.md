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

### Workdir staging

`workdir/` is populated by `os.link()` for each included document; if
the hardlink call fails (e.g. cross-filesystem `data/`), we fall back
to `shutil.copy2`. Either way, edits to the original after hydration
do not bleed into the session: hardlinks point to the original inode
and atomic-replace-on-save editors leave that inode untouched; copies
are obviously independent. `workdir/attachments/` is created lazily on
the first ask that ships uploads.

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
| `GET` | `/console/sessions/{sid}/ask/stream/{turn_id}` | SSE stream for one turn's claude_action / result events. Replays from `ask.progress.jsonl` on reconnect — see Stream resumption below. |
| `POST` | `/console/sessions/{sid}/ask/{turn_id}/cancel` | Send SIGINT to the in-flight subprocess for this turn. 204 on success; 404 if no such turn or the turn has already completed. |
| `GET` | `/console/sessions/{sid}/attachments/{img_id}` | Serve a user-uploaded image attachment (with the existing token-in-query mechanism). |
| `POST` | `/console/sessions/{sid}/archive` | Archive a session. Triggers a summarize subprocess and writes `meta.summary`. |
| `DELETE` | `/console/sessions/{sid}` | Hard delete (for cleanup, rarely used). |

All endpoints inherit the api_router auth dependency. The SSE stream
endpoints accept `?token=` for EventSource compatibility (same pattern
as `searchStreamUrl`).

### Stream resumption

Each `*/stream/*` endpoint is a thin tail over the corresponding
`*.progress.jsonl` on disk. On reconnect with the same `turn_id` (or
session id for hydrate), the server replays every event accumulated
so far and then continues tailing. The client can drop and reconnect
at any time without losing intermediate `claude_action` events. The
stream closes once the terminal `result` event has been replayed.

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
The meter reflects **the size of the last turn's prompt** — that is
what is actually loaded into context on the next turn. It is *not* a
sum across turns: each turn's `input_tokens` already counts the full
history (mostly as `cache_read`), so summing would over-count by
orders of magnitude.

```
context_used = last_result.usage.input_tokens
             + last_result.usage.cache_read_input_tokens
             + last_result.usage.cache_creation_input_tokens

pct_used = context_used / 1_000_000
pct_free = max(0, 1 - pct_used)
```

The **cost** number in the meter (`$0.412` in the wireframe) *is* a
running total — sum of every turn's `total_cost_usd`, plus the
hydration cost. Only the context-window gauge uses the last-turn
formula.

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

### Cancellation & health

The system must detect — and recover from — three failure modes the
user can't fix by waiting: a user changing their mind, a subprocess
that dies, and a subprocess that hangs.

- **User stop.** While a turn is in flight, a "Stop" button appears
  next to "Send" in the active session. Clicking it POSTs
  `/console/sessions/{sid}/ask/{turn_id}/cancel`; the server sends
  `SIGINT` to the subprocess — the same signal a human Ctrl-C in
  `claude -p` would send, exercised exactly as it has been from the
  command line. Claude's normal interrupt flow drains, the result
  event lands with `subtype: "error"`, and the ask handler writes the
  error turn and releases the queue lock.
- **Subprocess died.** Each running ask is wrapped in a coroutine
  that watches the OS-level `Process.returncode`. If it transitions
  to non-None *before* a terminal `result` event has been written to
  `ask.progress.jsonl`, we synthesize an assistant turn with
  `subtype: "error"`, `text: "Claude subprocess exited unexpectedly
  (code=N)"`, and release the queue.
- **Subprocess hung.** The same coroutine tracks elapsed time since
  the last stream-json event was appended to `ask.progress.jsonl`.
  If it exceeds **90 seconds** of silence, we send SIGINT, wait up to
  30s for clean exit, then SIGKILL. The synthesized error turn
  records which signal succeeded.
- **Wall-clock cap.** A backstop of **10 minutes** per ask. Past
  that, the watchdog interrupts even if events are still flowing.
  This is a safety net for runaway prompts, not the primary control.
- **Startup recovery sweep.** On boot, `console_session.recover()`
  walks `data/consoles/*/sessions/*/turns.jsonl`. Any session whose
  last record is a user turn with no matching assistant gets one
  synthesized as `{role: "assistant", subtype: "error", text:
  "Interrupted by server restart"}`. Queued-but-not-started turns do
  not survive restart (the queue is in-process by design); the user
  resends. Without this sweep, refreshing into a mid-flight session
  shows a spinner forever.

All four mechanisms write through the same "synthesize error turn +
release queue" path, so they share test coverage (see §11).

### UI

Within a session: queued turns appear in the transcript with a "queued
— position N" badge. The position decrements as prior turns complete.
A "Stop" button replaces the queue badge once a turn is actively
streaming.

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

## 10. Resource limits

Caps are enforced at the API layer; failures return `400` with a
specific `code` so the frontend can translate the message. Limits live
as constants in `server/console_store.py` for easy adjustment.

### Attachments

- **Per-image size:** ≤ 10 MB. Larger uploads return
  `400 {code: "attachment_too_large", limit_bytes: 10485760}`.
- **Type allowlist:** `image/png`, `image/jpeg`, `image/webp`. Anything
  else returns `400 {code: "attachment_type_not_allowed"}`.
- **MIME sniffing:** server verifies by reading the first 16 bytes of
  each upload (PNG header, JPEG SOI, RIFF/WEBP). The client-supplied
  `Content-Type` and filename are not trusted; rejecting a renamed
  `.exe` is a baseline expectation here.

### Sessions

- **Max active sessions per company:** 6. `POST /console/sessions`
  while already at 6 actives returns `409 {code:
  "session_limit_reached", limit: 6}`. The frontend disables `+ New`
  at the cap with a tooltip: "Archive a session to start a new one."
- No cap on archived sessions — they don't consume process resources,
  only disk. A bulk-purge admin action is out of scope for v1.

### Path-safety

- `sid`, `turn_id`, and `img_id` parameters are validated as UUID-v4
  / sha256-hex respectively before being joined into a filesystem
  path. The api layer rejects malformed values with `400` rather than
  passing them through to `os.path.join`.

---

## 11. Testing strategy

The Console is the largest single feature in the repo and the first
one that holds state across multiple Claude invocations. The repo has
no test infrastructure today; this section adds it.

Three layers, picked for cost/speed tradeoff:

### 11.1 Backend unit (pytest, fast, mocked subprocess)

Add `pytest`, `pytest-asyncio`, and `httpx` (already a dep) to dev
deps in `pyproject.toml`. Tests live in `tests/` at the repo root.

`claude_runner.run_console_*` is mocked via a fake that emits canned
stream-json events; the goal is to exercise *our* orchestration code,
not the Claude CLI.

| Module under test | What we assert |
|---|---|
| `console_store` | meta.json round-trip; atomic `tokens` increment (read–modify–write under lock); `turns.jsonl` append-then-read; attachment SHA addressing; hardlink path + copy fallback when hardlink raises `OSError(EXDEV)` |
| `console_session` | per-session queue dispatcher runs in order; `queue_position` decrements; error path releases the lock; two sessions advance in parallel |
| API (FastAPI `TestClient`) | each of the 10 routes — auth required, 404s for unknown sid/turn_id, 409 on ask-after-archive, 400 on oversize / wrong-type attachment, 409 on 7th active session |
| SSE | `/ask/stream/{turn_id}` returns the right event sequence given a fixture progress log; reconnecting mid-stream replays from `ask.progress.jsonl` |
| Token math (§5) | table-driven: given a sequence of synthetic `result.usage` blobs, the last-turn formula returns the expected `pct_used`; `total_cost_usd` accumulates correctly across turns |

### 11.2 Backend health & watchdog (pytest, fast, fake subprocess)

The cancellation / recovery surface from §7 is testable without a
real Claude. Each scenario uses a fake `asyncio.subprocess` that the
test controls explicitly.

| Scenario | Expected outcome |
|---|---|
| Fake exits 0 after writing a `result` event | success turn appended; queue released |
| Fake exits non-zero with no `result` event | synthesized `subtype: "error"` turn; queue released; `text` mentions exit code |
| Fake stops emitting events for > 90s (clock injected) | watchdog sends SIGINT; on clean exit, error turn says "interrupted by watchdog"; on no exit within 30s, watchdog sends SIGKILL and the error turn says so |
| Fake runs past 10min wall-clock cap | watchdog SIGINTs; error turn cites cap |
| User-cancel: cancel endpoint hit while fake is running | SIGINT delivered; queue released after fake exits |
| Startup recovery: prep `turns.jsonl` with an unmatched user turn, run `console_session.recover()` | error assistant record synthesized; queue is clean |

### 11.3 Frontend component (vitest + @vue/test-utils, fast)

Add `vitest`, `@vue/test-utils`, and `jsdom` as devDependencies.
Tests live under `frontend/tests/`.

- **Token meter** — render `CompanyConsole.vue` (or a thin
  `<TokenMeter>` extracted from it) with mocked session state at
  74 / 75 / 89 / 90 / 91% used; assert color class, banner copy, and
  Send-button-disabled state.
- **Token-math helper** — pure function in a new
  `frontend/src/console.js`: `usageToMeter(usage) ⇒ {used, pct_free,
  color, banner_key}`. Table-driven tests, no DOM.
- **Queue badge** — render the transcript with an in-flight turn and
  two queued turns; assert position badges show "2" and "3" and
  decrement when the first completes.
- **Attachment client validation** — file picker stub rejects 11 MB
  files and `.svg` uploads with the right i18n key, mirroring the
  server's caps from §10.
- **i18n coverage check** — assert every `console.*` key referenced
  in components has both `en` and `zh` translations defined.

### 11.4 Real-Claude end-to-end (pytest, manual)

Marked `@pytest.mark.e2e`; skipped by default. Run via
`pytest -m e2e`. Expected cost ~$0.50 per run, wall time ~30s.

Documented in `README.md` as the canary for upstream `claude -p`
changes. Two tests:

1. **Happy path** — temp `data/` dir; create a company fixture with 2
   small markdown files of known content; `POST /console/sessions`
   with both include flags; tail the hydrate SSE to completion;
   `POST /ask` with a question whose answer is grounded in the
   fixtures; assert the assistant turn references a known phrase;
   `POST /archive`; tail the summary SSE; assert
   `meta.summary.bullets` is non-empty.
2. **Interrupt path** — same setup, but after `POST /ask` and the
   first streamed `claude_action` event, call the cancel endpoint
   and assert (a) an error turn is written within 5s, (b) the queue
   accepts a follow-up ask immediately, (c) that follow-up completes
   normally — proving the on-disk Claude session survived the SIGINT.

These are the contract tests for "drive Claude the same way a human
would from the command line." If `claude -p` changes its event shape
or its SIGINT behavior, these break first.

### 11.5 CI policy

- 11.1 + 11.2 + 11.3 run on every push (no Claude cost, < 30s wall).
- 11.4 is manual / pre-ship. README documents the command.
- No GitHub Actions / CI config is added by this design — the user
  can adopt whichever runner they prefer. The tests themselves are
  framework-portable.

---

## 12. Implementation phases

Each phase is its own commit on `main` (per `CLAUDE.md`). The app
stays runnable between phases. Tests land alongside the code that
introduces them — not as a separate "test phase" — so each commit is
shippable.

### Phase 1 — Backend + backend tests

- `server/console_store.py` — file-based session/turn/attachment
  storage. Pure-Python, no DB. With caps from §10.
- `server/console_session.py` — orchestration. Owns the per-session
  queue dispatcher, the watchdog, and the startup recovery sweep.
- `server/claude_runner.py` — add `run_console_hydrate`,
  `run_console_ask`, `run_console_summary` (drop
  `--no-session-persistence` for the first two).
- `server/skills/bsh_company_console.md` — analyst persona prompt.
- `server/api.py` — 10 endpoints under the existing api_router. SSE
  endpoints accept `?token=` for EventSource and replay from disk.
- `tests/` — set up pytest; add the 11.1 + 11.2 suites alongside the
  code they cover. The e2e suite (11.4) lands here too, gated by
  marker.

### Phase 2 — Frontend + frontend tests

- `frontend/src/components/CompanyConsole.vue` — tab strip + active
  session pane (token meter, transcript scroller, input area, Stop
  button when streaming).
- `frontend/src/components/ConsoleSessions.vue` — archived sessions
  dropdown + read-only transcript modal.
- `frontend/src/views/ResearchView.vue` — wrap existing content in a
  three-tab shell (Overview, Documents, Console).
- `frontend/src/api.js` + `frontend/src/console.js` — `console.*`
  methods + the `usageToMeter` helper. All HTTP routed through
  `request` / `apiFetch` / `withApiToken`, inheriting auth +
  root_path.
- `frontend/src/i18n.js` — EN + ZH keys.
- `frontend/tests/` — set up vitest + the 11.3 suite.

### Phase 3 — Polish

- Token thresholds (75/90) with banner and lock behavior.
- Queued-turn UI: pending cards with position badge; Stop button
  during streaming.
- Confirm-create modal with file list and cost estimate (estimate is
  a server-side helper that walks `included_file_ids` and sums page
  counts / sizes, returns `{tokens_est, cost_usd_est, duration_est_s}`).
- AI-rail polish: titles, click-to-tail behavior, end-of-job cost
  display.
- Auto-rename of session tab after first turn (LLM call against the
  first Q&A pair, cheap; uses `run_simple_structured` style). On
  failure, leave the timestamp title in place — no retry, no error
  surfacing.
- Tab-strip overflow: horizontal scroll with an "overflow ▾" menu
  when > 5 active tabs render in the available width.

Total effort estimate: 6–9 hours of focused work (was 4–6; the delta
is the test scaffolding and watchdog).

---

## 13. Out of scope (for v1)

These are deliberate omissions; revisit later if needed.

- **Editing past turns.** Once submitted, a turn is immutable. Resend
  to retry.
- **Branching the conversation.** No git-like "fork from turn N".
- **Cross-company sessions.** Each session is bound to one company.
- **Exporting the transcript.** Easy follow-up: "Download as .md".
- **Sharing sessions between users.** When per-user auth is wired,
  sessions stay private to the creating user.
- **Voice or audio inputs.** Text + image only.
- **Bulk-purge of archived sessions.** Manual `DELETE` only for v1.

---

## 14. Open questions resolved

These were settled in design discussion before / while this doc was
written. Recording here so they're not relitigated.

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
- Token-meter math: last-turn `input + cache_read + cache_creation`
  (§5). Not a cumulative sum — that would over-count.
- Concurrency: in-session = client queue + sequential `--resume`;
  cross-session = truly parallel (separate session files).
- Cancellation: SIGINT to the subprocess — same as a human Ctrl-C in
  `claude -p`. Watchdog handles silent / dead / hung subprocesses
  (§7).
- Recovery: startup sweep synthesizes error turns for any user turn
  with no matching assistant. Queued-but-unstarted turns do not
  survive restart.
- Resource caps: 10 MB / PNG-JPEG-WebP image attachments; 6 active
  sessions per company. (§10)
- Testing: pytest + vitest for unit/component coverage on every
  push; real-Claude e2e is manual only (§11).
- Worktrees: none — all work commits to `main` per `CLAUDE.md`.
