"""Optional optimistic concurrency on PUT /api/desk/prefs.

``base_updated_at`` lets a client (web deskSync, the Mac desk outbox) say
which server copy its edit was based on. A stale base is refused with 409 so
the client re-pulls and merges instead of overwriting an edit made on another
device; omitting the field keeps the unconditional save the iPad and the
Settings import rely on.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from server import desk_store
from server.main import app

STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


@pytest.fixture()
def client():
    return TestClient(app)


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def test_matching_base_saves_and_moves_the_stamp(client):
    first = client.put("/api/desk/prefs", json={"data": {"bsh.marketPinnedTickers": ["NVDA"]}})
    assert first.status_code == 200, first.text
    base = first.json()["updated_at"]

    second = client.put(
        "/api/desk/prefs",
        json={"data": {"bsh.marketPinnedTickers": ["NVDA", "TSLA"]}, "base_updated_at": base},
    )

    assert second.status_code == 200, second.text
    assert second.json()["updated_at"] != base
    assert _parse(second.json()["updated_at"]) > _parse(base)
    assert client.get("/api/desk/prefs").json() == second.json()


def test_stale_base_is_a_409_conflict_and_leaves_the_blob_alone(client):
    stale = client.put("/api/desk/prefs", json={"data": {"bsh.marketPinnedTickers": ["AAPL"]}})
    base = stale.json()["updated_at"]
    newer = client.put("/api/desk/prefs", json={"data": {"bsh.marketPinnedTickers": ["KO"]}})
    stored = newer.json()["updated_at"]

    response = client.put(
        "/api/desk/prefs",
        json={"data": {"bsh.marketPinnedTickers": ["TSLA"]}, "base_updated_at": base},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "desk_prefs_conflict"
    assert detail["updated_at"] == stored
    assert isinstance(detail["message"], str) and detail["message"]
    fetched = client.get("/api/desk/prefs").json()
    assert fetched == {"updated_at": stored, "data": {"bsh.marketPinnedTickers": ["KO"]}}


def test_null_base_means_the_client_saw_an_empty_store(client):
    created = client.put(
        "/api/desk/prefs",
        json={"data": {"bsh.marketPinnedTickers": ["NVDA"]}, "base_updated_at": None},
    )
    assert created.status_code == 200, created.text

    again = client.put(
        "/api/desk/prefs",
        json={"data": {"bsh.marketPinnedTickers": ["SPY"]}, "base_updated_at": None},
    )

    assert again.status_code == 409
    assert again.json()["detail"]["updated_at"] == created.json()["updated_at"]
    assert client.get("/api/desk/prefs").json()["data"] == {"bsh.marketPinnedTickers": ["NVDA"]}


def test_omitting_the_base_keeps_the_unconditional_save(client):
    client.put("/api/desk/prefs", json={"data": {"bsh.marketPinnedTickers": ["AAPL"]}})
    client.put("/api/desk/prefs", json={"data": {"bsh.marketPinnedTickers": ["KO"]}})

    response = client.put("/api/desk/prefs", json={"data": {"bsh.marketPinnedTickers": ["TSLA"]}})

    assert response.status_code == 200, response.text
    assert client.get("/api/desk/prefs").json()["data"] == {"bsh.marketPinnedTickers": ["TSLA"]}


def test_validation_400_wins_over_a_stale_base(client):
    client.put("/api/desk/prefs", json={"data": {"bsh.marketPinnedTickers": ["AAPL"]}})

    response = client.put(
        "/api/desk/prefs",
        json={
            "data": {"bsh.marketPinnedTickers": ["not a ticker"]},
            "base_updated_at": "2000-01-01T00:00:00.000000Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "bsh.marketPinnedTickers[0] must be an upper-case ticker symbol "
        "(letters, digits, '.' or '-')"
    )
    assert client.get("/api/desk/prefs").json()["data"] == {"bsh.marketPinnedTickers": ["AAPL"]}


def test_stamps_strictly_increase_with_six_fractional_digits_on_clock_ties_and_rewinds(monkeypatch):
    frozen = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)  # microsecond == 0
    monkeypatch.setattr(desk_store, "_utcnow", lambda: frozen)
    stamps = [desk_store.save_prefs({"n": 1})["updated_at"]]
    stamps.append(desk_store.save_prefs({"n": 2})["updated_at"])  # clock tie

    earlier = datetime(2026, 9, 14, 9, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(desk_store, "_utcnow", lambda: earlier)
    stamps.append(desk_store.save_prefs({"n": 3})["updated_at"])  # clock went backwards

    assert stamps[0] == "2026-09-14T10:00:00.000000Z"
    for stamp in stamps:
        assert STAMP_RE.match(stamp), stamp
    parsed = [_parse(stamp) for stamp in stamps]
    assert parsed[0] < parsed[1] < parsed[2]
    assert desk_store.load_prefs()["updated_at"] == stamps[-1]


def test_save_prefs_raises_prefs_conflict_with_the_current_stamp():
    saved = desk_store.save_prefs({"bsh.marketPinnedTickers": ["NVDA"]})

    with pytest.raises(desk_store.PrefsConflict) as caught:
        desk_store.save_prefs({"bsh.marketPinnedTickers": ["TSLA"]}, expected_updated_at="x")

    assert caught.value.current_updated_at == saved["updated_at"]
    assert desk_store.load_prefs() == saved
    # The matching stamp goes through (and the lock was released after the conflict).
    after = desk_store.save_prefs(
        {"bsh.marketPinnedTickers": ["TSLA"]}, expected_updated_at=saved["updated_at"]
    )
    assert after["data"] == {"bsh.marketPinnedTickers": ["TSLA"]}


def test_legacy_stamp_without_a_fraction_still_gets_a_later_stamp(monkeypatch):
    legacy = "2026-09-14T10:00:00Z"
    desk_store.DESK_ROOT.mkdir(parents=True, exist_ok=True)
    (desk_store.DESK_ROOT / desk_store.PREFS_FILE).write_text(
        json.dumps({"updated_at": legacy, "data": {"bsh.marketPinnedTickers": ["AAPL"]}}),
        encoding="utf-8",
    )
    # The server clock reads the same second as the legacy stamp.
    monkeypatch.setattr(
        desk_store, "_utcnow", lambda: datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)
    )

    saved = desk_store.save_prefs({"bsh.marketPinnedTickers": ["NVDA"]}, expected_updated_at=legacy)

    assert saved["updated_at"] == "2026-09-14T10:00:00.000001Z"
    assert _parse(saved["updated_at"]) > _parse(legacy)
