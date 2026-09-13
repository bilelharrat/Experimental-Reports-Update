from __future__ import annotations

from pathlib import Path

from server import push_notify


def test_register_and_notify(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(push_notify, "_STORE_PATH", tmp_path / "device_tokens.json")
    monkeypatch.delenv("BSH_APNS_KEY_ID", raising=False)

    registered = push_notify.register_token(
        "a" * 32,
        platform="ios",
        topics=["brief"],
    )
    assert registered["ok"] is True
    assert push_notify.list_tokens(topic="brief")
    assert not push_notify.list_tokens(topic="memo")

    result = push_notify.notify("brief", "Ready", "KO briefing")
    assert result["configured"] is False
    assert result["recipients"] == 1
