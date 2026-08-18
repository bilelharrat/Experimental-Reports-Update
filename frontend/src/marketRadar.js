/** Shared Market Radar rows for the toolbar popover. */

export function marketRadarItems(news = [], research = [], limit = 8) {
  return [...news, ...research]
    .filter((item) => item?.id)
    .sort((a, b) =>
      String(b.captured_at || "").localeCompare(String(a.captured_at || "")),
    )
    .slice(0, limit);
}

export function radarRoute(item) {
  if (item.kind === "external_research") {
    return { name: "external-research", params: { id: item.id } };
  }
  return { name: "external-news", params: { id: item.id } };
}

export function radarAge(iso, t) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return t("sidebar.age_now");
  if (sec < 3600) return t("sidebar.age_minutes", { n: Math.round(sec / 60) });
  if (sec < 86400) return t("sidebar.age_hours", { n: Math.round(sec / 3600) });
  return t("sidebar.age_days", { n: Math.round(sec / 86400) });
}
