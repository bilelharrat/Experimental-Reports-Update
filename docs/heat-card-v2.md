# Positioning Structure — Heat Card v2

Design spec for the rebuilt trader-snapshot "Heat" card.

This is the canonical contract for `trader_snapshot.heat_card`. It
replaces the v1 shape (rel_volume, IV%, options_skew, news_flow,
insider_counts, social_mentions) entirely. Both the FastAPI server
and the iOS app read from this contract; the web SPA and iOS view
both consume it identically.

---

## 1. Goal

Let a desk analyst answer four questions in ~15 seconds:

1. **Who owns this?** — passive vs hedge fund vs retail vs strategic.
2. **Where are they trapped or comfortable?** — current price vs
   institutional cost-basis anchors.
3. **What breaks the thesis?** — fragility drivers, narrative
   premium, crowding.
4. **Where is asymmetric entry?** — float-turnover zones with
   support-confidence ratings.

The card optimizes for **explanatory power, decision usefulness,
regime awareness, positioning insight** — not data density. Every
field should let the reader take or rule out an action.

We drop the v1 fields wholesale. They were low-causal signal
(RSI-style indicators, generic social-mention trend, etc.). The
high-signal v1 fields that survive are folded into v2:
`short_interest_pct_float` and `days_to_cover` move under
`short_pressure`.

---

## 2. Sections (renders top to bottom in the card)

| # | Section | Sub-object | Purpose |
|---|---|---|---|
| 1 | Anchored cost basis | `anchored_vwaps` | Institutional cost basis vs current price |
| 2 | Float turnover zones | `float_turnover_zones` | Where shares actually changed hands |
| 3 | Holder mix | `holder_mix` | Stability quality of ownership |
| 4 | Options regime | `options_positioning` | Dealer gamma / put-call wall |
| 5 | Short pressure | `short_pressure` | Squeeze fuel + structural bearish conviction |
| 6 | Valuation | `valuation` | Downside asymmetry |
| 7 | Revisions | `revisions` | Forward estimate momentum |
| 8 | Next catalyst | `next_catalyst` | Repricing trigger + implied move |
| C1 | Support confidence | `support_confidence` | Composite — weighted by holder quality, valuation, gamma, turnover, insider |
| C2 | Fragility | `fragility` | Composite — narrative %, leverage, crowdedness, option instability |
| C3 | Repricing risk | `repricing_risk` | Probability distribution: positive / neutral / negative |

Card title: **"Positioning Structure"** (rendered as "持仓结构" in
Chinese). Replaces the old "Heat" label.

---

## 3. Schema (strict-mode JSON)

Every sub-object is independently nullable so a sparsely-covered
company doesn't poison the whole card. Every estimated sub-object
carries a `confidence` enum and paired bilingual `confidence_note`
strings — when `confidence == "unavailable"`, the data fields can
be null but the explanation must still be present so the UI can
render a meaningful "couldn't source this because X" placeholder.

```python
_CONFIDENCE = {
    "type": ["string", "null"],
    "enum": ["high", "medium", "low", "unavailable", None],
}

"heat_card": {
    "type": ["object", "null"],
    "additionalProperties": False,
    "properties": {

        # 1. Institutional cost basis — anchored VWAPs from key events.
        "anchored_vwaps": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "current_price": _NUM_NULL,
                "anchors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": [
                                    "earnings", "ai_event", "ipo",
                                    "secondary", "52w_high",
                                    "macro_event", "other",
                                ],
                            },
                            "label_en": _STR_NULL,
                            "label_zh": _STR_NULL,
                            "date": _STR_NULL,
                            "price": _NUM_NULL,
                        },
                        "required": ["kind", "label_en", "label_zh",
                                     "date", "price"],
                    },
                },
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["current_price", "anchors",
                         "confidence", "confidence_note_en",
                         "confidence_note_zh"],
        },

        # 2. Float turnover zones — where shares actually changed hands.
        "float_turnover_zones": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "zones": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "low": _NUM_NULL,
                            "high": _NUM_NULL,
                            "pct_float": _NUM_NULL,
                            "note_en": _STR_NULL,
                            "note_zh": _STR_NULL,
                        },
                        "required": ["low", "high", "pct_float",
                                     "note_en", "note_zh"],
                    },
                },
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["zones", "confidence",
                         "confidence_note_en", "confidence_note_zh"],
        },

        # 3. Holder mix — institutional ownership stability.
        "holder_mix": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "passive_pct": _NUM_NULL,
                "long_only_pct": _NUM_NULL,
                "hedge_fund_pct": _NUM_NULL,
                "retail_pct": _NUM_NULL,
                "insider_pct": _NUM_NULL,
                "strategic_pct": _NUM_NULL,
                "quality_label_en": _STR_NULL,
                "quality_label_zh": _STR_NULL,
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["passive_pct", "long_only_pct",
                         "hedge_fund_pct", "retail_pct",
                         "insider_pct", "strategic_pct",
                         "quality_label_en", "quality_label_zh",
                         "confidence", "confidence_note_en",
                         "confidence_note_zh"],
        },

        # 4. Options positioning — dealer gamma + walls.
        "options_positioning": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "gamma_flip": _NUM_NULL,
                "put_wall": _NUM_NULL,
                "call_wall": _NUM_NULL,
                "regime_en": _STR_NULL,
                "regime_zh": _STR_NULL,
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["gamma_flip", "put_wall", "call_wall",
                         "regime_en", "regime_zh",
                         "confidence", "confidence_note_en",
                         "confidence_note_zh"],
        },

        # 5. Short pressure — squeeze fuel + structural shorts.
        "short_pressure": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "si_pct_float": _NUM_NULL,
                "days_to_cover": _NUM_NULL,
                "borrow_rate_pct": _NUM_NULL,
                "trend": {
                    "type": ["string", "null"],
                    "enum": ["rising", "falling", "flat", None],
                },
                "note_en": _STR_NULL,
                "note_zh": _STR_NULL,
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["si_pct_float", "days_to_cover",
                         "borrow_rate_pct", "trend",
                         "note_en", "note_zh",
                         "confidence", "confidence_note_en",
                         "confidence_note_zh"],
        },

        # 6. Relative valuation — downside asymmetry.
        "valuation": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "ev_revenue_current": _NUM_NULL,
                "ev_revenue_5y_percentile": _INT_NULL,
                "fwd_ev_ebitda": _NUM_NULL,
                "peg": _NUM_NULL,
                "note_en": _STR_NULL,
                "note_zh": _STR_NULL,
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["ev_revenue_current",
                         "ev_revenue_5y_percentile",
                         "fwd_ev_ebitda", "peg",
                         "note_en", "note_zh",
                         "confidence", "confidence_note_en",
                         "confidence_note_zh"],
        },

        # 7. Estimate revisions — forward momentum.
        "revisions": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "eps_up_30d": _INT_NULL,
                "eps_down_30d": _INT_NULL,
                "eps_up_90d": _INT_NULL,
                "eps_down_90d": _INT_NULL,
                "direction": {
                    "type": ["string", "null"],
                    "enum": ["up", "down", "mixed", None],
                },
                "note_en": _STR_NULL,
                "note_zh": _STR_NULL,
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["eps_up_30d", "eps_down_30d",
                         "eps_up_90d", "eps_down_90d",
                         "direction", "note_en", "note_zh",
                         "confidence", "confidence_note_en",
                         "confidence_note_zh"],
        },

        # 8. Next catalyst — repricing trigger + implied move.
        "next_catalyst": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "label_en": _STR_NULL,
                "label_zh": _STR_NULL,
                "date": _STR_NULL,
                "implied_move_pct": _NUM_NULL,
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["label_en", "label_zh",
                         "date", "implied_move_pct",
                         "confidence", "confidence_note_en",
                         "confidence_note_zh"],
        },

        # Composite 1. Support confidence by price zone.
        "support_confidence": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "zones": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "low": _NUM_NULL,
                            "high": _NUM_NULL,
                            "confidence": _CONFIDENCE,
                            "reasons_en": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reasons_zh": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["low", "high", "confidence",
                                     "reasons_en", "reasons_zh"],
                    },
                },
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["zones", "confidence",
                         "confidence_note_en", "confidence_note_zh"],
        },

        # Composite 2. Fragility — 0-100 score + drivers.
        "fragility": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "score": _INT_NULL,
                "rating": {
                    "type": ["string", "null"],
                    "enum": ["low", "medium", "high", "extreme", None],
                },
                "drivers_en": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "drivers_zh": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["score", "rating",
                         "drivers_en", "drivers_zh",
                         "confidence", "confidence_note_en",
                         "confidence_note_zh"],
        },

        # Composite 3. Repricing risk — directional probability.
        "repricing_risk": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "positive_pct": _INT_NULL,
                "neutral_pct": _INT_NULL,
                "negative_pct": _INT_NULL,
                "note_en": _STR_NULL,
                "note_zh": _STR_NULL,
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": ["positive_pct", "neutral_pct",
                         "negative_pct",
                         "note_en", "note_zh",
                         "confidence", "confidence_note_en",
                         "confidence_note_zh"],
        },
    },
    "required": ["anchored_vwaps", "float_turnover_zones",
                 "holder_mix", "options_positioning",
                 "short_pressure", "valuation", "revisions",
                 "next_catalyst", "support_confidence",
                 "fragility", "repricing_risk"],
},
```

`schema_version` is stamped by the worker on the saved snapshot
(not in the model schema). When the worker writes a fresh
snapshot, it sets `trader_snapshot.schema_version = 2`. Anything
without that field, or with a lower value, is treated as legacy
by the server's migration sweep and by the client banner.

---

## 4. Confidence semantics

Per-section `confidence`:

| Value | Meaning | Data fields | UI treatment |
|---|---|---|---|
| `"high"` | Sourced from a primary or named aggregator | All populated | Render normally |
| `"medium"` | Sourced from secondary; some triangulation | Most populated | Render with a small confidence dot |
| `"low"` | Inferred / estimated from indirect signals | Partial | Render dimmed with a hover note |
| `"unavailable"` | Couldn't source | All null | Render the `confidence_note_*` as a one-line "couldn't source: X" placeholder |
| `null` | Not assessed | Data fields nullable | Treat as `"low"` |

`confidence_note_en` / `_zh` should always be filled. It's the
one place the LLM gets to be honest about uncertainty.

Example for AMD with weak option-flow coverage:

```json
"options_positioning": {
  "gamma_flip": null, "put_wall": null, "call_wall": null,
  "regime_en": null, "regime_zh": null,
  "confidence": "unavailable",
  "confidence_note_en":
    "SpotGamma/Tier1Alpha not publicly accessible; CBOE OI not granular enough.",
  "confidence_note_zh":
    "无法访问 SpotGamma/Tier1Alpha 等付费数据；CBOE 公开未结合约粒度不足。"
}
```

---

## 5. Visual layout (1/3-column card, sparse-friendly)

```
🔥 Positioning Structure                       fresh · 0.4h
─────────────────────────────────────────────────────────────
Anchored cost basis                       $446.40       ●●●
  vs Earnings AVWAP   $421.39   ▲ +5.9%
  vs AI-event AVWAP   $437.10   ▲ +2.1%
  vs 52w-high AVWAP   $469.22   ▼ −4.8%
─────────────────────────────────────────────────────────────
Float turnover (heat zones)                            ●●○
  $412–425  ████████░░  22%
  $380–400  ███████░░░  18%
  $355–370  █████░░░░░  11%
─────────────────────────────────────────────────────────────
Holder mix                  Options regime              ●●○
  Passive    35%           Gamma flip $432  above ▲
  Long-only  28%           Put wall   $400
  Hedge fund 22%           Call wall  $460
  Retail     10%
  Insider     1.5%
  Strategic   3.5%
  "Passive anchor, HF overhang"
─────────────────────────────────────────────────────────────
Short pressure              Valuation                   ●●●
  SI 2.2% float            EV/Rev 12× (18th %ile, 5y)
  Days cvr 0.8             Fwd EV/EBITDA 22×
  Borrow 0.5% ▼            PEG 1.4×
─────────────────────────────────────────────────────────────
Revisions (EPS)             Next catalyst               ●●●
  +14 / −3 (30d) ↑          Q2 earnings · Jul 30
  +22 / −8 (90d) ↑          Implied move ±11%
─────────────────────────────────────────────────────────────
Support confidence
  $412–425  HIGH  AVWAP earnings · 22% turnover
  $400–410  MED   AI-event AVWAP
Fragility ●●●○○  55/100  AI-narrative 55%, HF crowded
Repricing risk  35% ▲  /  40% ▬  /  25% ▼
─────────────────────────────────────────────────────────────
```

Confidence dots on the right of each section header. Each section
collapses to a single italic "couldn't source" line when
`confidence == "unavailable"`. The card hides any section whose
sub-object is null entirely.

---

## 6. Schema versioning + legacy migration

A breaking change like this needs to invalidate existing
snapshots so the iOS app and web SPA don't try to read v1 shape
through v2 code.

### `schema_version`

- Stamped by `_run_trader_snapshot_job` on every saved snapshot:
  `trader_snapshot.schema_version = 2`.
- Lives on `trader_snapshot`, not on the company record itself.
- `1` (or missing) means v1 (legacy). `2` means v2 (Positioning
  Structure).

### Startup migration

On server startup, sweep `companies.yaml`. For any company whose
`trader_snapshot` has either:

- No `schema_version` field, OR
- `schema_version < 2`, OR
- A `heat_card` containing v1-only keys (`rel_volume_20d`,
  `iv_30d_pct`, `options_skew`, `news_flow_24h`,
  `insider_activity_30d`, `social_mentions_trend`)

...strip the entire `heat_card` field and bump
`schema_version` to `2`. The rest of the snapshot (price card,
momentum, sentiment, catalysts, news, tech movers) stays intact
since those didn't change.

The migration is idempotent — running it twice is a no-op.

### Force-refresh endpoint

```http
POST /api/companies/{id}/trader/refresh?force=true
```

Skips the `already_running` short-circuit and clears any stale
in-flight progress file before queuing a new worker. Behavior:

1. If a progress file exists and isn't terminated, mark it as
   terminated (emit a synthetic `error` event with
   `"superseded by force-refresh"`) and unlink it.
2. Spawn a new worker as usual.
3. Response: same shape as the normal endpoint, with `status:
   "force_queued"` to distinguish from the usual `"queued"`.

UI surface: a long-press / option-click on the Refresh button on
the trader card surfaces a "Force refresh" menu item. Default
behavior unchanged.

---

## 7. Bilingual coverage

Every prose field carries paired `_en` / `_zh`:

- `anchored_vwaps.anchors[*].label_en` / `_zh`
- `anchored_vwaps.confidence_note_en` / `_zh`
- `float_turnover_zones.zones[*].note_en` / `_zh`
- `float_turnover_zones.confidence_note_en` / `_zh`
- `holder_mix.quality_label_en` / `_zh`
- `holder_mix.confidence_note_en` / `_zh`
- `options_positioning.regime_en` / `_zh`
- `options_positioning.confidence_note_en` / `_zh`
- `short_pressure.note_en` / `_zh`
- `short_pressure.confidence_note_en` / `_zh`
- `valuation.note_en` / `_zh`
- `valuation.confidence_note_en` / `_zh`
- `revisions.note_en` / `_zh`
- `revisions.confidence_note_en` / `_zh`
- `next_catalyst.label_en` / `_zh`
- `next_catalyst.confidence_note_en` / `_zh`
- `support_confidence.zones[*].reasons_en` / `_zh` (parallel arrays of equal length)
- `support_confidence.confidence_note_en` / `_zh`
- `fragility.drivers_en` / `_zh` (parallel arrays of equal length)
- `fragility.confidence_note_en` / `_zh`
- `repricing_risk.note_en` / `_zh`
- `repricing_risk.confidence_note_en` / `_zh`

Numeric / enum fields are language-neutral. Card section labels
("Anchored cost basis", "Float turnover (heat zones)", "Holder
mix", etc.) live in app-side i18n dictionaries (`AppCopy` /
`TraderCopy` on iOS, `i18n.js` on web).

Vocabulary guide (mirrors the existing trader prompt):

- 看涨 / 看跌 / 中性 (trend)
- 强力买入 / 买入 / 持有 / 卖出 / 强力卖出 (consensus)
- 上调 / 下调 / 首次覆盖 / 重申 (rating actions)
- 财报 / 指引 / 监管 / 会议 / 产品 / 法律 / 分红 (catalyst types)
- 持仓结构 (Positioning Structure — card title)
- 锚定成本 (anchored cost basis)
- 换手区 (float turnover zone)
- 持有人结构 (holder mix)
- 期权情绪 / 期权结构 (options regime)
- 空头压力 (short pressure)
- 估值压缩 (valuation compression)
- 业绩修正 (estimate revisions)
- 即将到来的催化剂 (next catalyst)
- 支撑置信度 (support confidence)
- 脆弱度 (fragility)
- 重估风险 (repricing risk)

---

## 8. Rollout

1. **Server**: add `_CONFIDENCE` constant, replace `heat_card`
   in `SCHEMA`, rewrite the heat-card paragraph in
   `SYSTEM_PROMPT` (instructs declarative confidence + reason
   + bilingual). Stamp `schema_version: 2` in
   `_run_trader_snapshot_job`. Add startup migration sweep. Add
   `?force=true` query param.
2. **Web**: rebuild the heat block in `TraderView.vue` around the
   new sections. Add `pickLocalized` consumers for every prose
   field. Add i18n keys. Extend `TraderView.spec.js` with
   sparse / partial / full / null fixtures.
3. **iOS**: in `ResearchModels.swift`, replace `TraderHeatCard`
   with new typed structures (one per sub-object) plus bilingual
   accessors and confidence helpers. Rebuild
   `TraderHeatCardView` in `CompanyDetailView.swift` around the
   new sections. Extend `BSHResearchTests/TraderSnapshotDecodeTests`
   with new fixtures.
4. **Docs**: update `BILINGUAL_TRADER_IMPLEMENTATION.md` field
   inventory; this file (`heat-card-v2.md`) is the canonical spec.
5. **Sweep**: audit for any remaining hard-coded English in
   `TraderView.vue`, `CompanyDetailView.swift`, and adjacent
   files; lift everything through the localized accessor or
   i18n dictionary.

All migrations should be reversible via `git revert`; data on
disk is regenerated on next Refresh.
