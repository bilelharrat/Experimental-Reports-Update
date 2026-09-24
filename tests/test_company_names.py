from __future__ import annotations

from pathlib import Path

from server import companies_autocomplete
from server.company_names import clean_display_name


def test_clean_display_name_strips_edgar_state_tokens():
    assert clean_display_name("Occidental Petroleum Corp /De/") == "Occidental Petroleum Corp"
    assert clean_display_name("OCCIDENTAL PETROLEUM CORP /DE/") == "OCCIDENTAL PETROLEUM CORP"
    assert clean_display_name("Wells Fargo & Company/MN") == "Wells Fargo & Company"
    assert clean_display_name("Foo Holdings /NEW/ /DE/") == "Foo Holdings"
    assert clean_display_name("Crown Castle Inc. /TX/") == "Crown Castle Inc."


def test_clean_display_name_leaves_ordinary_names_alone():
    for name in ("Apple Inc.", "Coca Cola Co", "AT&T Inc.", "3M Co", "Brown-Forman Corp", "中经网数据有限公司"):
        assert clean_display_name(name) == name


def test_clean_display_name_is_one_safe_path_component():
    for raw in ("AC/DC Holdings", "Back\\slash Co", "../etc/passwd", "Tab\tName\x07", "/DE/"):
        cleaned = clean_display_name(raw)
        assert cleaned and Path(cleaned).name == cleaned
        assert "/" not in cleaned and "\\" not in cleaned
        assert not cleaned.startswith(".")
        assert all(ord(ch) >= 32 for ch in cleaned)
    assert clean_display_name(None) == ""
    assert clean_display_name("   ") == ""


def test_edgar_suggestions_carry_the_clean_name(monkeypatch):
    monkeypatch.setattr(companies_autocomplete.storage, "search_companies", lambda *_a, **_k: [])
    monkeypatch.setattr(companies_autocomplete, "_load_researched", lambda: [])
    monkeypatch.setattr(
        companies_autocomplete,
        "_load_edgar_index",
        lambda: [
            {
                "ticker": "OXY",
                "ticker_lower": "oxy",
                "name": "OCCIDENTAL PETROLEUM CORP /DE/",
                "name_lower": "occidental petroleum corp /de/",
                "cik": 797468,
            }
        ],
    )
    results = companies_autocomplete.autocomplete("OXY", limit=3)
    assert results[0]["ticker"] == "OXY"
    assert results[0]["name"] == "Occidental Petroleum Corp"
