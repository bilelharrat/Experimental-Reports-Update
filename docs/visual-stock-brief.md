# Visual Stock Brief — design & prototype plan

A bilingual (English + 简体中文), magazine-grade, multi-page **visual
report for public stocks** (AMD, NVDA, AMZN, …). Visual language inspired
by the WeChat "一天吃透一条产业链" infographic decks (dense, colorful,
strong hierarchy, real charts, one punchline per page) and the
`AlphaSense Visual Memo` HTML deck (dark fintech aesthetic, A4 page deck,
verdict / waterfall / scenario components) — but with **richer content**
and **every chart/diagram code-generated and rasterized to PNG at maximum
quality**.

Locked decisions (from the kickoff):

1. **All data visuals are code-driven.** Every chart, diagram, donut,
   waterfall, matrix is SVG/HTML/CSS composed by deterministic code,
   rendered to crisp PNG (and print PDF). "Max quality" = vector
   components rasterized at high device-scale-factor. **Supporting
   imagery** (atmospheric hero / section art that carries *no data*) is
   a separate, optional, bounded additive layer — see §4.
2. **First target is an offline prototype harness**, not in-app. A CLI
   takes a ticker → emits a versioned deck into `data/`. App integration
   is explicitly deferred until the quality bar is cleared.
3. **Content comes from a new dedicated deep-research pass** (not the
   existing `trader_snapshot`). Purpose-built bilingual narrative +
   structured chart-data JSON.

Per repo rules: the research pass runs **only** through
`claude_runner` (`claude -p` subprocess, stream-json, progress events) —
no direct OpenAI/Anthropic SDK. Work happens on `main`.

---

## 1. Three-layer architecture

```
TICKER ──▶  [1] RESEARCH LAYER  ──▶ brief.json  ──▶  [2] RENDER LAYER  ──▶ pages/*.png
                (Claude, slow,        (frozen           (deterministic,      brief-*.pdf
                 non-deterministic,    typed             zero-cost,           brief.html
                 cached/frozen)        contract)         golden-testable)
                                                              │
                                          [3] HARNESS + EVAL LAYER
                                          (CLI orchestration, automated
                                           visual QA, critique loop,
                                           golden snapshots)
```

The split is the whole strategy. Research is expensive and
non-deterministic, so we run it ~3 times during prototyping and **freeze
the JSON as a fixture**. Rendering is deterministic and free, so we can
iterate the visual design hundreds of times against the frozen fixture
with golden-file regression safety. Eval automates the "is it awesome
yet" judgment so we are not eyeballing every run.

---

## 2. The brief data model (the contract between layers)

A strict `BRIEF_SCHEMA` (JSON-schema, enforced on the Claude call exactly
like `companies_ai_public.py` does). One brief = an ordered list of
**typed pages** drawn from a page catalog. The research pass chooses
which pages apply to the company and fills them; numbers are nullable and
**never invented** (null over guess — same convention as the trader
snapshot), and every figure carries provenance.

Every page object shares a frame:

```jsonc
{
  "page_type": "revenue_bridge",
  "kicker":   { "en": "04 · Growth quality", "zh": "04 · 增长质量" },
  "headline": { "en": "...punchline...",       "zh": "...金句..." },
  "dek":      { "en": "one-sentence sub",      "zh": "一句话副标题" },
  "viz":      { "kind": "waterfall", /* typed payload, see §2.2 */ },
  "footer":   { "en": "...", "zh": "..." },
  "sources":  [ { "label": "AMD 10-Q Q1'26", "url": "https://..." } ]
}
```

### 2.1 Page catalog (~10–14 pages; research pass selects)

| # | page_type | Story (WeChat / AlphaSense analog) | Primary viz |
|---|---|---|---|
| 1 | `cover_verdict` | Thesis + posture in one breath | `hero` + `metric_quad` |
| 2 | `the_tape` | Price action / momentum / rel-strength | `area_chart` |
| 3 | `why_it_moves` | The 3–5 structural business drivers (产业链 angle) | `donut` + `grouped_bars` |
| 4 | `revenue_bridge` | PY revenue → segment deltas → current | `waterfall` |
| 5 | `unit_economics` | Margin story / "real cost vs price" (SpaceX 1/6 analog) | `grouped_bars` |
| 6 | `moat_integration` | Own vs license vs commodity; vertical integration | `pyramid` + `matrix` |
| 7 | `supply_chain` | Tier-2 suppliers, single-point risk, customer concentration (SpaceX 二级供应商 analog) | `matrix` |
| 8 | `competitive_field` | Replacement vs coexistence | `matrix` + `score_donut` |
| 9 | `catalysts` | Next ~4 dated events, impact-weighted | `timeline` |
| 10 | `sentiment` | Analyst dist, target dispersion, short interest, skew, insiders | `metric_quad` + `grouped_bars` |
| 11 | `scenario_math` | Bear / base / bull → revenue, multiple, implied value, return | `scenario_set` |
| 12 | `risk_gates` | What would change our mind (SpaceX 工程冗余 / AlphaSense six-gates analog) | `gate_grid` |
| 13 | `sources` | Every figure's provenance | `source_table` |

### 2.2 `viz` discriminated union (the component contract)

Each `kind` is a strongly-typed payload the render layer maps 1:1 to a
component. Examples:

- `area_chart`: `series: [{x, y}]`, `bands?`, `markers?`, `unit`,
  `baseline?`.
- `donut`: `slices: [{label_{en,zh}, value, accent}]`, `center_{en,zh}`.
- `waterfall`: `start{label,value}`, `steps:[{label,value,kind:
  base|add|subtract|acquired}]`, `end{label,value}`.
- `grouped_bars`: `groups:[{label}]`, `series:[{name, values[]}]`, `unit`.
- `pyramid`: `tiers:[{label_{en,zh}, strength, note_{en,zh}}]`.
- `matrix`: `cols`, `rows`, `cells:[{text_{en,zh}, weight}]` (the
  SpaceX supplier-tier grid pattern).
- `timeline`: `nodes:[{date, label_{en,zh}, impact, note_{en,zh}}]`.
- `scenario_set`: `bear|base|bull` each `{moic, rows:[{k,v}]}`.
- `score_donut`: `score`, `out_of`, `caption_{en,zh}`.
- `metric_quad`: 4 × `{label_{en,zh}, value, note_{en,zh}, tone}`.
- `gate_grid`: `gates:[{n, title_{en,zh}, body_{en,zh}}]`.
- `hero`: `signature` ("orbit" | "price_arc" | "constellation"),
  `core_{en,zh}`, `tags`.

**Bilingual is field-level, not render-time.** Both languages come from
the research JSON. The render layer never machine-translates. To keep
layout stable across locales the research prompt is given **hard
max-character budgets per field** (e.g. headline ≤ 64 EN / ≤ 30 CJK),
so EN and ZH pages share geometry instead of being auto-shrunk to fit.

---

## 3. Render layer (deterministic, max-quality PNG)

**Recommended toolchain: headless Chromium (Playwright) over HTML/CSS +
hand-built inline SVG charts.** Rationale:

- The target aesthetic is already CSS (the AlphaSense deck proves it):
  gradients, glass panels, fine typography, print geometry.
- Chromium rasterizes at arbitrary `deviceScaleFactor` → genuinely crisp
  PNG, and `page.pdf()` gives a free vector print deck.
- Charts are **hand-written SVG path generators** (no charting lib) so
  every pixel is controlled and the output is reproducible.

Python-only fallback (if we want zero Node): `svgwrite` + `resvg`/
`cairosvg` → PNG. Noted as a fallback; Chromium is the recommendation.

Render contract:

- **Design tokens in one file** — palette, type scale, spacing, page
  geometry (e.g. `1240×1754` logical @ `scale=3` → ~3720×5262 PNG; plus
  an optional `1080×1350` social variant).
- **One parametric component per `viz.kind`.** Pure function of
  `(payload, locale, tokens)`. No data fetching, no LLM.
- **Bundled CJK font** (Noto Sans SC) so 中文 never renders tofu.
  Per-locale typographic rules (line-height, no `letter-spacing` on
  CJK).
- **Render twice** (`locale=en`, `locale=zh`) from the same model.
- **Outputs** per run: `brief.html` (live deck), `pages/en/page-NN.png`,
  `pages/zh/page-NN.png`, `brief-en.pdf`, `brief-zh.pdf`.

---

## 4. Supporting-image prompt craft (optional additive layer)

Code/SVG owns everything that carries a number. **Supporting images** are
the magazine-grade atmospheric art that makes a page feel art-directed
rather than dashboard-y — a stylized EUV lithography close-up behind the
AMD cover, an abstract datacenter lattice on the NVDA moat page, a
logistics-web texture on the AMZN supply-chain divider. They are
**decorative, never informational**, and the whole deck must look like
one art director made it, not a stock-photo grab bag.

### 4.1 Hard constraints (these are non-negotiable)

- **Zero text, zero data in generated raster.** No words, numbers,
  charts, axes, logos, tickers, faces, real product likenesses, UI. Text
  and data live only in the code/SVG layer on top. (Image models garble
  text and would also violate the truthfulness rule.)
- **Bilingual by being language-free.** One image serves both EN and ZH
  because it contains no glyphs. This is why the no-text rule is
  structural, not stylistic.
- **Additive, never load-bearing.** A page must be fully legible and
  on-brand with the image *absent*. Missing/failed/QA-rejected image →
  graceful fallback to a code-drawn gradient/texture in the slot. Images
  never block the deck.
- **Routed through an approved generation path**, produced as a
  *separate cached asset step* (cache key = `hash(prompt + seed + model +
  params)` under the run folder). No direct third-party SDK calls
  sneaked into the render layer — same governance rule as the research
  pass.
- **Reproducible.** The full prompt, negative prompt, seed, model, and
  params are stored **as data in `brief.json`** next to the page that
  uses them, so any run re-creates byte-identically.

### 4.2 The prompt is built, not written — a three-part template

A great prompt here is a *parametric build*, not freeform prose:

```
PROMPT  =  STYLE_CAPSULE   (fixed code constant — the house style)
         + SUBJECT         (authored by Claude from page semantics)
         + COMPOSITION      (from the slot's layout role)
         + NEGATIVES        (fixed code constant)
```

- **`STYLE_CAPSULE` — the consistency lock.** One verbatim block reused
  on *every* image so the deck is visually coherent. Pin: medium
  ("cinematic 3D render, shallow depth of field" or "matte editorial
  illustration" — pick one and never mix within a deck), palette tied to
  the design tokens (the same deep-navy / cyan / violet family as the
  fintech theme, named by hex intent: "ink-navy background, electric-cyan
  rim light, violet accent bloom"), lighting ("single cool key, soft
  volumetric, deep falloff to black"), material/texture, lens ("85mm,
  f/1.8" or "wide 24mm"), grade ("filmic, low-saturation, fine grain"),
  mood ("quiet, precise, expensive"). This block is the single biggest
  lever — lock it before generating anything.
- **`SUBJECT` — authored from the page's meaning.** This is the part
  Claude (the research/critique pass) writes, because it knows the
  narrative. Map company/segment to a *concrete, specific* metaphor from
  a maintained bank, not a cliché:
  - AMD → silicon wafer / EUV lithography optics / chiplet packaging
    macro.
  - NVDA → GPU die topology / liquid-cooled rack corridor / abstract
    CUDA-grid field.
  - AMZN → fulfilment-lattice / logistics web / multi-region cloud
    topology.
  Be concrete ("a single 300mm wafer catching cyan rim light, extreme
  macro, out-of-focus fab background") and **ban the clichés explicitly**
  (no glowing brains, no generic blue circuit boards, no upward stock
  arrows, no rocket-to-the-moon, no robotic handshake).
- **`COMPOSITION` — derived from the slot's layout role.** The image
  exists under live text and charts, so the prompt must *engineer
  negative space*: aspect ratio exact to the slot; subject pushed to one
  third; a deliberate clean, low-detail dark gradient region where the
  headline/dek/quad sits ("subject lower-right, upper-left two-thirds an
  empty dark gradient with no detail, reserved for text overlay"). Cover
  hero, section band, and full-bleed divider each get their own
  composition preset.
- **`NEGATIVES` — fixed.** "no text, no letters, no numbers, no logos,
  no watermark, no UI, no charts, no human faces, no brand likeness,
  no clutter, no busy background, no oversaturation, no lens flare
  kitsch."

### 4.3 Generation & selection loop (fits the Phase-1 gallery)

- Generate **3–4 seeds per slot**; vary only the SUBJECT clause across a
  small A/B set, never the STYLE_CAPSULE.
- The same Phase-3 **vision-critique pass** scores each candidate against
  the style capsule on: on-brand consistency, overlay-safe negative
  space actually present, zero text/artifact contamination, metaphor
  aptness, no uncanny/garbled regions. Auto-rank, keep the winner.
- Log the winning prompt+seed as **golden** alongside the component
  goldens. Regressions in art are caught the same way as layout
  regressions.
- A page-level check: composite the winning image *under the real text/
  charts* and re-score legibility — the image is only "good" in context,
  never in isolation.

### 4.4 Worked example (NVDA moat page, section-band slot)

```
[STYLE_CAPSULE] Cinematic 3D product render, single cool key light,
  soft volumetric haze, deep falloff to near-black; ink-navy base,
  electric-cyan rim light, restrained violet accent bloom; 85mm f/1.8,
  filmic low-saturation grade, fine film grain; mood: quiet, precise,
  expensive.
[SUBJECT] Extreme-macro abstraction of a GPU die's interconnect
  topology — fine parallel copper traces fanning into darkness, one
  cyan-lit ridge in sharp focus, the rest dissolving to bokeh; cold
  industrial, no symbology.
[COMPOSITION] 16:9, subject anchored lower-right third, upper-left
  two-thirds a smooth detail-free dark gradient reserved for headline
  and a 4-up metric quad; horizon-free, no center subject.
[NEGATIVES] no text, no letters, no numbers, no logos, no watermark,
  no UI, no charts, no faces, no brand likeness, no clutter, no
  oversaturation, no flare kitsch.
seed=fixed · model=<approved> · stored in brief.json:page.assets[0]
```

### 4.5 Schema hook

Each page gains an optional `assets: [{ slot, prompt, negative, seed,
model, params, cache_path, status }]`. The research/critique pass fills
`prompt` (SUBJECT+COMPOSITION) from page meaning; STYLE_CAPSULE and
NEGATIVES are injected by code so they can't drift. `status` ∈
`pending|ok|rejected|fallback` drives the graceful-degradation logic.

---

## 5. Harness & versioned output

CLI: `python -m scripts.visual_brief TICKER [flags]`

| Flag | Effect |
|---|---|
| (default) | research → render EN+ZH → eval |
| `--render-only` | skip research; render from existing/fixture `brief.json` (the fast loop) |
| `--research-only` | run research, freeze `brief.json`, stop |
| `--locale en,zh` | which locales to emit |
| `--rubric` | run the automated visual-QA + critique pass |
| `--golden accept` | promote this run's PNGs to the golden baseline |

Run folder (mirrors `memo-pipeline` versioning — never overwrite):

```
data/visual_briefs/<ticker>/<YYYY-MM-DD>__<HHMMSS>/
  brief.json                 # frozen research model
  brief.html                 # live deck for inspection
  pages/en/page-01.png …     pages/zh/page-01.png …
  brief-en.pdf  brief-zh.pdf
  eval/
    rubric.json              # automated score per dimension/page
    critique.md              # Claude vision-critique output + fix list
    lint.json                # deterministic linter results
    diff/page-NN.png         # pixel diff vs accepted golden
  logs/stream.jsonl          # progress events (same vocabulary as memo
                             #   pipeline → trivial Active-Jobs wiring later)
```

---

## 6. Iterative testing — the path to "awesome"

This is the core methodology. It converges fast because research is
frozen, rendering is free and deterministic, and the quality signal is
automated.

**Phase 0 — Freeze fixtures.** Run the research pass for **AMD, NVDA,
AMZN** (deliberately different data shapes: AMD = segment growth, NVDA =
margin/concentration extreme, AMZN = multi-segment conglomerate). Hand-
verify each JSON. Save to `tests/fixtures/brief_{amd,nvda,amzn}.json`.
After this, all rendering iteration is **$0 and deterministic**.

**Phase 1 — Component gallery.** `gallery.html` renders every component
in isolation with **edge-case synthetic data**: huge/negative numbers,
12-row matrices, missing values, longest-allowed CJK strings. Tune each
component to perfection here before composing pages. Lock golden PNGs.

**Phase 2 — Page composition.** Compose all ~13 page templates from the
AMD fixture, EN + ZH. First full visual review.

**Phase 3 — Automated visual QA (two gates, no eyeballing required):**

- **Deterministic linter** (`eval/lint.json`): zero text overflow/clip
  (measured via Chromium box metrics), no element collisions, contrast
  ≥ AA, each page has kicker+headline+dek+footer+≥1 viz, CJK glyph
  coverage (no `�`/tofu), exact page count & aspect, chart values
  numerically equal to the JSON (truthfulness check, not "looks right").
- **LLM vision critique** (`eval/critique.md`): a `claude_runner` vision
  pass receives the rendered PNGs + the rubric and scores each page 1–5
  on **information density, visual hierarchy, chart truthfulness,
  aesthetic polish, bilingual parity, "WeChat-shareable punch."** It
  returns specific, actionable fixes. We apply, re-render (free),
  re-score. Loop.

**Phase 4 — Robustness sweep.** `--render-only` against NVDA, AMZN, and
a deliberately sparse fixture. Fix every layout that breaks under real
data variance. Re-lock goldens.

**Phase 5 — Quality-bar gate (explicit exit criteria):**

- Rubric ≥ 4.3/5 mean across pages, no single page < 4.0.
- Zero linter failures across all 4 fixtures, both locales.
- Blind A/B critique: our deck beats the WeChat SpaceX reference on
  density + polish in ≥ 4 of 5 trials.

Only after Phase 5 do we discuss app integration.

---

## 7. App integration (deferred — not in the prototype)

Once the quality gate is cleared, the wiring is mechanical and mirrors
patterns already in the repo:

- `claude_runner.run_visual_brief()` — research pass, schema-validated,
  stream-json, progress events.
- `report_type = "Visual Stock Brief"` in `POST /api/reports`; job kind
  `visual_brief`; surfaces in the bottom-of-sidebar Active Jobs (the
  `logs/stream.jsonl` vocabulary is already compatible).
- A modal showing the PNG deck with the existing EN/中文 toggle, deep-
  linking to versioned runs like the memo UI.

Explicitly **out of scope** until the prototype quality bar passes.

---

## 8. Risks & decisions flagged

- **Chromium/Playwright dependency.** Fine on the user's Mac; add to
  README. Python-only (`resvg`) fallback documented but not preferred.
- **Research truthfulness.** Enforced by schema (nullable) + the
  linter's JSON-vs-chart numeric equality check. The critique pass
  judges design, the linter judges facts.
- **Bilingual layout drift.** Solved by per-field max-char budgets in
  the research prompt, not by render-time text shrinking (which would
  destroy the aesthetic). A hard floor on font size; if content can't
  fit at the floor, that's a research-prompt bug, not a render hack.
- **Cost/latency of research.** Mitigated structurally: ~3 research runs
  total during the entire prototype; everything else is free re-renders.
- **Generated-art drift / off-brand / text contamination.** Contained by
  the fixed `STYLE_CAPSULE` + `NEGATIVES` constants (only SUBJECT/
  COMPOSITION vary), the vision-critique gate, golden prompt+seed
  locking, and the rule that art is additive — a rejected image falls
  back to a code-drawn texture and never blocks the deck.

---

## 9. First concrete actions

1. Stand up `scripts/visual_brief.py` skeleton + run-folder versioning
   (copy the `memo_prep` folder/manifest pattern).
2. Write `BRIEF_SCHEMA` + the research SYSTEM_PROMPT; add
   `claude_runner.run_visual_brief()`. Generate + hand-verify the AMD
   fixture, freeze it.
3. Build the design-token file + Chromium render harness + the
   `hero`, `metric_quad`, `area_chart`, `donut`, `waterfall` components.
   `gallery.html` with edge-case data.
4. Lock the `STYLE_CAPSULE` + `NEGATIVES` constants and the metaphor
   bank; wire the cached, approved-path art step + the `assets[]` schema
   hook; A/B 3–4 seeds per slot in the gallery and golden-lock winners.
5. Compose the AMD deck EN+ZH end-to-end (charts + composited art);
   first visual review.
6. Add the deterministic linter, then the Claude vision-critique loop
   (pages *and* in-context art legibility); iterate to the Phase-5 bar.
