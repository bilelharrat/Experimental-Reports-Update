"""Shared fixtures for the Console test suite."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """Force ``require_api_token`` into dev-mode (no token configured →
    dependency is a no-op) for every test in this suite. We restore the
    user's original env automatically when the test exits.
    """
    monkeypatch.delenv("BSH_RESEARCH_API_TOKEN", raising=False)


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
