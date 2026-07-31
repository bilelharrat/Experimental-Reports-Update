const FIELD_KEYS = {
  "Last price": "trader_stats.field_last_price",
  "1d move": "trader_stats.field_1d_move",
  "30d move": "trader_stats.field_30d_move",
  "MA crossover": "trader_stats.field_ma_crossover",
  "Short interest % float": "trader_stats.field_short_interest",
  "Days to cover": "trader_stats.field_days_to_cover",
  "Short trend": "trader_stats.field_short_trend",
  "EV/Revenue": "trader_stats.field_ev_revenue",
  PEG: "trader_stats.field_peg",
  "Fragility score": "trader_stats.field_fragility_score",
  "Next catalyst": "trader_stats.field_next_catalyst",
};

const VALUE_KEYS = {
  golden_cross: "trader_stats.value_golden_cross",
  death_cross: "trader_stats.value_death_cross",
  flat: "trader_stats.value_flat",
  rising: "trader_stats.value_rising",
  falling: "trader_stats.value_falling",
};

const LIST_DELTA_KEYS = {
  "Catalysts added": "trader_stats.delta_catalysts_added",
  "Catalysts removed": "trader_stats.delta_catalysts_removed",
  "Trader news added": "trader_stats.delta_news_added",
  "Trader news removed": "trader_stats.delta_news_removed",
};

function localizedValue(value, t) {
  if (value == null) return t("trader_stats.value_none");
  if (typeof value === "boolean") {
    return t(value ? "trader_stats.value_yes" : "trader_stats.value_no");
  }
  const key = VALUE_KEYS[String(value).toLowerCase()];
  return key ? t(key) : String(value);
}

function deltaCount(value) {
  const datedItems = String(value || "").match(/\d{4}-\d{2}-\d{2}:/g);
  return datedItems?.length || 1;
}

export function localizedChangeHighlights(record, language, t) {
  const summary = record?.change_summary || {};
  const original = Array.isArray(summary.highlights) ? summary.highlights : [];
  if (language !== "zh") return original;

  const rows = [];
  const fieldChanges = Array.isArray(summary.field_changes)
    ? summary.field_changes
    : [];
  for (const change of fieldChanges) {
    const fieldKey = FIELD_KEYS[change?.field];
    if (!fieldKey) continue;
    const label = t(fieldKey);
    if (
      change.field === "Next catalyst" &&
      (typeof change.before === "string" || typeof change.after === "string")
    ) {
      rows.push(t("trader_stats.field_updated", { field: label }));
      continue;
    }
    rows.push(
      t("trader_stats.field_change", {
        field: label,
        before: localizedValue(change.before, t),
        after: localizedValue(change.after, t),
      }),
    );
  }

  for (const highlight of original) {
    const separator = String(highlight).indexOf(":");
    if (separator < 0) continue;
    const prefix = String(highlight).slice(0, separator);
    const key = LIST_DELTA_KEYS[prefix];
    if (!key) continue;
    rows.push(t(key, { count: deltaCount(String(highlight).slice(separator + 1)) }));
  }

  if (!rows.length && original.length) {
    return [t("trader_stats.no_localized_change_detail")];
  }
  return rows;
}
