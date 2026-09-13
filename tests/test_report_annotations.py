"""Account-scoped memo annotation sync (PKDrawing + PNG overlay)."""
from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from server import annotation_store, storage
from server.main import app


def _seed_report() -> str:
    report = storage.create_report_record(
        company_id="acme",
        kind="investment_memo",
        title="Acme memo",
        status="complete",
    )
    return report["id"]


def test_annotation_store_roundtrip_and_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(annotation_store, "ANNOTATIONS_ROOT", tmp_path / "ann")
    drawing = b"pk-drawing-bytes"
    overlay = b"\x89PNG\r\n\x1a\n" + b"fake"

    saved = annotation_store.save(
        "analyst@bsh.com",
        "rep-1",
        drawing_pk_base64=base64.b64encode(drawing).decode("ascii"),
        overlay_png_base64=base64.b64encode(overlay).decode("ascii"),
        canvas_width=612,
        canvas_height=1600,
    )
    assert saved["has_drawing_pk"] is True
    assert saved["has_overlay"] is True
    assert saved["updated_at"]
    assert saved["canvas_width"] == 612

    loaded = annotation_store.get("analyst@bsh.com", "rep-1", include_drawing=True)
    assert base64.b64decode(loaded["drawing_pk_base64"]) == drawing
    assert annotation_store.overlay_file("analyst@bsh.com", "rep-1") is not None

    # Different account is isolated.
    other = annotation_store.get("other@bsh.com", "rep-1")
    assert other["has_drawing_pk"] is False

    cleared = annotation_store.save("analyst@bsh.com", "rep-1", clear=True)
    assert cleared["cleared"] is True
    assert cleared["has_drawing_pk"] is False
    assert annotation_store.overlay_file("analyst@bsh.com", "rep-1") is None
    tombstone = annotation_store.get("analyst@bsh.com", "rep-1")
    assert tombstone["cleared"] is True
    assert tombstone["updated_at"]


def test_report_annotations_api_put_get_overlay_delete():
    report_id = _seed_report()
    client = TestClient(app)
    drawing_b64 = base64.b64encode(b"pencilkit-blob").decode("ascii")
    overlay_b64 = base64.b64encode(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
        )
    ).decode("ascii")

    empty = client.get(f"/api/reports/{report_id}/annotations")
    assert empty.status_code == 200, empty.text
    assert empty.json()["has_drawing_pk"] is False

    put = client.put(
        f"/api/reports/{report_id}/annotations",
        json={
            "drawing_pk_base64": drawing_b64,
            "overlay_png_base64": overlay_b64,
            "canvas_width": 612.0,
            "canvas_height": 900.0,
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["has_drawing_pk"] is True
    assert body["has_overlay"] is True
    assert body["overlay_url"] == f"/api/reports/{report_id}/annotations/overlay.png"
    assert body["updated_at"]

    got = client.get(
        f"/api/reports/{report_id}/annotations",
        params={"include_drawing": "true", "include_overlay": "false"},
    )
    assert got.status_code == 200
    assert got.json()["drawing_pk_base64"] == drawing_b64

    overlay = client.get(f"/api/reports/{report_id}/annotations/overlay.png")
    assert overlay.status_code == 200
    assert overlay.headers["content-type"].startswith("image/png")
    assert overlay.content.startswith(b"\x89PNG")

    deleted = client.delete(f"/api/reports/{report_id}/annotations")
    assert deleted.status_code == 204
    after = client.get(f"/api/reports/{report_id}/annotations")
    assert after.status_code == 200
    assert after.json()["cleared"] is True
    assert after.json()["has_drawing_pk"] is False
    missing = client.get(f"/api/reports/{report_id}/annotations/overlay.png")
    assert missing.status_code == 404


def test_report_annotations_require_existing_report():
    client = TestClient(app)
    res = client.get("/api/reports/does-not-exist/annotations")
    assert res.status_code == 404
