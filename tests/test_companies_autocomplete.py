from __future__ import annotations

from server import companies_autocomplete


def test_edgar_ticker_suggestions_are_marked_public(monkeypatch):
    monkeypatch.setattr(companies_autocomplete.storage, "search_companies", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(companies_autocomplete, "_load_researched", lambda: [])
    monkeypatch.setattr(
        companies_autocomplete,
        "_load_edgar_index",
        lambda: [
            {
                "ticker": "PTCO",
                "ticker_lower": "ptco",
                "name": "PUBLIC TICKER CO",
                "name_lower": "public ticker co",
                "cik": 123456,
            }
        ],
    )

    results = companies_autocomplete.autocomplete("PTCO", limit=3)

    assert results[0]["ticker"] == "PTCO"
    assert results[0]["company_type"] == "public"
    assert results[0]["status"] == "public"
