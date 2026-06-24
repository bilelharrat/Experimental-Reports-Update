# Memo generation latency and quality hardening handoff

**Purpose:** context transfer for a future session. The original latency plan
targeted a nonexistent JS `docx` toolchain. Current `main` has moved to a
tracked Python renderer instead. Treat this document as the current plan of
record.

**Current status:** the major latency and reliability change is implemented.
The default memo path now produces `logs/memo_package.json` through a fast
multi-subprocess pipeline; Python validates the package and renders both DOCX
files through `server.memo_docx_renderer`.
Progress hardening is also in place: the runner now exposes initial source
intake as `Phase 1 - Intake and setup`, pre-populates the later memo phases as
`not_started` rows in the same expandable task window, embeds the resolved
company registry entry so Claude does not have to hunt through `companies.yaml`,
blocks Task/ToolSearch scaffolding tools for memo runs, and maps optional
synthesis artifacts into the same per-flow progress UI. Phase 1 carries a
150-second estimate so the UI can show that setup usually takes about 2m 30s.

The default runtime path now uses real parallelism for independent memo
analysis:

- `BSH_MEMO_FAST_PIPELINE` defaults to enabled. With no approved Memo Studio
  packet, Python runs eight narrow Claude analysis subprocesses in parallel
  (bounded by `BSH_MEMO_FAST_MAX_WORKERS`, default `4`), writes compact
  `analysis/*.md` artifacts plus `analysis/fast/*.json`, then runs one English
  synthesis/package subprocess and one Chinese package-completion subprocess.
- `BSH_MEMO_FAST_PIPELINE=0` restores the legacy single-Claude skill run for
  quality comparison or emergency fallback.
- Approved Memo Studio sessions are the fastest path: the memo runner skips
  the eight analysis subprocesses and uses the approved packet as primary
  synthesis input.

The default runtime path also treats two expensive conveniences as opt-in:

- `BSH_MEMO_RENDER_PDF_PREVIEWS=1` enables Word/AppleScript PDF previews for
  the English and Chinese DOCX outputs. Without it, the run completes after the
  DOCX, parity, and quality gates pass, and the UI simply omits preview links.
- `BSH_MEMO_GENERATE_INTERNAL=1` enables the separate internal diligence memo
  Claude pass. Without it, the LP-facing memo becomes ready without waiting for
  a second Claude subprocess.

This keeps the critical path focused on the sell-side memo deliverables:
parallel analysis or approved packet synthesis, English source package,
Chinese-completed `memo_package.json`, English DOCX, Chinese DOCX, Chinese
parity gate, and English quality gate.

**Last verified commands:**

```bash
python -m py_compile server/claude_runner.py server/memo_analysis.py
python -m pytest tests/test_memo_analysis.py tests/test_memo_prep.py tests/test_serena_analysis.py tests/test_memo_quality_lint.py
```

Latest run passed with 126 tests and only existing FastAPI `on_event`
deprecation warnings.

---

## Current Implementation Context

Important files:

- `server/claude_runner.py`
  - Fast-path helpers run compact JSON analysis passes, English package
    synthesis, and Chinese package completion.
  - The legacy memo prompt tells Claude to write `logs/memo_package.json`.
  - Claude is explicitly told not to run `python -m server.memo_docx_renderer`
    and not to write final `.docx` files.
  - The prompt requires core section ids, bilingual block/table/source
    treatment text, and a non-empty source list.

- `server/memo_analysis.py`
  - `_run_fast_memo_pipeline()` is the default path. It emits `phase_timing`
    events for the full fast pipeline, parallel analysis, each pass, English
    package synthesis, and Chinese package completion.
  - `BSH_MEMO_FAST_MAX_WORKERS` controls bounded analysis-pass parallelism.
  - Normal runs and stale-run recovery both call `_render_memo_outputs()`.
  - `_render_memo_outputs()` calls `memo_docx_renderer.render_memos()`.
  - `_maybe_render_memo_pdf_previews()` skips Word PDF conversion unless
    `BSH_MEMO_RENDER_PDF_PREVIEWS=1`.
  - Internal diligence generation is skipped unless
    `BSH_MEMO_GENERATE_INTERNAL=1`.
  - Approved Memo Studio sessions skip the fast analysis fan-out and enter
    packet-first synthesis/package generation.
  - `_renderer_contract_errors()` verifies:
    - `logs/memo_package.json`
    - English and Chinese DOCX outputs
    - `logs/validation.txt`
    - `logs/validation_cn.txt`
    - `logs/file_inventory.md`
    - `logs/run_manifest.md`
    - manifest contains `server.memo_docx_renderer`
    - manifest contains `validation_status: passed`
  - Generated renderer scripts such as `build_memo.py` are blocked in both the
    normal path and stale-run recovery.

- `server/memo_docx_renderer.py`
  - Owns DOCX generation, validation logs, inventory, and manifest finalization.
  - `validate_package()` rejects:
    - unsupported schema version
    - missing `company.name`
    - missing required core sections
    - empty section block lists
    - unsupported block types
    - required sections without substantive content
    - missing Chinese translations for final user-facing text
    - missing sources

- `server/memo_chinese_parity.py`
  - Checks English/Chinese rendered DOCX parity after rendering.
  - Blocks missing Chinese core sections, missing CJK body text, material
    table-count divergence, and prompt-scaffold Chinese artifacts.

- `server/memo_quality_lint.py`
  - Runs a hard P0 quality gate on the English source-of-truth DOCX.
  - It catches source-token leaks, internal artifact names, scaffold labels,
    banned fuzzy phrases, em dash bridge punctuation, and untreated disclosure
    gaps.

- `tests/test_memo_docx_renderer.py`
  - Covers renderer output, generated-renderer script detection, required
    sections, Chinese translations, unsupported block types, and sources.

- `tests/test_memo_analysis.py`
  - Covers package rendering in normal runs, missing package failure, generated
    renderer blocking, stale-run recovery rendering, and stale-run generated
    renderer blocking.

---

## Implemented Quality Gates

The renderer now rejects structurally valid but empty memo packages. Required
core sections need substantive content, not only headings, spacers, title-only
callouts, title-only tables, or generic filler. Existing tests cover
heading-only sections, spacer-only sections, empty tables, and valid
substantive sections.

The Chinese parity gate now runs after DOCX rendering and before the English
quality gate. It checks rendered English/Chinese structure and CJK body
presence, and fails closed on missing Chinese core sections, missing CJK body
text, material table-count divergence, and prompt-scaffold Chinese artifacts.

### Chinese Memo Guidance For Prompt And Review

The Chinese memo should be a native professional investment memo, not an
English memo mirrored word-for-word. It must preserve the same claims,
evidence, caveats, order, tables, and gating questions, while using natural
Chinese for a Chinese-speaking investment audience.

Principles:

- **Analytical parity first.** The Chinese memo must express the same
  recommendation, confidence level, risks, valuation posture, and diligence
  thresholds as English. It may reorder words for Chinese fluency, but not
  change the substance.
- **Native professional register.** Use fluent investment Chinese suitable for
  an IC memo. Prefer concise, direct phrasing over literal translation.
- **No prompt jargon.** Do not translate internal scaffolding such as
  "present-state", "upside-state", "Critical Reality Check", "source traces",
  "memo packet", "reviewer prompt", or "claim register" into visible memo
  prose.
- **No mechanical English syntax.** Avoid sentence shapes that sound like
  English with Chinese words substituted. Use Chinese topic-comment structure
  and natural connective phrasing where appropriate.
- **Consistent deal vocabulary.** Use stable terms across the memo.

Recommended vocabulary patterns:

- investment memo: `投资备忘录`
- investment highlights: `投资亮点`
- investment risks: `投资风险`
- executive summary: `执行摘要`
- gating questions: `关键尽调问题` or `核心尽调问题`
- diligence threshold: `尽调门槛`
- source class: `来源类别`
- model treatment: `模型处理方式`
- revenue recognition: `收入确认`
- unit economics: `单位经济模型`
- gross margin: `毛利率`
- deployment depth: `部署深度`
- repeatable production use: `可重复的生产环境使用`
- customer concentration: `客户集中度`
- scenario range: `情景区间`
- valuation support: `估值支撑`
- downside protection: `下行情景保护`
- pass trigger / kill criterion: `放弃投资的触发条件`

Avoid or rewrite:

- `硬 IP 墙` unless describing a legal/IP barrier with precise meaning. Prefer
  `知识产权壁垒尚未形成可验证防线` or the specific mechanism.
- `上行状态` / `现态` as literal translations of prompt labels. Prefer
  `乐观情景`, `当前已验证部分`, or a direct sentence.
- `软工具` / `软性工具` for "soft instrument". Prefer the exact instrument or
  `约束力有限的协议安排`.
- `叙事` when the point is evidence. Prefer `投资判断`, `证据链`, `商业验证`,
  or `承销假设`.
- Long strings of nominalized nouns. Break into clear investment judgments.

Good Chinese output should sound like:

- `BSH 应将本轮视为有条件推进的机会：现有部署已经证明产品具备落地可能，但收入确认、毛利率路径和客户复购深度仍需在尽调中验证。`
- `估值承销不应直接采用管理层口径，而应以已确认收入、可重复部署数量和毛利率改善路径建立保守情景区间。`

Bad Chinese output to reject:

- `本部分展示当前状态与上行状态之间的关键现实检查。`
- `该公司拥有硬 IP 墙和强源追踪，因此应进行上行案例。`
- `根据 memo_packet 和 chart_specs，投资亮点如下。`

## Remaining Tightening Work

These are intentionally smaller than the completed renderer handoff and fast
pipeline changes, and should be safe to do directly on `main`.

### 1. Add Package Hash And Renderer Version Traceability

Problem:

The run manifest says `server.memo_docx_renderer`, but it does not record the
exact package hash or renderer version. That makes auditing and stale-run
diagnosis harder.

Implementation direction:

- Add `RENDERER_VERSION = 1` to `server/memo_docx_renderer.py`.
- Compute `memo_package_sha256` from the raw JSON file bytes before rendering.
- Add the hash and renderer version to:
  - `logs/run_manifest.md`
  - `logs/file_inventory.md`
  - the report record via `storage.update_report()`, probably from
    `server/memo_analysis.py` after successful render.
- Consider returning the hash from `render_memos()` so callers do not duplicate
  logic.

Tests to add:

- renderer unit test asserts manifest includes `memo_package_sha256` and
  `renderer_version`;
- memo analysis test asserts the report record gets `memo_package_sha256`.

### 2. Run Real-Run Timing Calibration

The fast path is now instrumented with `phase_timing` events, but production
wall-clock targets should be measured on real memo runs. Compare:

- approved-packet mode, which skips analysis fan-out;
- normal fast mode with `BSH_MEMO_FAST_MAX_WORKERS=4`;
- normal fast mode with `BSH_MEMO_FAST_MAX_WORKERS=8`;
- legacy mode with `BSH_MEMO_FAST_PIPELINE=0` for quality and latency baseline.

Run after each future slice:

```bash
python -m py_compile server/claude_runner.py server/memo_analysis.py server/memo_docx_renderer.py server/docx_pdf.py
python -m pytest tests/test_memo_docx_renderer.py tests/test_memo_analysis.py tests/test_memo_prep.py tests/test_serena_analysis.py tests/test_memo_quality_lint.py
```

Do not create branches or worktrees for this repo. Per `AGENTS.md`, all work
happens directly on `main`.
