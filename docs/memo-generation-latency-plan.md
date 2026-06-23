# Memo generation latency and quality hardening handoff

**Purpose:** context transfer for a future session. The original latency plan
targeted a nonexistent JS `docx` toolchain. Current `main` has moved to a
tracked Python renderer instead. Treat this document as the current plan of
record.

**Current status:** the major latency and reliability change is implemented.
Claude authors memo judgment and `logs/memo_package.json`; Python validates the
package and renders both DOCX files through `server.memo_docx_renderer`.
Progress hardening is also in place: the runner now exposes initial source
intake as `Phase 1 - Intake and setup`, pre-populates the later memo phases as
`not_started` rows in the same expandable task window, embeds the resolved
company registry entry so Claude does not have to hunt through `companies.yaml`,
blocks Task/ToolSearch scaffolding tools for memo runs, and maps optional
synthesis artifacts into the same per-flow progress UI. Phase 1 carries a
150-second estimate so the UI can show that setup usually takes about 2m 30s.

**Last verified command:**

```bash
PYTHONPATH=. pytest -q tests/test_memo_docx_renderer.py tests/test_memo_analysis.py tests/test_memo_prep.py tests/test_serena_analysis.py
```

At handoff this passed with 74 tests and only existing FastAPI deprecation
warnings. After the Phase 1 progress/intake hardening, the same command passed
with 94 tests and the same existing FastAPI deprecation warnings.

---

## Current Implementation Context

Important files:

- `server/claude_runner.py`
  - The memo prompt tells Claude to write `logs/memo_package.json`.
  - Claude is explicitly told not to run `python -m server.memo_docx_renderer`
    and not to write final `.docx` files.
  - The prompt requires core section ids, bilingual block/table/source
    treatment text, and a non-empty source list.

- `server/memo_analysis.py`
  - Normal runs and stale-run recovery both call `_render_memo_outputs()`.
  - `_render_memo_outputs()` calls `memo_docx_renderer.render_memos()`.
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
    - missing Chinese translations for final user-facing text
    - missing sources

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

## Remaining Tightening Work

These are the next high-value changes. They are intentionally smaller than the
completed renderer handoff and should be safe to do directly on `main`.

### 1. Add A Content Floor To `validate_package()`

Problem:

`validate_package()` currently requires each core section to have non-empty
`blocks`, but a section can still be structurally valid while carrying no useful
memo content. Examples that may pass today:

- a core section with only `spacer`
- a core section with only headings
- a single generic sentence such as "More diligence is needed"
- an empty-looking table with headers but no real rows

Implementation direction:

- Add a helper in `server/memo_docx_renderer.py`, probably near
  `_validate_block()`:
  - `_block_content_score(block) -> dict`
  - or `_has_real_content(block) -> bool`
- Count real content as:
  - paragraph/callout body text with meaningful length
  - bullet items with meaningful length
  - table rows with at least one non-empty body row
  - callout items
- Do not count:
  - `spacer`
  - headings alone
  - title-only callouts
  - title-only tables

Suggested acceptance floor:

- Every required core section must contain at least one real content block.
- `executive_summary` should contain either:
  - at least two real content blocks, or
  - one real paragraph plus one table/callout.
- `investment_highlights` and `investment_risk` should each contain at least
  two real bullets, or one substantive table/callout plus explanatory prose.
- `financial_forecast_valuation` should include a real paragraph or table that
  references model treatment, scenario ranges, valuation, revenue, margins,
  or diligence thresholds.

Tests to add:

- `test_renderer_rejects_heading_only_required_section`
- `test_renderer_rejects_spacer_only_required_section`
- `test_renderer_rejects_table_with_headers_but_no_rows`
- `test_renderer_accepts_substantive_required_sections`

### 2. Add Chinese/English Parity And Native-Chinese Quality Checks

Problem:

The package validator now requires Chinese text, but it does not prove that:

- the Chinese memo has the same analytical structure as English;
- the rendered Chinese DOCX has actual CJK text in core sections;
- the Chinese reads like fluent professional Chinese rather than stiff
  translationese;
- important deal terms are consistently localized.

Implementation direction:

- Add a lightweight post-render check in `server/memo_analysis.py`, after
  `_render_memo_outputs()` and before the English quality gate, or add a helper
  in a new small module if it grows.
- Use `python-docx` extraction, similar to `memo_quality_lint.py`.
- Compare the English and Chinese rendered documents:
  - section heading count
  - table count
  - callout-like table count if easy to detect
  - source/fact-reference section presence
  - approximate paragraph count range
- Check the Chinese document:
  - contains CJK characters in every required core section;
  - does not contain large English-only body paragraphs outside names, tickers,
    dates, units, and source titles;
  - does not contain prompt-scaffold artifacts translated literally.

Suggested failure model:

- P0: missing Chinese core section, missing CJK in core section, materially
  different table count, missing source section.
- P1: suspiciously low CJK ratio, excessive English in body prose, repeated
  translationese markers.

Tests to add:

- `test_chinese_parity_passes_for_renderer_output`
- `test_chinese_parity_fails_when_zh_section_missing`
- `test_chinese_parity_fails_when_zh_has_no_cjk_body`
- `test_chinese_parity_fails_when_table_counts_diverge`

#### Chinese Memo Guidance For Prompt And Review

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

### 3. Add Package Hash And Renderer Version Traceability

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

### 4. Clean Up Stale Failure Wording

Problem:

`server/memo_analysis.py` still has a fallback missing-output message that says:

> Skill finished but the expected output files are missing...

With Python-owned rendering, this should say renderer/server, not skill. This is
mostly diagnostic hygiene, but it matters when a production run fails.

Implementation direction:

- Update the message around the post-render existence check in
  `server/memo_analysis.py`.
- The post-render existence check may now be redundant because
  `_renderer_contract_errors()` already checks outputs. Keep it if useful as a
  defensive check, but make the text accurate.

Test to add or update:

- If no direct test exists for that fallback, add one only if easy. Otherwise a
  small wording-only change is acceptable.

---

## Suggested Sequencing

1. Content floor in package validation.
2. Chinese/English parity checks.
3. Package hash and renderer version traceability.
4. Stale wording cleanup.

Run after each slice:

```bash
PYTHONPATH=. pytest -q tests/test_memo_docx_renderer.py tests/test_memo_analysis.py tests/test_memo_prep.py tests/test_serena_analysis.py
python -m py_compile server/memo_docx_renderer.py server/memo_analysis.py server/claude_runner.py server/docx_pdf.py
```

Do not create branches or worktrees for this repo. Per `AGENTS.md`, all work
happens directly on `main`.
