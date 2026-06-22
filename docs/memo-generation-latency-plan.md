# Memo generation latency — root cause & remediation plan

**Goal:** cut investment-memo runs from ~21 min (zainar baseline) toward ~7–8 min.

**Status:** plan approved (all three tiers; docx **JS** library as the standard
engine). Not yet implemented.

---

## Baseline: the zainar run (2026-06-22__093627)

Source data:
`data/memos/zainar-inc/2026-06-22__093627__zainar-inc__memo-run/logs/stream.jsonl`
(150 events) and report `data/reports/56f8b9daeab9.yaml`.

- Wall-clock: **1,258 s (21.0 min)**.
- Claude subprocess: **1,166 s** (`claude_duration_ms`), cost **$5.89**.

### Phase breakdown (derived from inter-event gaps)

| Step (serial) | window | duration |
|---|---|---|
| Setup + tooling discovery + 14 analysis passes | 0 → 440 s | **7.3 min** |
| EN memo (build_memo.py + memo_content.py) | 440 → 790 s | **5.8 min** |
| ZH memo (memo_content_zh.py) | 790 → 990 s | **3.3 min** |
| Build + validate + render + finalize | 990 → 1258 s | **4.5 min** |

No single step is pathological (~5–8 min each). The 21 minutes is the **sum of
four serial steps that never overlap.**

---

## Root cause

The memo runs as **one `claude -p` subprocess** with tools
`Read,Write,Edit,Bash,Grep,Glob` — the **Task/subagent tool is not enabled**
(`server/claude_runner.py:2208`). A single subprocess has exactly **one token
decode stream**, so:

1. **Everything is authored token-by-token in that one stream.** The run produced
   ~116 KB / ~29 K tokens of *final* artifacts — 14 analysis `.md` files **+** a
   hand-written 15 KB `build_memo.py` renderer **+** a 32 KB `memo_content.py`
   (EN) **+** a 17 KB `memo_content_zh.py` (ZH) **+** `run_build.py` — before
   counting thinking blocks and rewrites. At Opus decode rates this alone is
   ~10+ min; with thinking and discovery thrash it lands at ~19 min of model time.

2. **Steps physically cannot overlap.** One process = one decoder. The "12
   parallel threads" in the UI are just filename labels
   (`server/claude_runner.py:354`, `:1842`), not real concurrency. Even "parallel
   tool calls" would not help here, because the bottleneck is the model *writing
   content*, not the tools *executing*.

### Two compounding problems

- **The run went off-script.** The skill says *"use the docx JavaScript library…
  at `.claude/skills/docx/SKILL.md`"* (`server/skills/bsh_investment_memo_latestage.md:1041`).
  On this machine **none of that exists**: no `~/.claude/skills/docx`, no `docx`
  npm package (not local, not global), no repo `package.json`. So the agent spent
  **~3.5 min** probing the filesystem (including a ~127 s runaway
  `find /Users/rparker -maxdepth 6`) and then **improvised a python-docx
  pipeline**, hand-authoring a 15 KB renderer from scratch.
- **EN→ZH is fully serial by design** (`…latestage.md:1043`: "Finish the English
  memo first… then translate"), and ZH adds ~17 KB of generated content.

**The only two real levers:** (A) generate far fewer tokens, and (B) split into
multiple subprocesses for genuine parallel decode streams.

---

## Plan

Standard engine: **docx JS library** (per decision). This means Tier 1 must first
*actually provision* the JS toolchain — it is exactly what was missing.

### Workstream A — Provision the JS docx toolchain (Tier 1, prerequisite)

*Without this, every run repeats the 3.5-min hunt and the Python fallback.*

1. Create **`server/memo_builder/`** in the repo:
   - `package.json` pinning `docx` (+ CJK-safe font setup), with `node_modules/docx`
     installed and vendored/committed so it lives at a fixed absolute path.
   - **`build_memo.mjs`** — a generic, committed JS renderer (palette, TOC, tables,
     headers/footers, page numbers, CJK fonts) that takes a content JSON and emits
     a `.docx`. The agent must `import`-and-call this, never re-author it.
2. In `server/claude_runner.py` (~2037–2122, the operational prompt header):
   inject the **absolute path** to `build_memo.mjs` and the `docx` install, plus an
   explicit rule: *"docx tooling is at `<path>`; do NOT search the filesystem
   (`find`/`npm ls`/`fc-list`) for it."*
3. Rewrite the skill's Step 3 (`server/skills/bsh_investment_memo_latestage.md`
   ~1037–1056) to point at the committed builder instead of the nonexistent
   `.claude/skills/docx/SKILL.md`.

**Saves ~5–7 min** (3.5 min discovery + ~2–3 min not re-authoring the renderer).

### Workstream B — Content as data, rendering out of the model (Tier 2)

4. Define a content schema; the agent writes only compact **`content_en.json`** /
   **`content_zh.json`** (META, TOC, BLOCKS, APPENDIX) — no Python/JS literals, no
   `build_memo.py`, no `run_build.py`.
5. **Move docx render + validate + preview into the deterministic orchestrator**
   (Python invoking `node build_memo.mjs`). The model stops spending tokens on
   rendering, validation scripts, and `qlmanage` orchestration; these become fixed
   pipeline steps. Also removes the ~90 s PDF-preview tail from the model's
   critical path.

**Saves ~3–5 min** (smaller payloads + zero model time on render/validate scaffolding).

### Workstream C — Parallel decode streams (Tier 3)

6. In `server/memo_analysis.py` / `server/claude_runner.py`, split authoring across
   **two coordinated subprocesses**:
   - **P1:** analysis passes + synthesis → `content_en.json`.
   - **P2:** spawned the moment `content_en.json` exists → translate →
     `content_zh.json` (expensive ZH generation now overlaps with EN docx render +
     EN validation instead of waiting for them).
   - Orchestrator renders both `.docx` via the committed JS builder after each JSON
     lands.
7. Merge the two progress streams via `server/run_ledger.py` /
   `server/job_progress.py` so the UI shows one coherent timeline; update
   recovery/stale-run handling for two PIDs.

**Saves ~3–5 min** (true overlap of the two largest generation steps — the only
way to beat the single-stream limit while the Task tool is disabled).

---

## Sequencing, risk, validation

- **A → B → C.** A is low-risk and independently shippable (biggest risk-adjusted
  win). B is medium-risk (schema + orchestrator render path). C is the largest
  change (multi-process coordination, progress merging, recovery).
- Validate after each workstream by re-running a memo and diffing the new
  `stream.jsonl` phase breakdown against the zainar baseline above (the analysis is
  repeatable from the inter-event gaps).
- Per `CLAUDE.md`, all work lands directly on `main`.

### Projected wall-clock

| After | Target |
|---|---|
| Baseline | ~21 min |
| Workstream A | ~13–15 min |
| Workstream A + B | ~9–11 min |
| Workstream A + B + C | ~7–8 min |
