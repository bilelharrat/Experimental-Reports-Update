from server import api, external_store


def test_external_feed_omits_missing_and_remote_favicons(tmp_path, monkeypatch):
    monkeypatch.setattr(external_store, "EXTERNAL_ROOT", tmp_path / "external")

    ok_assets = external_store.archive_asset_dir("news", "ok")
    ok_assets.mkdir(parents=True)
    (ok_assets / "icon.ico").write_bytes(b"\x00\x00")

    external_store.write_item(
        "news",
        {
            "id": "ok",
            "kind": "news",
            "status": "ready",
            "title": "Has local icon",
            "source_url": "https://example.com/ok",
            "favicon": "/api/external/news/ok/assets/icon.ico",
            "captured_at": "2026-05-25T01:00:00+00:00",
        },
    )
    external_store.write_item(
        "news",
        {
            "id": "missing",
            "kind": "news",
            "status": "ready",
            "title": "Missing icon",
            "source_url": "https://example.com/missing",
            "favicon": "/api/external/news/missing/assets/missing.ico",
            "captured_at": "2026-05-25T02:00:00+00:00",
        },
    )
    external_store.write_item(
        "news",
        {
            "id": "remote",
            "kind": "news",
            "status": "ready",
            "title": "Remote icon",
            "source_url": "https://example.com/remote",
            "favicon": "https://t3.gstatic.com/faviconV2?url=http://example.com",
            "captured_at": "2026-05-25T03:00:00+00:00",
        },
    )

    feed = {item["id"]: item for item in api.get_external_feed()}

    assert feed["ok"]["favicon"] == "/api/external/news/ok/assets/icon.ico"
    assert feed["missing"]["favicon"] is None
    assert feed["remote"]["favicon"] is None
