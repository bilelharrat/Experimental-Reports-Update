"""The shared cadence bar for every background job that spends tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from server import auto_update, news_brief, storage, tracking_updates
from server.main import app


def test_the_bar_offers_the_same_five_choices_everywhere():
    assert list(auto_update.CADENCES) == ["manual", "6h", "12h", "1d", "3d"]
    assert auto_update.CADENCE_HOURS == {
        "manual": 0.0,
        "6h": 6.0,
        "12h": 12.0,
        "1d": 24.0,
        "3d": 72.0,
    }
    for row in auto_update.list_channels():
        assert row["choices"] == list(auto_update.CADENCES)
        assert row["label"]["en"] and row["label"]["zh"]


def test_every_token_spending_loop_is_registered():
    """A new background job that calls Claude belongs on the bar."""
    assert set(auto_update.CHANNELS) == {"news_brief", "tracked_news"}
    assert news_brief.AUTO_UPDATE_CHANNEL == "news_brief"
    assert tracking_updates.AUTO_UPDATE_CHANNEL == "tracked_news"


def test_everything_is_manual_until_someone_turns_it_on(monkeypatch):
    """The owner's rule: nothing spends on a schedule out of the box."""
    monkeypatch.delenv("BSH_NEWS_BRIEF_REFRESH_HOURS", raising=False)
    monkeypatch.delenv("BSH_TRACKING_SYNC_INTERVAL_SECONDS", raising=False)
    for channel_id in auto_update.CHANNELS:
        assert auto_update.cadence(channel_id) == "manual"
        assert auto_update.interval_hours(channel_id) == 0.0
        assert auto_update.next_run_at(channel_id) is None
    assert news_brief.refresh_interval_hours() == 0.0
    assert tracking_updates.sync_interval_seconds() == 0.0


def test_env_supplies_the_default_and_a_choice_overrides_it(monkeypatch):
    monkeypatch.setenv("BSH_NEWS_BRIEF_REFRESH_HOURS", "12")
    assert auto_update.cadence("news_brief") == "12h"

    auto_update.set_cadence("news_brief", "3d", updated_by="owner@example.com")
    assert auto_update.cadence("news_brief") == "3d"
    assert auto_update.interval_hours("news_brief") == 72.0
    assert news_brief.refresh_interval_hours() == 72.0

    row = auto_update.describe("news_brief")
    assert row["updated_by"] == "owner@example.com"
    assert row["updated_at"]


def test_an_env_value_off_the_bar_reads_as_custom(monkeypatch):
    monkeypatch.setenv("BSH_TRACKING_SYNC_INTERVAL_SECONDS", "900")
    assert auto_update.cadence("tracked_news") == "custom"
    assert auto_update.interval_hours("tracked_news") == 0.25


def test_manual_never_fires_and_never_reports_a_next_run():
    auto_update.set_cadence("news_brief", "manual")
    auto_update.set_cadence("tracked_news", "manual")

    assert auto_update.next_run_at("news_brief") is None
    assert auto_update.seconds_until_due("news_brief") is None
    assert news_brief.next_refresh_at() is None
    assert news_brief.refresh_status()["cadence"] == "manual"

    assert tracking_updates.sync_interval_seconds() == 0.0
    assert tracking_updates.seconds_until_sync_due() is None
    settings = tracking_updates.get_settings()
    assert settings["cadence"] == "manual"
    assert settings["next_sync_at"] is None


def test_starting_the_server_does_not_make_anything_due(monkeypatch):
    """The owner's rule: booting must not cost tokens.

    Even with a cadence turned on, a server that has never run waits a
    full interval instead of firing at startup."""
    monkeypatch.delenv("BSH_NEWS_BRIEF_REFRESH_HOURS", raising=False)
    monkeypatch.delenv("BSH_TRACKING_SYNC_INTERVAL_SECONDS", raising=False)
    auto_update.set_cadence("news_brief", "6h")
    auto_update.set_cadence("tracked_news", "12h")

    assert news_brief.last_refresh_at() is None
    assert news_brief.seconds_until_due() > 5 * 3600
    assert tracking_updates.last_sync_at() is None
    assert tracking_updates.seconds_until_sync_due() > 11 * 3600

    news_brief.start_clock_if_unset()
    tracking_updates.start_clock_if_unset()
    assert news_brief.last_refresh_at() is not None
    assert tracking_updates.last_sync_at() is not None
    assert news_brief.seconds_until_due() > 5 * 3600
    assert tracking_updates.seconds_until_sync_due() > 11 * 3600


def test_a_stored_choice_changes_the_next_run(monkeypatch):
    an_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    tracking_updates._mark_synced(an_hour_ago)

    auto_update.set_cadence("tracked_news", "6h")
    wait = tracking_updates.seconds_until_sync_due()
    assert 5 * 3600 - 60 < wait <= 5 * 3600

    auto_update.set_cadence("tracked_news", "3d")
    wait = tracking_updates.seconds_until_sync_due()
    assert 71 * 3600 - 60 < wait <= 71 * 3600


def test_unknown_channel_and_unknown_cadence_are_rejected():
    try:
        auto_update.set_cadence("news_brief", "every-hour")
    except ValueError as exc:
        assert "manual" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an off-bar cadence must be rejected")

    try:
        auto_update.channel("nope")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("an unknown channel must be rejected")


def test_api_lists_and_sets_the_bar(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    client = TestClient(app)

    listed = client.get("/api/auto-updates")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["choices"] == list(auto_update.CADENCES)
    ids = {row["id"] for row in payload["channels"]}
    assert ids == {"news_brief", "tracked_news"}

    saved = client.put("/api/auto-updates/news_brief", json={"cadence": "1d"})
    assert saved.status_code == 200
    assert saved.json()["cadence"] == "1d"
    assert news_brief.refresh_interval_hours() == 24.0

    assert client.put(
        "/api/auto-updates/news_brief", json={"cadence": "hourly"}
    ).status_code == 400
    assert client.put(
        "/api/auto-updates/nope", json={"cadence": "1d"}
    ).status_code == 404
