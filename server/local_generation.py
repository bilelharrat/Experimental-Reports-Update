"""Generate server-local runtime state from Git-tracked seeds.

The application keeps mutable runtime data under ignored ``data/`` paths.
This module is the deterministic bridge from repository data to local server
state, so startup and operators can run the same idempotent materialization.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from . import auth_store, memo_prep, stock_research, storage, trader_stats


def generate_local_runtime_state(
    *,
    include_users: bool = True,
    include_stock_research: bool = True,
    include_trader_stats: bool = False,
    include_fixture_companies: bool = False,
) -> dict[str, Any]:
    """Materialize Git-tracked seeds into ignored runtime storage.

    The default mirrors server startup and intentionally avoids generating
    trader-stat baseline rows. Those baselines are derived from local public
    trader snapshots and are still created on demand by the Trader Stats view.
    """
    storage.bootstrap_seed_data()
    company_records_materialized = storage.materialize_seed_company_records(
        include_fixtures=include_fixture_companies,
    )
    memo_prep.ensure_settings_file()

    summary: dict[str, Any] = {
        "data_dir": str(storage.DATA_DIR),
        "companies_file": str(storage.COMPANIES_FILE),
        "company_records_materialized": company_records_materialized,
        "company_count": len(storage.list_companies()),
        "fixture_companies_included": include_fixture_companies,
    }

    if include_users:
        auth_store.bootstrap_seed_users()
        summary["users_file"] = str(auth_store.USERS_FILE)
        summary["users_bootstrapped"] = True
    else:
        summary["users_bootstrapped"] = False

    if include_stock_research:
        trackers = stock_research.seed_tracker_registry()
        summary["stock_research_root"] = str(stock_research.STOCK_RESEARCH_ROOT)
        summary["stock_research_tracker_count"] = len(trackers)
    else:
        summary["stock_research_tracker_count"] = None

    if include_trader_stats:
        summary["trader_stat_baselines_created"] = trader_stats.seed_baseline_records(
            storage.list_companies(),
        )
    else:
        summary["trader_stat_baselines_created"] = None

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate ignored server-local runtime state from tracked seeds.",
    )
    parser.add_argument(
        "--skip-users",
        action="store_true",
        help="Do not seed local login users.",
    )
    parser.add_argument(
        "--skip-stock-research",
        action="store_true",
        help="Do not seed stock-research tracker metadata.",
    )
    parser.add_argument(
        "--include-trader-stats",
        action="store_true",
        help="Also derive initial trader-stat rows from existing public snapshots.",
    )
    parser.add_argument(
        "--include-fixture-companies",
        action="store_true",
        help="Also materialize deterministic QA fixture companies.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a human summary.",
    )
    args = parser.parse_args(argv)

    summary = generate_local_runtime_state(
        include_users=not args.skip_users,
        include_stock_research=not args.skip_stock_research,
        include_trader_stats=args.include_trader_stats,
        include_fixture_companies=args.include_fixture_companies,
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    print("Generated local runtime state:")
    for key in sorted(summary):
        print(f"- {key}: {summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
