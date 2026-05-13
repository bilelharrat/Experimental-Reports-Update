"""Tests for the public/private discriminator + backfill in
server/storage.py (see docs/public-company-trader-view.md §1)."""
from __future__ import annotations

import pytest

from server import storage


@pytest.fixture
def tmp_storage(monkeypatch, tmp_path):
    """Redirect the YAML data dir to a fresh tmp path so tests don't
    touch the project's actual companies.yaml.
    """
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", tmp_path / "threads")
    return tmp_path


# ---- infer_company_type pure rules --------------------------------------


@pytest.mark.parametrize("status,ticker,expected", [
    ("public", None, "public"),
    ("Public", "AAPL", "public"),                    # case insensitive
    ("private", "ANDU", "private"),                  # private w/ tradable rumor → private (status wins)
    ("subsidiary", "", "private"),
    ("nonprofit", None, "private"),
    (None, "NVDA", "public"),                        # null status + ticker → public
    (None, None, "private"),                         # null status, no ticker → private
    ("", " ", "private"),                            # whitespace ticker doesn't count
    ("unknown_status_value", "TSLA", "public"),      # unrecognized status + ticker → ticker wins
    ("unknown_status_value", None, "private"),       # unrecognized + no ticker → default private
])
def test_infer_company_type(status, ticker, expected):
    record = {"status": status, "ticker": ticker}
    assert storage.infer_company_type(record) == expected


# ---- upsert sets company_type -------------------------------------------


def test_upsert_new_public_company_sets_type(tmp_storage):
    company = storage.upsert_company_from_match({
        "name": "Advanced Micro Devices, Inc.",
        "ticker": "AMD",
        "status": "public",
        "exchange": "NASDAQ",
    })
    assert company["company_type"] == "public"
    # And persisted to disk.
    assert storage.get_company(company["id"])["company_type"] == "public"


def test_upsert_new_private_company_sets_type(tmp_storage):
    company = storage.upsert_company_from_match({
        "name": "Anduril Industries",
        "status": "private",
    })
    assert company["company_type"] == "private"


def test_upsert_null_status_with_ticker_buckets_public(tmp_storage):
    """Deep-search occasionally leaves status null; ticker presence still
    routes it to the trader view."""
    company = storage.upsert_company_from_match({
        "name": "NVIDIA Corporation",
        "ticker": "NVDA",
        "status": None,
    })
    assert company["company_type"] == "public"


def test_upsert_existing_company_refreshes_type(tmp_storage):
    """A previously-typed record gets its company_type re-derived on the
    next upsert so going public (or being reclassified) reflows."""
    first = storage.upsert_company_from_match({
        "name": "Foo Co",
        "status": "private",
    })
    assert first["company_type"] == "private"
    # Now imagine the company IPO'd and deep-search returns a ticker.
    second = storage.upsert_company_from_match({
        "name": "Foo Co",
        "ticker": "FOO",
        "status": "public",
        "exchange": "NYSE",
    })
    assert second["id"] == first["id"]  # same record
    assert second["company_type"] == "public"


# ---- backfill -----------------------------------------------------------


def _seed_legacy_records():
    """Direct YAML write that bypasses upsert — simulates a companies.yaml
    on disk that predates the company_type field."""
    return [
        {"id": "amd", "name": "AMD", "ticker": "AMD", "status": "public"},
        {"id": "anduril", "name": "Anduril", "status": "private"},
        {"id": "msft", "name": "Microsoft", "ticker": "MSFT"},          # null status
        {"id": "no_ticker", "name": "Quiet Co"},                         # null status + ticker
        {"id": "already_typed", "name": "Tag", "ticker": "TAG",
         "company_type": "public"},                                       # untouched
    ]


def test_backfill_idempotent(tmp_storage):
    storage._write_yaml(storage.COMPANIES_FILE, _seed_legacy_records())
    storage.bootstrap_seed_data()
    after = storage.list_companies()
    types = {c["id"]: c["company_type"] for c in after}
    assert types == {
        "amd": "public",
        "anduril": "private",
        "msft": "public",
        "no_ticker": "private",
        "already_typed": "public",
    }
    # Run again: nothing changes.
    before_bytes = storage.COMPANIES_FILE.read_bytes()
    storage.bootstrap_seed_data()
    assert storage.COMPANIES_FILE.read_bytes() == before_bytes


def test_backfill_preserves_existing_value(tmp_storage):
    """If a record is already typed, the backfill must not overwrite it
    (even if our rule would have produced a different answer)."""
    storage._write_yaml(storage.COMPANIES_FILE, [
        # A record where status says "public" but someone manually
        # tagged it private (hypothetical edge case). Backfill should
        # leave the manual override alone.
        {"id": "weird", "name": "Weird", "ticker": "WRD",
         "status": "public", "company_type": "private"},
    ])
    storage.bootstrap_seed_data()
    assert storage.get_company("weird")["company_type"] == "private"
