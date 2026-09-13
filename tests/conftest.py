"""Shared fixtures for the Console test suite."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch, tmp_path):
    """Redirect every module-level data path to a per-test tmp dir.

    The live ``data/`` directory used to be the default for any test that
    forgot to monkeypatch a root — ``data/companies.yaml.broken_by_tests``
    was the scar. Modules freeze path constants at import time, so each one
    must be re-pointed individually; keep this list in sync when adding a
    store with its own module-level path constant. Tests that need their
    own layout simply monkeypatch over these (their patch runs later).
    """
    from server import (
        annotation_store,
        auth_store,
        cache,
        console_store,
        desk_store,
        external_store,
        files_store,
        hormuz_store,
        market_brief,
        memo_editor_store,
        memo_prep,
        news_brief,
        product_store,
        research_store,
        serena_analysis,
        stock_research,
        storage,
        weekly_stocks,
    )

    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", data_root / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", data_root / "threads")
    monkeypatch.setattr(cache, "CACHE_ROOT", data_root / "cache")
    monkeypatch.setattr(auth_store, "USERS_FILE", data_root / "users.json")
    monkeypatch.setattr(auth_store, "SESSIONS_FILE", data_root / "sessions.json")
    monkeypatch.setattr(external_store, "EXTERNAL_ROOT", data_root / "external")
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", data_root / "uploads")
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", data_root / "research")
    monkeypatch.setattr(console_store, "CONSOLES_ROOT", data_root / "consoles")
    monkeypatch.setattr(memo_editor_store, "EDITOR_ROOT", data_root / "memo_editor")
    monkeypatch.setattr(product_store, "SETTINGS_ROOT", data_root / "settings")
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", data_root / "memos")
    monkeypatch.setattr(
        memo_prep, "SETTINGS_FILE", data_root / "settings" / "serena_background.md"
    )
    monkeypatch.setattr(memo_prep, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(hormuz_store, "DATA_DIR", data_root)
    monkeypatch.setattr(
        hormuz_store,
        "SOURCES_ROOT",
        data_root / "external" / "hormuz_research" / "sources",
    )
    monkeypatch.setattr(hormuz_store, "APPENDIX_ROOT", data_root / "hormuz_appendix")
    monkeypatch.setattr(weekly_stocks, "WEEKLY_DIR", data_root / "_weekly_stocks")
    monkeypatch.setattr(
        stock_research, "STOCK_RESEARCH_ROOT", data_root / "stock_research"
    )
    monkeypatch.setattr(
        serena_analysis, "ANALYSIS_ROOT", data_root / "serena_analysis"
    )
    monkeypatch.setattr(
        serena_analysis, "TRAINING_ROOT", data_root / "serena_training"
    )
    monkeypatch.setattr(desk_store, "DESK_ROOT", data_root / "market_desk")
    monkeypatch.setattr(
        annotation_store, "ANNOTATIONS_ROOT", data_root / "report_annotations"
    )
    monkeypatch.setattr(market_brief, "BRIEFS_ROOT", data_root / "market_briefs")
    monkeypatch.setattr(news_brief, "BRIEFS_ROOT", data_root / "news_briefs")


@pytest.fixture(autouse=True)
def _no_real_claude_cli(request, monkeypatch):
    """Fail closed on real Claude CLI spawns in unit tests.

    Every spawn path checks ``claude_runner.is_available()`` first, so forcing
    it False makes an unmocked path return its "claude not on PATH" error
    instead of silently launching a real (paid, minutes-long) subprocess.
    This actually happened: on machines with ``claude`` installed, the fast
    memo pipeline tests reached the real bilingual parallel wrapper, spawned
    per-section Claude processes, and only then fell back to the patched
    monolithic fake — one such test took 58s with claude on PATH vs 0.9s
    without. CI has no claude binary, so this also makes local runs match CI.
    Tests that need availability monkeypatch ``is_available`` themselves
    (their patch runs after this one and wins); e2e tests keep the real
    check.
    """
    if request.node.get_closest_marker("e2e"):
        return
    from server import claude_runner

    monkeypatch.setattr(claude_runner, "is_available", lambda: False)


@pytest.fixture(autouse=True)
def _neutral_structure_flag(monkeypatch):
    """Tests must not inherit the developer's .env: importing server.main
    anywhere in the session load_dotenv()s the project .env into
    os.environ, and a BSH_MEMO_STRUCTURE_V2=1 there flips every
    pipeline test to the v2 structure mid-session (observed 2026-09-11
    as order-dependent failures). Default the flag off; tests that
    exercise v2 set it themselves.
    """
    monkeypatch.delenv("BSH_MEMO_STRUCTURE_V2", raising=False)


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """Let API tests through without credentials. ``require_api_token`` now
    fails closed, so we clear any shared token AND opt into anonymous dev
    access explicitly. Tests that exercise auth itself override these with
    their own ``monkeypatch`` in the test body. Env is restored on exit.
    """
    monkeypatch.delenv("BSH_RESEARCH_API_TOKEN", raising=False)
    monkeypatch.setenv("BSH_ALLOW_ANON_DEV", "1")
    # The /api/jobs/active TTL cache is keyed on time only; tests monkeypatch
    # data roots, so a cache entry from one test would otherwise leak into the
    # next. Clear it before each test.
    try:
        from server import api as _api

        _api._active_jobs_cache = None
    except Exception:
        pass


@pytest.fixture
def tmp_consoles(monkeypatch, tmp_path):
    """Redirect ``console_store.CONSOLES_ROOT`` to a tmp dir for a single
    test, plus the two source-file stores it can pull from."""
    from server import console_store, files_store, research_store

    consoles_root = tmp_path / "consoles"
    uploads_root = tmp_path / "uploads"
    research_root = tmp_path / "research"

    monkeypatch.setattr(console_store, "CONSOLES_ROOT", consoles_root)
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", uploads_root)
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", research_root)

    return {
        "consoles": consoles_root,
        "uploads": uploads_root,
        "research": research_root,
        "root": tmp_path,
    }


@pytest.fixture
def png_bytes() -> bytes:
    """Minimal valid 1x1 PNG."""
    # 8-byte signature + IHDR + IDAT + IEND. Hand-crafted minimal PNG.
    return bytes.fromhex(
        "89504e470d0a1a0a"            # signature
        "0000000d49484452"            # IHDR length(13) + tag
        "00000001000000010806000000"  # 1x1 RGBA, bit depth 8
        "1f15c4890000000a4944415478"  # CRC + IDAT length + tag + start
        "9c6300010000000500010d0a2db4"
        "0000000049454e44ae426082"    # IEND
    )


@pytest.fixture
def jpeg_bytes() -> bytes:
    """Tiny JPEG header (enough to pass our magic-byte sniff)."""
    # FF D8 FF E0 ... full minimal JPEG isn't needed — sniffer only reads
    # the first 3 bytes for JPEG.
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" \
           + b"\xff\xd9"


@pytest.fixture
def webp_bytes() -> bytes:
    """RIFF/WEBP container header — magic-byte check needs bytes 0-3 == RIFF
    and 8-11 == WEBP."""
    return b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 16


@pytest.fixture
def pdf_bytes() -> bytes:
    """Tiny PDF — just the magic header is enough for our sniffer."""
    return b"%PDF-1.4\n%mock\n1 0 obj <<>> endobj\n%%EOF\n"


@pytest.fixture
def doc_bytes() -> bytes:
    """OLE2 compound-binary header — same magic shared with .xls/.ppt; the
    sniffer relies on the .doc extension to disambiguate."""
    return b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" + b"\x00" * 32


@pytest.fixture
def docx_bytes() -> bytes:
    """ZIP local-file header — same magic shared with .xlsx/.pptx; the
    sniffer relies on the .docx extension to disambiguate."""
    return b"PK\x03\x04" + b"\x00" * 32
