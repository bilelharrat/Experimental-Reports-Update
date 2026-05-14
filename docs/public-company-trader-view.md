# Public-Company Trader View — design

When the user searches for and opens a publicly-traded company (e.g.
`AMD`, `NVDA`, `AAPL`), the company-detail page renders a
**trader-focused dossier** instead of the private-company dossier we
already render today. The trader view is what an active trader would
want to see to make a snap decision: where price has been, what the
sell-side thinks, what the calendar holds, what the tape feels like.

Private companies (and subsidiaries, nonprofits, etc.) keep the
current `CompanyDetail` layout exactly as it is.

This doc is the spec. Four phases at the bottom.

---

## 1. Company-type discriminator

The deep-search schema already emits `status` with one of
`"public" | "private" | "subsidiary" | "nonprofit" | null`. We promote
that to a first-class **`company_type`** discriminator on the
persisted record so every consumer (API, frontend, Console) can route
on it without reinterpreting `status` each time.

```yaml
# companies.yaml — one entry per company
- id: amd
  name: Advanced Micro Devices, Inc.
  ticker: AMD
  status: public                # raw from deep-search
  company_type: public          # NEW — normalized: "public" | "private"
  # …existing fields…
  trader_snapshot:              # NEW — present only when company_type == "public"
    refreshed_at: 2026-05-13T18:04:00Z
    # …cards detailed in §3…
```

### Bucketing rule

| `status` value | → `company_type` |
|---|---|
| `public` | `public` |
| `private` | `private` |
| `subsidiary` | `private` |
| `nonprofit` | `private` |
| `null` and ticker present on a real exchange | `public` |
| `null` and no ticker | `private` |

The fallback for null+ticker handles companies the deep-search left
under-specified but where ticker presence is a strong signal.

### Backfill

A one-shot backfill runs on server startup (`storage.bootstrap_seed_data`
already exists — extend it). It iterates `companies.yaml`, computes
`company_type` for every entry missing the field, and writes the file
back. Idempotent.

```python
def _backfill_company_types() -> None:
    companies = list_companies()
    changed = False
    for c in companies:
        if c.get("company_type"):
            continue
        c["company_type"] = _infer_company_type(c)
        changed = True
    if changed:
        _write_yaml(COMPANIES_FILE, companies)
```

Going forward, `storage.upsert_company_from_match` sets
`company_type` at create time from the deep-search status field.

---

## 2. UX

The user opens `/research/{company_id}` and sees one of two layouts
based on `company_type`. The header (name, ticker, logo, description,
language toggle, refresh button) is shared.

### Public layout

```
┌─ Header ───────────────────────────────────────────────────────────┐
│ [logo]  AMD · NASDAQ · Semiconductors                              │
│         Advanced Micro Devices designs and produces GPUs, CPUs, …  │
│         [ ↻ Refresh trader view ]  updated 8 min ago               │
├────────────────────────────────────────────────────────────────────┤
│ ┌─ Price ─────┐ ┌─ Momentum ────┐ ┌─ Sentiment ────────────────┐  │
│ │ $174.22     │ │ ▲ Bullish     │ │ Buy · 38  Hold · 12  Sell·1│  │
│ │ +1.8% (1d)  │ │ Above 50DMA   │ │ Target: $195 (mean)        │  │
│ │ +12.4% (30d)│ │ Above 200DMA  │ │  high $230 · low $148       │  │
│ │ +28% YTD    │ │ 5-day high    │ │ 3 upgrades, 0 downgrades 7d │  │
│ │ +14% vs SOX │ │               │ │                             │  │
│ └─────────────┘ └───────────────┘ └─────────────────────────────┘  │
│ ┌─ Heat ──────────────────────────┐ ┌─ Catalysts ──────────────┐  │
│ │ Relative vol: 1.4× 20d avg      │ │ Q2 earnings · Jul 30     │  │
│ │ IV (30d): 42% (78th pctile)     │ │ AI Day · Jun 12          │  │
│ │ Skew: call-side bid             │ │ Mi400 launch (rumored)   │  │
│ │ News flow: 11 items / 24h       │ │ ex-div · May 28          │  │
│ │ Insiders: 2 sells, 0 buys 30d   │ │                          │  │
│ │ Short interest: 2.1% (low)      │ │                          │  │
│ └─────────────────────────────────┘ └──────────────────────────┘  │
│ ┌─ Trader news ─────────────────────────────────────────────────┐ │
│ │ ⚡ Q1 beat on data-center, FY guide raised   May 7   positive │ │
│ │ ⚡ Reuters: hyperscaler deal expanded         May 5   positive │ │
│ │ • DOJ probe headline — sector-wide           May 3   negative │ │
│ └────────────────────────────────────────────────────────────────┘ │
│ ┌─ Background ──────────────────────────────────────────────────┐ │
│ │ Sector · Industry · HQ · Founded · Employees                  │ │
│ │ Key people (CEO, CFO, CTO)                                    │ │
│ │ Competitors                                                    │ │
│ └────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

Below the trader cards, a slimmer **Background** strip keeps the
non-trader identity fields (sector, industry, HQ, founded year,
employees, CEO/CFO/CTO chips, competitors). These are still useful but
demoted from "first thing you see."

### Private layout

Unchanged. Today's `CompanyDetail.vue` renders products, key people,
funding history, recent news, contracts, acquisitions — same as ever.

### Tabs

The three Research-view tabs (Overview / Documents / Console) keep
their meaning. The trader cards live in **Overview** for public
companies. Documents and Console are type-agnostic.

---

## 3. Trader-snapshot data model

`trader_snapshot` is a typed object the LLM fills per refresh. Every
card has its own sub-object so individual cards can be flagged stale
and (later) refreshed independently. For v1, **one refresh button
rebuilds the whole snapshot in one Claude call**.

```yaml
trader_snapshot:
  refreshed_at: 2026-05-13T18:04:00Z
  generation_cost_usd: 0.18
  generation_duration_ms: 14200

  price_card:
    last_price: 174.22
    currency: USD
    as_of: 2026-05-13T15:59:00-04:00     # ISO with tz
    change_pct_1d: 1.82
    change_pct_5d: 4.10
    change_pct_30d: 12.41
    change_pct_ytd: 28.03
    change_pct_1y: 47.55
    vs_sector_30d_pct: 14.20             # vs SOX or sector ETF
    vs_sp500_30d_pct: 9.80

  momentum_card:
    trend: bullish                       # bullish | neutral | bearish
    above_50dma: true
    above_200dma: true
    ma_crossover_recent: golden_cross    # null | golden_cross | death_cross
    breakout_signals: ["5-day high", "20-day high"]
    notable_levels:
      support: 162.00
      resistance: 178.50

  sentiment_card:
    analyst_consensus: Buy               # Strong Buy | Buy | Hold | Sell | Strong Sell
    coverage_count: 51
    rating_distribution:
      strong_buy: 18
      buy: 20
      hold: 12
      sell: 1
      strong_sell: 0
    target_price:
      mean: 195.00
      high: 230.00
      low: 148.00
    recent_rating_changes:               # last 30d
      - { firm: "Morgan Stanley", action: "Upgrade", from: "EW", to: "OW", date: "2026-05-08", target: 210 }
      - { firm: "Goldman",        action: "Maintain", from: null, to: "Buy", date: "2026-05-05", target: 200 }

  heat_card:
    rel_volume_20d: 1.4                  # today vs 20-day average
    iv_30d_pct: 42.0
    iv_percentile_1y: 78
    options_skew: call_bid               # call_bid | balanced | put_bid
    news_flow_24h: 11
    insider_activity_30d:
      buys: 0
      sells: 2
      net_share_count_change: -45000
    short_interest_pct_float: 2.1
    days_to_cover: 1.8
    social_mentions_trend: rising        # rising | flat | falling | null

  catalysts:
    - date: 2026-07-30
      type: earnings                      # earnings | guidance | regulatory | conference | product | legal | dividend | other
      title: Q2 2026 earnings
      summary: After-hours; current consensus EPS $1.28
      est_impact: high                    # high | medium | low
    - date: 2026-06-12
      type: conference
      title: Advancing AI 2026
      summary: Annual data-center / AI roadmap event
      est_impact: high
    - date: 2026-05-28
      type: dividend
      title: ex-dividend date
      summary: $0.24/share
      est_impact: low

  trader_news:
    - headline: "Q1 beat on data-center; FY guide raised"
      date: 2026-05-07
      summary: Data-center revenue +47% YoY; FY26 revenue guided $35-37B vs $33B prior
      bias: positive                      # positive | negative | neutral
      source_url: https://…
    - headline: "Reuters: hyperscaler deal expanded"
      …

  tech_movers:
    updated_at: 2026-05-13T20:15:00Z      # daily market context
    movers:
      - ticker: NVDA
        company_en: NVIDIA
        company_zh: 英伟达
        change_pct_1d: 5.8
        direction: up                      # up | down | flat
        market_driver_en: Analyst target raise and AI data-center demand read-through.
        market_driver_zh: 分析师上调目标价，并受益于 AI 数据中心需求预期。
        source_url: https://…
      - ticker: SNOW
        company_en: Snowflake
        company_zh: Snowflake
        change_pct_1d: -6.4
        direction: down
        market_driver_en: Post-earnings guidance reset and software multiple compression.
        market_driver_zh: 财报后指引下修，叠加软件板块估值压缩。
        source_url: https://…
```

All numeric fields are nullable (`null`) so the model can leave any
piece unverifiable — same convention as the existing
private-company schema.

---

## 4. Backend pipeline

### New module: `server/companies_ai_public.py`

Owns the public-snapshot SCHEMA + SYSTEM_PROMPT. Roughly mirrors the
shape of the existing `companies_ai.py` but the prompt is built for
trader output, not company-dossier output.

```python
SYSTEM_PROMPT = (
    "You are a sell-side trader's research desk. Given a publicly-"
    "traded company (ticker + name), produce a JSON snapshot covering "
    "price action, momentum, sentiment, heat, upcoming catalysts, and "
    "trader-relevant news.\n\n"
    "Use WebSearch and WebFetch aggressively: pull from Yahoo Finance, "
    "Nasdaq, official IR pages, the SEC, Refinitiv-style aggregator "
    "pages, Reuters, Bloomberg, recent analyst reports. NEVER invent "
    "numbers — if a field can't be verified, return null.\n\n"
    "Per-card guidance:\n"
    "- price_card: last close + % returns + relative vs sector/SP500.\n"
    "- momentum_card: trend label + MA position + recent breakouts.\n"
    "- sentiment_card: analyst rating distribution + price targets + "
    "  rating changes in the last 30 days.\n"
    "- heat_card: relative volume, IV percentile, options skew, "
    "  insider 30-day net, short interest, news flow count.\n"
    "- catalysts: upcoming dated events the next ~90 days, sorted by "
    "  date. Earnings, FDA, court rulings, ex-div, M&A votes, "
    "  conferences, product launches.\n"
    "- trader_news: 3-5 items from the last 14 days that meaningfully "
    "  moved the stock or are likely to. Tag bias.\n"
)
```

### New claude_runner helper

```python
def run_public_company_snapshot(
    *,
    company: dict,   # the current company record (name, ticker, …)
    schema: dict,
    system_prompt: str,
    timeout_sec: int = 600,
    progress=None,
) -> tuple[dict | None, str | None]:
    """Return (snapshot, error). Mirrors run_company_search but with
    schema/prompt tuned for a single ticker, not a list of matches.
    """
```

Inside, the prompt is built from `company.name`, `company.ticker`,
`company.exchange`. Streams `claude_action` events through `progress`
identical to existing pipelines.

### Refresh endpoint

```
POST /api/companies/{company_id}/trader/refresh
```

Returns immediately with `{job_id, stream_url}`; the snapshot is
written to disk when the subprocess finishes and the SSE stream emits
`done`. The frontend tails the stream to update the card grid live.

```
GET /api/companies/{company_id}/trader/refresh/stream/{job_id}    # SSE
```

Job kind: `public_snapshot`. Surfaces in the existing
`/api/jobs/active` AI rail alongside Console / search / memo jobs.

### Storage hook

`storage.upsert_company_from_match` (existing) sets `company_type`
from the deep-search `status` field on first create. A new
`storage.update_company_snapshot(company_id, snapshot: dict)` writes
the snapshot back atomically.

---

## 5. Console adaptation

The Console feature today loads `server/skills/bsh_company_console.md`
as `--append-system-prompt` for every hydrate/ask. We add a sibling:

`server/skills/bsh_company_console_public.md` — same shape, different
persona:

- "You are a sell-side trader's analyst." (vs the existing analyst-
  desk persona)
- Ground claims in price moves, catalysts, sentiment as well as the
  staged dossier.
- Recent-news answers should cite **and date** the move.
- The bilingual rule and document discipline from the base skill
  apply unchanged.

`console_session.create_session` reads the target company's
`company_type` and selects the right skill path. The selection is
recorded on `meta.skill_path` so it's stable across the lifetime of
the session even if the company gets re-typed later. (Re-typing a
company mid-session would be rare; recording the choice keeps the
behavior deterministic.)

---

## 6. Per-card staleness

One refresh button, but the UI flags each card with its own stale
threshold so the user can see at a glance which numbers are dependable:

| Card | Fresh (green) | Warning (yellow) | Stale (red) |
|---|---|---|---|
| price_card | < 1h | 1–4h | ≥ 4h |
| momentum_card | < 4h | 4–24h | ≥ 24h |
| sentiment_card | < 24h | 1–7d | ≥ 7d |
| heat_card | < 6h | 6–24h | ≥ 24h |
| catalysts | < 24h | 1–7d | ≥ 7d |
| trader_news | < 6h | 6–24h | ≥ 24h |

Thresholds are frontend constants. The card chrome uses a tiny
"updated 2h ago" caption; the badge color is driven by the bucket.
**One** refresh button at the top of the page re-runs everything (one
Claude subprocess, one SSE stream). v1 does not refresh cards
individually.

---

## 7. Tests

### Backend

- `tests/test_companies_ai_public.py` — schema validation; SYSTEM_PROMPT
  is well-formed; `run_public_company_snapshot` stubs return shape.
- `tests/test_storage_company_type.py` — backfill is idempotent;
  bucketing rule covers all `status` values; `upsert_company_from_match`
  sets `company_type` correctly.
- `tests/test_trader_api.py` — `POST /trader/refresh` returns
  job/stream URL; SSE replay works.
- `@pytest.mark.e2e` — one real-Claude run against `AMD`; assert
  `price_card.last_price` is a number, `catalysts` is a non-empty
  list, `sentiment_card.target_price.mean` is plausible.

### Frontend

- `frontend/tests/CompanyDetail.spec.js` — branch test:
  `company_type === "public"` mounts the trader cards;
  `company_type === "private"` mounts the existing layout.
- Per-card staleness coloring (table-driven, similar to the Console
  token-meter test).
- i18n key coverage for new trader strings.

---

## 8. Implementation phases

Each phase is one commit on `main`.

### Phase 1 — schema discriminator + backfill

- `server/storage.py` — `company_type` derived/persisted on upsert;
  one-shot backfill in `bootstrap_seed_data`.
- `server/api.py` — `CompanyOut` exposes `company_type`.
- Frontend — no UI change yet; just plumbs the new field through
  `api.js` types.
- Test: backfill is idempotent; existing companies get a sensible
  type; new deep-search results carry the type forward.

### Phase 2 — trader snapshot backend

- `server/companies_ai_public.py` — schema + prompt.
- `server/claude_runner.py` — `run_public_company_snapshot`.
- `server/api.py` — `POST /trader/refresh`, SSE stream, job-rail
  integration (kind=`public_snapshot`).
- `server/storage.py` — `update_company_snapshot()`.
- Test: stubbed runner returns a synthetic snapshot, endpoint persists
  it, SSE stream replays it.

### Phase 3 — type-aware CompanyDetail (frontend)

- `frontend/src/components/CompanyDetail.vue` — split into
  `CompanyDetailPrivate.vue` (current behavior) + `CompanyDetailPublic.vue`
  (trader cards) + a thin dispatcher that picks one based on
  `company.company_type`.
- `frontend/src/components/trader/` — one file per card
  (`PriceCard.vue`, `MomentumCard.vue`, `SentimentCard.vue`,
  `HeatCard.vue`, `CatalystCard.vue`, `TraderNewsCard.vue`).
- `frontend/src/trader.js` — pure helpers for staleness bucketing,
  number/% formatting, color picking.
- `frontend/src/i18n.js` — EN + ZH for all new strings.

### Phase 4 — Console persona swap + polish

- `server/skills/bsh_company_console_public.md`.
- `server/console_session.py` — pick skill by `company_type`,
  record on `meta.skill_path`.
- Polish: refresh-button loading state, per-card stale color, tooltips
  with sources.

Total effort estimate: 6–9 hours.

---

## 9. Out of scope (v1)

- **Auto-refresh on page open.** Manual button only; staleness is
  flagged visually but never auto-acts.
- **Per-card refresh.** One big refresh re-runs everything.
- **Real-time market-data API.** All data comes through Claude's
  WebSearch/WebFetch against public pages (Yahoo, Nasdaq, IR, SEC,
  Reuters). A Polygon / Alpha Vantage integration is a future option
  if the WebFetch path proves too slow or unreliable.
- **Options chain / advanced derivatives.** `heat_card` shows IV
  percentile and skew direction; no chain rendering.
- **Backtests / hypothetical PnL.** Snap decision support only.
- **Multi-class / multi-listing handling.** Each ticker = one record;
  no GOOGL-vs-GOOG dance for v1.
- **Custom-watchlist alerting.** No "ping me when AMD breaks $180."

---

## 10. Open questions resolved

- Placement: trader info renders **as** the company-detail card when
  `company_type === "public"` — not a separate tab. Mirrors how the
  private dossier works today.
- Field granularity: **structured cards** (typed sub-objects), not
  free-text bullets. Filterable, comparable, easy to refresh.
- Refresh cadence: **manual button + per-card stale color**. No
  auto-refresh, no scheduled cron.
- Console adaptation: **yes** — public-company Console sessions use
  a different skill prompt (trader analyst persona). Selection is
  baked into the session at create time.
- Discriminator field name: `company_type` (normalized, two values);
  the raw deep-search `status` stays as-is for higher-resolution
  bucketing later.
