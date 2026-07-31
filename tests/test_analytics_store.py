from __future__ import annotations

from server import analytics_store, storage


def test_parse_ts_roundtrip():
    parsed = analytics_store._parse_ts("2026-07-30T10:00:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.isoformat() == "2026-07-30T10:00:00+00:00"


def test_parse_ts_rejects_empty_and_garbage():
    assert analytics_store._parse_ts(None) is None
    assert analytics_store._parse_ts("") is None
    assert analytics_store._parse_ts("not-a-date") is None


def test_summary_time_to_first_memo(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")

    analytics_store.record_event("search_started", company_id="acme")
    # Overwrite timestamps to a known 30-minute gap.
    events_path = analytics_store._events_file()
    lines = events_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    events_path.write_text(
        lines[0].replace(
            lines[0].split('"ts": "')[1].split('"')[0],
            "2026-07-30T10:00:00+00:00",
        )
        + "\n",
        encoding="utf-8",
    )
    analytics_store.record_event("memo_first_draft_ready", company_id="acme")
    lines = events_path.read_text(encoding="utf-8").strip().splitlines()
    events_path.write_text(
        lines[0]
        + "\n"
        + lines[1].replace(
            lines[1].split('"ts": "')[1].split('"')[0],
            "2026-07-30T10:30:00+00:00",
        )
        + "\n",
        encoding="utf-8",
    )

    metric = analytics_store.summary()["time_to_first_memo"]
    assert metric["company_count"] == 1
    assert metric["median_minutes"] == 30.0
