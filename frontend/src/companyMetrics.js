const pending = (label, labelKey) => ({
  label,
  label_key: labelKey,
  value: "Unknown",
  source_class: "source pending",
  source_key: "company.metric_pending",
});

const METRIC_LABEL_KEYS = {
  arr: "company.metric_arr",
  "yoy growth": "company.metric_yoy_growth",
  valuation: "company.metric_valuation",
  tam: "company.metric_tam",
};

const SOURCE_LABEL_KEYS = {
  "bsh prd reference package": "company.metric_source_bsh_prd",
  "stealth-exit funding disclosure": "company.metric_source_stealth_funding",
  "bsh market model reference": "company.metric_source_bsh_market_model",
};

export function inferredMetricLabelKey(label) {
  return METRIC_LABEL_KEYS[String(label || "").trim().toLowerCase()] || null;
}

export function inferredMetricSourceKey(label) {
  return SOURCE_LABEL_KEYS[String(label || "").trim().toLowerCase()] || null;
}

function source(label, sourceKey, asOf) {
  return {
    source_class: label,
    source_key: sourceKey,
    ...(asOf ? { as_of: asOf } : {}),
  };
}

function latestRevenueMetrics(company) {
  const earnings = company.latest_earnings || {};
  const disclosure = String(earnings.revenue_yoy || "").trim();
  const revenue = disclosure.match(/\$[\d,.]+\s*[KMBT]?/i)?.[0];
  const growth = disclosure.match(/([+-]?\d+(?:\.\d+)?)%\s*(?:YoY)?/i)?.[1];
  const period = earnings.period || null;

  return {
    revenue: revenue
      ? {
          label: "Quarterly Revenue",
          label_key: "company.metric_quarterly_revenue",
          value: revenue,
          ...source("company earnings", "company.metric_source_earnings", period),
        }
      : pending("Quarterly Revenue", "company.metric_quarterly_revenue"),
    growth: growth
      ? {
          label: "YoY Growth",
          label_key: "company.metric_yoy_growth",
          value: Number(growth),
          ...source("company earnings", "company.metric_source_earnings", period),
        }
      : pending("YoY Growth", "company.metric_yoy_growth"),
  };
}

function publicCompanyMetrics(company) {
  const earnings = latestRevenueMetrics(company);
  const overview = company.trader_snapshot?.research_overview || {};
  const valuation = company.trader_snapshot?.heat_card?.valuation || {};
  const quality = overview.financial_quality || {};
  const operatingMargin = Array.isArray(quality.metrics)
    ? quality.metrics.find((metric) =>
        String(metric.label_en || metric.label || "").toLowerCase().includes("operating margin"),
      )
    : null;

  return [
    earnings.revenue,
    earnings.growth,
    valuation.ev_revenue_current != null
      ? {
          label: "EV / Revenue",
          label_key: "company.metric_ev_revenue",
          value: `${valuation.ev_revenue_current}x`,
          ...source(
            "public-market research",
            "company.metric_source_public_market",
            company.trader_snapshot?.price_card?.as_of,
          ),
        }
      : pending("EV / Revenue", "company.metric_ev_revenue"),
    operatingMargin?.value
      ? {
          label: "Operating Margin",
          label_key: "company.metric_operating_margin",
          value: operatingMargin.value,
          ...source(
            "company filings",
            "company.metric_source_filings",
            overview.financial_quality?.updated_at,
          ),
        }
      : pending("Operating Margin", "company.metric_operating_margin"),
  ];
}

function privateCompanyMetrics(company) {
  const funding = company.latest_funding;
  return [
    pending("ARR", "company.metric_arr"),
    pending("YoY Growth", "company.metric_yoy_growth"),
    funding?.post_money_usd
      ? {
          label: "Valuation",
          label_key: "company.metric_valuation",
          value: funding.post_money_usd,
          ...source("company record", "company.metric_source_record", funding.date),
        }
      : pending("Valuation", "company.metric_valuation"),
    pending("TAM", "company.metric_tam"),
  ];
}

export function companySummaryMetrics(company) {
  const supplied = Array.isArray(company.metrics) ? company.metrics : [];
  if (supplied.length) return supplied;
  const isPublic = company.company_type === "public" || company.status === "public" || company.ticker;
  return isPublic ? publicCompanyMetrics(company) : privateCompanyMetrics(company);
}

function parseNumericMetric(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const text = String(value || "").trim();
  if (!text || /^unknown$/i.test(text)) return null;
  const match = text.match(/([+-]?\d+(?:\.\d+)?)(.*)/);
  if (!match) return null;
  let number = Number(match[1]);
  if (!Number.isFinite(number)) return null;
  const suffix = String(match[2] || "").trim().toUpperCase();
  if (suffix.startsWith("%")) return number;
  if (suffix.startsWith("T")) number *= 1e12;
  else if (suffix.startsWith("B")) number *= 1e9;
  else if (suffix.startsWith("M")) number *= 1e6;
  else if (suffix.startsWith("K")) number *= 1e3;
  return number;
}

/** Return chartable yearly/period series for ARR / YoY when present. */
export function companyMetricHistories(company) {
  const histories = [];
  const supplied = Array.isArray(company?.metric_history) ? company.metric_history : [];
  for (const series of supplied) {
    if (!series || typeof series !== "object") continue;
    const points = Array.isArray(series.points) ? series.points : [];
    const values = points
      .map((point) => ({
        label: String(point?.period || point?.label || point?.year || ""),
        value: parseNumericMetric(point?.value),
      }))
      .filter((point) => point.label && point.value != null);
    if (values.length >= 2) {
      histories.push({
        id: series.id || series.label || values[0].label,
        label: series.label || series.id || "Metric",
        label_key: series.label_key || inferredMetricLabelKey(series.label),
        points: values,
      });
    }
  }

  // Fall back to per-metric history arrays on company.metrics.
  for (const metric of companySummaryMetrics(company)) {
    const points = Array.isArray(metric.history) ? metric.history : [];
    const values = points
      .map((point) => ({
        label: String(point?.period || point?.label || point?.year || ""),
        value: parseNumericMetric(point?.value ?? point),
      }))
      .filter((point) => point.label && point.value != null);
    if (values.length < 2) continue;
    const id = metric.label_key || metric.label;
    if (histories.some((row) => row.id === id)) continue;
    histories.push({
      id,
      label: metric.label,
      label_key: metric.label_key || inferredMetricLabelKey(metric.label),
      points: values,
    });
  }

  return histories.filter((row) => {
    const key = String(row.label_key || row.label || "").toLowerCase();
    return key.includes("arr") || key.includes("yoy") || key.includes("growth") || key.includes("revenue");
  });
}
