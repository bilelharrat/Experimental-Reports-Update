/** Shared company grouping and sort for Tracking and the sidebar Companies list. */

export function companyBucket(company) {
  const type = String(company?.company_type || "").toLowerCase();
  const status = String(company?.status || "").toLowerCase();
  if (type === "public" || status === "public" || String(company?.ticker || "").trim()) {
    return "watchlist";
  }
  const explicit = String(
    company?.investment_bucket || company?.bucket || company?.pipeline_stage || "",
  ).toLowerCase();
  if (explicit.includes("watch") || explicit.includes("top")) return "watchlist";
  return "portfolio";
}

export function companyStatusLine(company, t) {
  const translated = company?.translation || {};
  return (
    translated.industry ||
    translated.sector ||
    company?.industry ||
    company?.sector ||
    (company?.company_type === "public" || company?.status === "public"
      ? t("sidebar.public_equity")
      : company?.company_type === "private" || company?.status === "private"
        ? t("sidebar.private_company")
        : "")
  );
}

export function sortCompanies(
  companies,
  { sort = "az", views = {}, favorites = new Set() } = {},
) {
  const favs = favorites instanceof Set ? favorites : new Set(favorites);
  const rows = (companies || [])
    .filter((company) => company?.id)
    .map((company, index) => ({ company, index }));

  const byName = (a, b) =>
    String(a.company.name || "").localeCompare(String(b.company.name || ""));
  const stamp = (row) =>
    String(row.company.created_at || row.company.added_at || "");
  const byNewest = (a, b) => stamp(b).localeCompare(stamp(a)) || b.index - a.index;
  const byViews = (a, b) =>
    (Number(views[b.company.id]) || 0) - (Number(views[a.company.id]) || 0) ||
    byName(a, b);

  const cmp =
    sort === "newest"
      ? byNewest
      : sort === "oldest"
        ? (a, b) => -byNewest(a, b)
        : sort === "views"
          ? byViews
          : sort === "za"
            ? (a, b) => -byName(a, b)
            : byName;

  rows.sort((a, b) => {
    const favDelta =
      Number(favs.has(String(b.company.id))) - Number(favs.has(String(a.company.id)));
    return favDelta || cmp(a, b);
  });
  return rows.map((row) => row.company);
}

export function relatedNews(news = [], companies = [], limit = 8) {
  if (!companies.length) return [];
  const needles = companies
    .flatMap((company) => [company.name, company.ticker])
    .filter(Boolean)
    .map((needle) => String(needle).toLowerCase());
  return [...news]
    .filter((item) => {
      if (!item?.id) return false;
      const hay =
        `${item.title || ""} ${item.summary || ""} ${item.company || ""}`.toLowerCase();
      return needles.some((needle) => needle && hay.includes(needle));
    })
    .sort((a, b) =>
      String(b.captured_at || "").localeCompare(String(a.captured_at || "")),
    )
    .slice(0, limit);
}

export function latestNewsFor(news = [], company) {
  return relatedNews(news, company ? [company] : [], 1)[0] || null;
}

export function priceSignal(company) {
  const snap = company?.trader_snapshot;
  const raw =
    snap?.price_card?.change_pct_1d ??
    snap?.price?.change_pct_1d ??
    company?.change_pct_1d;
  const n = Number(raw);
  if (!Number.isFinite(n)) return { dir: "flat", value: null };
  return { dir: n > 0 ? "up" : n < 0 ? "down" : "flat", value: n };
}
