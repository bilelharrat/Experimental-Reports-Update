"""The company news sweep: grounded research appended to the record feed."""
from __future__ import annotations

import pytest

from server import company_news_research, storage

COMPANY = {
    "id": "acme",
    "name": "Acme Robotics",
    "status": "private",
    "website": "https://acme.example",
    "description": "Warehouse automation.",
    "recent_news": [
        {
            "headline": "Acme raises $40M Series B",
            "date": "2026-06-01",
            "url": "https://techcrunch.com/acme-series-b",
        }
    ],
}

META = {
    "engine": "gemini",
    "model": "gemini-3.8-flash",
    "sources": [{"title": "Reuters", "url": "https://reuters.com/acme"}],
    "queries": ["Acme Robotics news"],
    "fallback_reason": None,
}


@pytest.fixture
def company():
    storage._write_yaml(storage.COMPANIES_FILE, [dict(COMPANY)])
    return dict(COMPANY)


def _stub(monkeypatch, data, meta=None, error=None):
    calls: list[dict] = []

    def grounded(**kwargs):
        calls.append(kwargs)
        return data, (meta if meta is not None else META), error

    monkeypatch.setattr(company_news_research.ai_engine, "grounded", grounded)
    return calls


def _item(**over):
    base = {
        "headline": "Acme signs Maersk as launch customer",
        "summary": "Multi-year deal across four ports.",
        "date": "2026-09-10",
        "url": "https://reuters.com/acme-maersk",
        "source": "Reuters",
        "category": "partnership",
    }
    base.update(over)
    return base


# ---- happy path -----------------------------------------------------------


def test_new_items_land_on_the_feed_and_the_record(monkeypatch, company):
    _stub(monkeypatch, {"items": [_item()]})
    feed = company_news_research.sweep_company_news("acme")

    assert feed["sweep"]["added"] == 1
    assert feed["sweep"]["engine"] == "gemini"
    assert feed["sweep"]["sources"] == META["sources"]
    titles = [row["title"] for row in feed["rows"]]
    assert "Acme signs Maersk as launch customer" in titles

    stored = storage.get_company("acme")["recent_news"]
    assert [row["headline"] for row in stored] == [
        "Acme signs Maersk as launch customer",
        "Acme raises $40M Series B",
    ]
    assert stored[0]["origin"] == "news_sweep"


def test_the_prompt_lists_what_the_desk_already_has(monkeypatch, company):
    calls = _stub(monkeypatch, {"items": []})
    company_news_research.sweep_company_news("acme")
    prompt = calls[0]["user_prompt"]
    assert "Acme Robotics" in prompt
    assert "Acme raises $40M Series B (2026-06-01)" in prompt
    assert "do not return these again" in prompt


def test_unknown_company_raises(company):
    with pytest.raises(ValueError):
        company_news_research.sweep_company_news("nope")


# ---- what the merge refuses to do -----------------------------------------


def test_existing_rows_are_never_edited_or_dropped(monkeypatch, company):
    _stub(
        monkeypatch,
        {
            "items": [
                # Same story, rewritten headline and a tracking-tagged URL.
                _item(
                    headline="ACME RAISES $40 MILLION SERIES B",
                    url="https://techcrunch.com/acme-series-b?utm_source=x",
                    date="2026-06-02",
                )
            ]
        },
    )
    feed = company_news_research.sweep_company_news("acme")
    assert feed["sweep"]["added"] == 0
    stored = storage.get_company("acme")["recent_news"]
    assert stored == COMPANY["recent_news"]


def test_duplicate_headlines_without_urls_are_dropped(monkeypatch, company):
    _stub(monkeypatch, {"items": [_item(headline="Acme raises $40M Series B!", url="")]})
    feed = company_news_research.sweep_company_news("acme")
    assert feed["sweep"]["added"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"headline": "No date at all"},
        {"headline": "Vague date", "date": "September 2026"},
        {"headline": "", "date": "2026-09-10"},
        "not a dict",
    ],
)
def test_undated_and_headless_items_are_dropped(monkeypatch, company, bad):
    _stub(monkeypatch, {"items": [bad]})
    feed = company_news_research.sweep_company_news("acme")
    assert feed["sweep"]["added"] == 0
    assert storage.get_company("acme")["recent_news"] == COMPANY["recent_news"]


def test_non_http_urls_are_not_stored(monkeypatch, company):
    _stub(monkeypatch, {"items": [_item(url="javascript:alert(1)")]})
    company_news_research.sweep_company_news("acme")
    stored = storage.get_company("acme")["recent_news"][0]
    assert "url" not in stored


def test_an_unknown_category_is_dropped_rather_than_stored(monkeypatch, company):
    _stub(monkeypatch, {"items": [_item(category="gossip")]})
    company_news_research.sweep_company_news("acme")
    assert "category" not in storage.get_company("acme")["recent_news"][0]


def test_the_batch_is_capped(monkeypatch, company):
    items = [
        _item(headline=f"Acme development {n}", url=f"https://reuters.com/acme-{n}", date="2026-09-01")
        for n in range(company_news_research.MAX_NEW_ROWS + 15)
    ]
    _stub(monkeypatch, {"items": items})
    feed = company_news_research.sweep_company_news("acme")
    assert feed["sweep"]["added"] == company_news_research.MAX_NEW_ROWS


def test_rows_are_stored_newest_first(monkeypatch, company):
    _stub(
        monkeypatch,
        {
            "items": [
                _item(headline="Older", url="https://r.example/1", date="2026-01-05"),
                _item(headline="Newest", url="https://r.example/2", date="2026-09-15"),
            ]
        },
    )
    company_news_research.sweep_company_news("acme")
    dates = [row["date"] for row in storage.get_company("acme")["recent_news"]]
    assert dates == sorted(dates, reverse=True)


# ---- the translation hazard ----------------------------------------------


def test_a_changed_list_invalidates_the_index_aligned_zh_cache(monkeypatch, company):
    """`translation.recent_news` is aligned to `recent_news` by index, so
    appending rows without clearing it captions new headlines with unrelated
    Chinese."""
    record = dict(COMPANY)
    record["translation"] = {
        "recent_news": [{"headline": "艾克média A轮", "summary": "旧的摘要"}],
        "description": "仓储自动化",
    }
    storage._write_yaml(storage.COMPANIES_FILE, [record])

    _stub(monkeypatch, {"items": [_item()]})
    company_news_research.sweep_company_news("acme")

    translation = storage.get_company("acme")["translation"]
    assert "recent_news" not in translation
    # Only the misaligned slice goes; the rest of the translation survives.
    assert translation["description"] == "仓储自动化"


def test_an_unchanged_list_keeps_the_zh_cache(monkeypatch, company):
    record = dict(COMPANY)
    record["translation"] = {"recent_news": [{"headline": "艾克méd"}]}
    storage._write_yaml(storage.COMPANIES_FILE, [record])

    _stub(monkeypatch, {"items": []})
    company_news_research.sweep_company_news("acme")
    assert storage.get_company("acme")["translation"]["recent_news"]


# ---- failure --------------------------------------------------------------


def test_a_failed_sweep_returns_the_feed_it_had(monkeypatch, company):
    _stub(monkeypatch, None, {"engine": "gemini"}, "gemini HTTP 503 — unavailable")
    feed = company_news_research.sweep_company_news("acme")
    assert feed["sweep"]["error"] == "gemini HTTP 503 — unavailable"
    assert feed["sweep"]["added"] == 0
    assert [row["title"] for row in feed["rows"]] == ["Acme raises $40M Series B"]
    assert storage.get_company("acme")["recent_news"] == COMPANY["recent_news"]


def test_a_name_collision_note_is_reported(monkeypatch, company):
    _stub(
        monkeypatch,
        {"items": [], "notes": "Most results were about an unrelated Acme Corp."},
    )
    feed = company_news_research.sweep_company_news("acme")
    assert "unrelated Acme Corp" in feed["sweep"]["notes"]
    assert feed["sweep"]["added"] == 0
