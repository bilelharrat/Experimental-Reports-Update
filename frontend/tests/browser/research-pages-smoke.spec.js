import { expect, test } from "@playwright/test";

const marketPulseEmpty = {
  schema_version: 1,
  page_id: "market_pulse",
  generated_at: "2026-06-17T00:00:00+00:00",
  as_of: "2026-06-17",
  status: "empty",
  summary: {
    signal_count: 0,
    empty_state: "Missing latest Stock Research weekly aggregate.",
  },
  source_health: {
    source_trace_count: 0,
    average_source_quality: 0,
  },
  doctor_issues: [
    {
      severity: "error",
      type: "market_pulse_missing_latest_aggregate",
      message: "No Stock Research weekly aggregate exists. Run /api/stock-research/aggregates/run after tracker runs complete.",
    },
  ],
  sections: {
    market_regime: {
      posture: "empty",
      breadth: { positive_signals: 0, negative_signals: 0, neutral_signals: 0 },
      volatility: { status: "placeholder" },
      rates: { status: "placeholder" },
      liquidity: { status: "placeholder" },
    },
    ranked_signals: [],
    theme_heatmap: [],
    changed_since_last_week: {
      previous_period_id: null,
      new_signals: [],
      fading_signals: [],
      revised_conviction: [],
      new_contradictions: [],
    },
    catalyst_calendar: [],
    next_steps: [
      {
        label: "Run Stock Research weekly aggregate",
        method: "POST",
        endpoint: "/api/stock-research/aggregates/run",
        requires: "Completed tracker runs with source traces.",
      },
    ],
  },
};

const traderStats = {
  totals: {
    recorded_count: 1,
    total_tokens: 24000,
    average_change_pct: 4.25,
    failed_section_count: 1,
    cost_usd: 1.23,
  },
  items: [
    {
      company_id: "nvidia",
      ticker: "NVDA",
      company_name: "NVIDIA",
      latest_record: {
        status: "done",
        refreshed_at: "2026-06-17T12:00:00Z",
        duration_ms: 62000,
        cost_usd: 0.42,
        token_usage: {
          total_tokens: 24000,
          by_thread: [{ thread: "heat_card", total_tokens: 12000, duration_ms: 30000 }],
        },
        change_summary: {
          change_pct: 4.25,
          changed_sections: ["heat_card", "research_overview"],
          highlights: ["Heat card changed."],
        },
        failed_sections: [{ thread: "catalysts", error: "Timed out fetching catalysts." }],
      },
      history: [
        {
          recorded_at: "2026-06-17T12:00:00Z",
          duration_ms: 62000,
          cost_usd: 0.42,
          token_usage: { total_tokens: 24000 },
          change_summary: { change_pct: 4.25 },
          failed_sections: [{ thread: "catalysts", error: "Timed out fetching catalysts." }],
        },
      ],
    },
  ],
};

async function mockApi(page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "bsh.research.session",
      JSON.stringify({ token: "research-pages-smoke", expires_at: "2099-01-01T00:00:00Z" }),
    );
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (body) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });

    if (path === "/api/auth/me") return json({ email: "browser@example.com" });
    if (path === "/api/research-pages/market-pulse") return json(marketPulseEmpty);
    if (path === "/api/trader/stats") return json(traderStats);
    if (path === "/api/jobs/active") return json([]);
    return json({});
  });
}

test("empty Signals page preserves the research page frame", async ({ page }) => {
  await mockApi(page);
  await page.goto("/research/research-pages/market-pulse");

  await expect(page.getByRole("heading", { name: "Signals" })).toBeVisible();
  await expect(page.getByText("Missing latest Stock Research weekly aggregate.").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Market Regime" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Theme Heat Map" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Changed Since Last Week" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Catalyst Preview" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Doctor Issues" })).toBeVisible();
  await expect(page.getByText("POST /api/stock-research/aggregates/run")).toBeVisible();

  const hasPageOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(hasPageOverflow).toBe(false);
});

test("Trader Stats removes high-level cost and avoids a status column", async ({ page }) => {
  await mockApi(page);
  await page.goto("/research/trader-stats");

  await expect(page.getByRole("heading", { name: "Stats" })).toBeVisible();
  const topMetrics = page.locator("[aria-live='polite']");
  await expect(topMetrics).toContainText("Symbols");
  await expect(topMetrics).toContainText("Tokens");
  await expect(topMetrics).toContainText("Failed sections");
  await expect(topMetrics).not.toContainText("Cost");
  await expect(page.locator("thead")).not.toContainText("Status");
  await expect(page.getByText("Timed out fetching catalysts.")).toBeVisible();

  const hasPageOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(hasPageOverflow).toBe(false);
});
