"""Corrupt store files must be quarantined, not silently replaced.

July 2026 review finding: an unparseable index.yaml was read as [] and the
next write rebuilt it with only the new entry, orphaning every previously
uploaded file's record (files_store, research_store), wiping the intake
queue (evidence_store), and resetting preferences (product_store).
"""
from __future__ import annotations

import pytest

from server import evidence_store, files_store, product_store, research_store, storage


def test_files_store_quarantines_corrupt_index(monkeypatch, tmp_path):
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", tmp_path / "uploads")
    company_dir = tmp_path / "uploads" / "acme"
    company_dir.mkdir(parents=True)
    (company_dir / "index.yaml").write_text("{unclosed: [", encoding="utf-8")

    with pytest.raises(RuntimeError, match="quarantined"):
        files_store.list_files("acme")

    assert not (company_dir / "index.yaml").exists()
    quarantined = list(company_dir.glob("index.yaml.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "{unclosed: ["
    # After quarantine the store treats the index as missing (fresh start),
    # with the old bytes preserved on disk for recovery.
    assert files_store.list_files("acme") == []


def test_research_store_quarantines_corrupt_index(monkeypatch, tmp_path):
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", tmp_path / "research")
    company_dir = tmp_path / "research" / "acme"
    company_dir.mkdir(parents=True)
    (company_dir / "index.yaml").write_text(":\n  - not yaml: [", encoding="utf-8")

    with pytest.raises(RuntimeError, match="quarantined"):
        research_store.list_files("acme")
    assert list(company_dir.glob("index.yaml.corrupt-*"))


def test_evidence_store_quarantines_corrupt_queue(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    intake_dir = tmp_path / "data" / "intake"
    intake_dir.mkdir(parents=True)
    (intake_dir / "unresolved.yaml").write_text("[broken", encoding="utf-8")

    with pytest.raises(RuntimeError, match="quarantined"):
        evidence_store.list_unresolved_intake()
    assert list(intake_dir.glob("unresolved.yaml.corrupt-*"))


def test_product_store_quarantines_corrupt_preferences(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    settings_dir = tmp_path / "data" / "settings"
    settings_dir.mkdir(parents=True)
    (settings_dir / "preferences.yaml").write_text("{bad: [", encoding="utf-8")

    with pytest.raises(RuntimeError, match="quarantined"):
        product_store._read_yaml({})
    assert list(settings_dir.glob("preferences.yaml.corrupt-*"))
