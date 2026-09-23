"""Unit tests for server/console_store.py — §11.1 in the design doc."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from server import attachment_text, console_store


COMPANY = "test_company_id"


# ---- Session creation + listing ----------------------------------------


def test_create_session_round_trip(tmp_consoles):
    meta = console_store.create_session(
        company_id=COMPANY,
        include_background_docs=True,
        include_library_docs=False,
        included_files=[{"id": "abc", "kind": "research", "filename": "deck.pdf"}],
    )
    sid = meta["id"]
    assert meta["status"] == "active"
    assert meta["title"].startswith("Session ·")
    assert meta["claude_session_id"]
    assert meta["output_language"] == "en"  # default
    assert meta["tokens"]["total_cost_usd"] == 0.0
    assert meta["tokens"]["last_turn_usage"] is None

    # Disk side: meta.json and turns.jsonl present, workdir + ask + attachments
    # directories created.
    sdir = console_store.session_dir(COMPANY, sid)
    assert (sdir / "meta.json").exists()
    assert (sdir / "turns.jsonl").exists()
    assert (sdir / "workdir").is_dir()
    assert (sdir / "workdir" / "attachments").is_dir()
    assert (sdir / "ask").is_dir()
    assert (sdir / "attachments").is_dir()

    # Listing returns it.
    sessions = console_store.list_sessions(COMPANY)
    assert [s["id"] for s in sessions] == [sid]


def test_list_sessions_can_hide_copilot(tmp_consoles):
    user = console_store.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
        included_files=[],
    )
    copilot = console_store.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
        included_files=[],
        title="Co-Pilot Inspector",
    )
    console_store.update_meta(
        COMPANY, copilot["id"], session_kind="copilot_quick",
    )
    assert console_store.is_copilot_session(
        console_store.load_meta(COMPANY, copilot["id"])
    )
    all_ids = {s["id"] for s in console_store.list_sessions(COMPANY)}
    assert {user["id"], copilot["id"]}.issubset(all_ids)
    visible = {
        s["id"]
        for s in console_store.list_sessions(COMPANY, include_copilot=False)
    }
    assert user["id"] in visible
    assert copilot["id"] not in visible
    # Co-Pilot sessions don't burn the per-company active cap.
    assert console_store.active_count(COMPANY) == 1


def test_create_session_with_zh_output_language(tmp_consoles):
    meta = console_store.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
        included_files=[], output_language="zh",
    )
    assert meta["output_language"] == "zh"
    # Persists across a reload.
    refreshed = console_store.load_meta(COMPANY, meta["id"])
    assert refreshed["output_language"] == "zh"


def test_create_session_rejects_unknown_language(tmp_consoles):
    with pytest.raises(ValueError, match="Unsupported output_language"):
        console_store.create_session(
            company_id=COMPANY,
            include_background_docs=False, include_library_docs=False,
            included_files=[], output_language="fr",
        )


def test_session_limit_enforced(tmp_consoles):
    for _ in range(console_store.MAX_ACTIVE_SESSIONS_PER_COMPANY):
        console_store.create_session(
            company_id=COMPANY,
            include_background_docs=False,
            include_library_docs=False,
            included_files=[],
        )
    with pytest.raises(console_store.SessionLimitReached):
        console_store.create_session(
            company_id=COMPANY,
            include_background_docs=False,
            include_library_docs=False,
            included_files=[],
        )


def test_archive_clears_active_slot(tmp_consoles):
    metas = [
        console_store.create_session(
            company_id=COMPANY,
            include_background_docs=False,
            include_library_docs=False,
            included_files=[],
        )
        for _ in range(console_store.MAX_ACTIVE_SESSIONS_PER_COMPANY)
    ]
    console_store.archive_session(COMPANY, metas[0]["id"])
    assert console_store.active_count(COMPANY) == (
        console_store.MAX_ACTIVE_SESSIONS_PER_COMPANY - 1
    )
    # Can now create another active session.
    console_store.create_session(
        company_id=COMPANY,
        include_background_docs=False,
        include_library_docs=False,
        included_files=[],
    )


# ---- Token accounting ---------------------------------------------------


def test_update_tokens_accumulates(tmp_consoles):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    console_store.update_tokens(
        COMPANY, sid,
        usage={"input_tokens": 100, "output_tokens": 20,
               "cache_read_input_tokens": 200,
               "cache_creation_input_tokens": 50},
        cost_usd=0.05,
    )
    console_store.update_tokens(
        COMPANY, sid,
        usage={"input_tokens": 50, "output_tokens": 10,
               "cache_read_input_tokens": 400,
               "cache_creation_input_tokens": 0},
        cost_usd=0.02,
    )
    meta = console_store.load_meta(COMPANY, sid)
    t = meta["tokens"]
    assert t["input"] == 150
    assert t["output"] == 30
    assert t["cache_read"] == 600
    assert t["cache_creation"] == 50
    assert abs(t["total_cost_usd"] - 0.07) < 1e-9
    # last_turn_usage reflects ONLY the most recent turn.
    assert t["last_turn_usage"]["input_tokens"] == 50
    assert t["last_turn_usage"]["cache_read_input_tokens"] == 400


def test_context_used_formula(tmp_consoles):
    # Per §5: context_used = input + cache_read + cache_creation.
    usage = {
        "input_tokens": 1000,
        "output_tokens": 500,        # NOT counted (it's output).
        "cache_read_input_tokens": 300_000,
        "cache_creation_input_tokens": 25_000,
    }
    assert console_store.context_used_from_usage(usage) == 326_000


# ---- Turns ---------------------------------------------------------------


def test_append_and_read_turns(tmp_consoles):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    console_store.append_turn(COMPANY, sid, {"id": "t1", "role": "user", "text": "hi"})
    console_store.append_turn(
        COMPANY, sid, {"id": "t1", "role": "assistant", "text": "hello", "subtype": "success"},
    )
    turns = console_store.read_turns(COMPANY, sid)
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[1]["subtype"] == "success"


# ---- Attachments --------------------------------------------------------


def test_save_png_attachment(tmp_consoles, png_bytes):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    record = console_store.save_attachment(
        company_id=COMPANY, session_id=sid,
        filename="chart.png", data=png_bytes,
    )
    assert record["mime"] == "image/png"
    assert record["size_bytes"] == len(png_bytes)
    assert record["id"].startswith(record["id"][:8])  # sha is hex

    # Mirrored into workdir/attachments for Claude.
    work = console_store.workdir_attachments(COMPANY, sid) / record["stored_name"]
    canonical = console_store.attachments_dir(COMPANY, sid) / record["stored_name"]
    assert canonical.is_file()
    assert work.is_file()


def test_save_attachment_too_large(tmp_consoles):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    huge = b"\x89PNG\r\n\x1a\n" + b"\x00" * (console_store.MAX_ATTACHMENT_BYTES + 1)
    with pytest.raises(console_store.AttachmentTooLarge):
        console_store.save_attachment(
            company_id=COMPANY, session_id=sid,
            filename="big.png", data=huge,
        )


def test_save_pdf_attachment(tmp_consoles, pdf_bytes):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    record = console_store.save_attachment(
        company_id=COMPANY, session_id=sid,
        filename="report.pdf", data=pdf_bytes,
    )
    assert record["mime"] == "application/pdf"
    assert record["stored_name"].endswith(".pdf")


def test_save_doc_attachment_requires_extension(tmp_consoles, doc_bytes):
    """OLE2 magic is shared with .xls/.ppt; we accept only .doc."""
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    record = console_store.save_attachment(
        company_id=COMPANY, session_id=sid,
        filename="notes.doc", data=doc_bytes,
    )
    assert record["mime"] == "application/msword"
    # Same magic with an .xls name is rejected (we don't accept Excel).
    with pytest.raises(console_store.AttachmentTypeNotAllowed):
        console_store.save_attachment(
            company_id=COMPANY, session_id=sid,
            filename="spreadsheet.xls", data=doc_bytes,
        )


def test_save_docx_attachment_requires_extension(
    tmp_consoles, docx_bytes, real_docx_bytes,
):
    """ZIP magic is shared with .xlsx/.pptx, so the extension names which
    one it is; a generic .zip stays out."""
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    record = console_store.save_attachment(
        company_id=COMPANY, session_id=sid,
        filename="memo.docx", data=real_docx_bytes,
    )
    assert record["mime"].endswith("wordprocessingml.document")
    with pytest.raises(console_store.AttachmentTypeNotAllowed):
        console_store.save_attachment(
            company_id=COMPANY, session_id=sid,
            filename="bundle.zip", data=docx_bytes,
        )


def test_a_word_file_is_staged_with_its_text_beside_it(
    tmp_consoles, real_docx_bytes,
):
    """The fix for "I wasn't able to open that .docx": Read sees a .docx
    as binary, so the text is pulled out once, here."""
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    record = console_store.save_attachment(
        company_id=COMPANY, session_id=sid,
        filename="term-sheet.docx", data=real_docx_bytes,
    )
    assert record["text_chars"] > 0
    workdir = console_store.workdir_attachments(COMPANY, sid)
    name, text = attachment_text.read_text(workdir, record["stored_name"])
    assert name == "term-sheet.docx"
    assert "Pre-money valuation of $42M." in text
    # Tables keep their rows, which is where a term sheet keeps numbers.
    assert "Liquidation pref | 1x non-participating" in text
    assert not attachment_text.needs_native_read(workdir, [record["stored_name"]])


@pytest.mark.parametrize(
    "filename,fixture,expected",
    [
        ("deck.pptx", "real_pptx_bytes", "ARR $4.2M"),
        ("cap-table.xlsx", "real_xlsx_bytes", "Ada Lovelace"),
        ("notes.md", None, "option pool"),
    ],
)
def test_the_other_document_types_land_as_text_too(
    tmp_consoles, request, filename, fixture, expected,
):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    data = (
        request.getfixturevalue(fixture) if fixture
        else b"# Notes\n\nThe option pool refreshes pre-close.\n"
    )
    record = console_store.save_attachment(
        company_id=COMPANY, session_id=sid, filename=filename, data=data,
    )
    _, text = attachment_text.read_text(
        console_store.workdir_attachments(COMPANY, sid), record["stored_name"]
    )
    assert expected in text


def test_a_document_with_no_readable_text_is_refused(
    tmp_consoles, empty_docx_bytes,
):
    """Refused at the composer, where the analyst can still do something
    about it, rather than two minutes into an answer."""
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    with pytest.raises(console_store.AttachmentUnreadable):
        console_store.save_attachment(
            company_id=COMPANY, session_id=meta["id"],
            filename="scan.docx", data=empty_docx_bytes,
        )


def test_an_image_needs_no_text_to_be_staged(tmp_consoles, png_bytes):
    """Images (and PDFs) are read by the model itself, so they are staged
    with no text beside them — and those asks have to go to Claude."""
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    record = console_store.save_attachment(
        company_id=COMPANY, session_id=sid,
        filename="chart.png", data=png_bytes,
    )
    assert record["text_chars"] == 0
    assert attachment_text.needs_native_read(
        console_store.workdir_attachments(COMPANY, sid), [record["stored_name"]]
    )


def test_save_attachment_wrong_type(tmp_consoles):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    # Plausible-looking bytes that aren't PNG/JPEG/WebP.
    with pytest.raises(console_store.AttachmentTypeNotAllowed):
        console_store.save_attachment(
            company_id=COMPANY, session_id=sid,
            filename="evil.png", data=b"MZ\x90\x00" + b"\x00" * 20,
        )


def test_detect_attachment_type_sniffing(
    png_bytes, jpeg_bytes, webp_bytes, pdf_bytes, doc_bytes, docx_bytes,
):
    detect = console_store.detect_attachment_type
    assert detect(png_bytes) == "image/png"
    assert detect(jpeg_bytes) == "image/jpeg"
    assert detect(webp_bytes) == "image/webp"
    assert detect(pdf_bytes) == "application/pdf"
    assert detect(doc_bytes, "x.doc") == "application/msword"
    assert detect(docx_bytes, "x.docx").endswith("wordprocessingml.document")
    # The ZIP magic is shared, so the extension picks the Office format.
    assert detect(docx_bytes, "x.xlsx").endswith("spreadsheetml.sheet")
    assert detect(docx_bytes, "x.pptx").endswith("presentationml.presentation")
    # Ambiguous magics without a known extension fall back to None.
    assert detect(doc_bytes, "x.xls") is None
    assert detect(docx_bytes, "x.zip") is None
    assert detect(b"\x00\x00\x00\x00") is None
    # Text formats have no magic: the extension names them and the bytes
    # have to look like text.
    assert detect(b"name,shares\nAda,100\n", "cap.csv") == "text/csv"
    assert detect(b"# Notes", "notes.md") == "text/markdown"
    assert detect(b"<p>hi</p>", "page.html") == "text/html"
    assert detect(b"\x00\x01\x02binary", "fake.txt") is None


# ---- Workdir staging ----------------------------------------------------


def test_stage_docs_hardlink(tmp_consoles, tmp_path):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4 hello")
    staged = console_store.stage_docs(
        company_id=COMPANY, session_id=sid, source_paths=[src],
    )
    assert len(staged) == 1
    # Hardlink: same inode as source.
    assert staged[0].stat().st_ino == src.stat().st_ino


def test_stage_docs_copy_fallback(tmp_consoles, tmp_path, monkeypatch):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4 copy-fallback")

    import errno
    def boom(*args, **kwargs):
        raise OSError(errno.EXDEV, "Cross-device link")
    monkeypatch.setattr(os, "link", boom)

    staged = console_store.stage_docs(
        company_id=COMPANY, session_id=sid, source_paths=[src],
    )
    assert staged[0].read_bytes() == src.read_bytes()
    # Independent copy: different inode.
    assert staged[0].stat().st_ino != src.stat().st_ino


# ---- Path safety --------------------------------------------------------


def test_rejects_path_traversal_in_session_id(tmp_consoles):
    with pytest.raises(ValueError):
        console_store.session_dir(COMPANY, "../../../etc")
    with pytest.raises(ValueError):
        console_store.meta_path(COMPANY, "/etc/passwd")


def test_rejects_bad_attachment_id(tmp_consoles):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    with pytest.raises(ValueError):
        console_store.get_attachment_path(COMPANY, sid, "../evil")


# ---- Hard delete --------------------------------------------------------


def test_hard_delete_removes_directory(tmp_consoles):
    meta = console_store.create_session(
        company_id=COMPANY, include_background_docs=False,
        include_library_docs=False, included_files=[],
    )
    sid = meta["id"]
    assert console_store.session_exists(COMPANY, sid)
    assert console_store.hard_delete_session(COMPANY, sid) is True
    assert not console_store.session_exists(COMPANY, sid)
    assert console_store.hard_delete_session(COMPANY, sid) is False
