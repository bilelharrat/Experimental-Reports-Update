"""Choosing which analysed documents a run may read.

The customizer lists the `<name>_analysis.md` files in the company's
research folder and lets the analyst drop some before launching. The
choice is pinned into the run folder at bootstrap so every phase — and a
resume — reads the same set.
"""
from __future__ import annotations

import json
from pathlib import Path

from server import claude_runner, research_store


def _listed(listing: str) -> set[str]:
    """The files the listing actually offers, by name.

    A raw source's name also appears inside its analysis line ("distilled
    analysis of deck.pdf"), so only the bullet's own filename counts."""
    names = set()
    for line in listing.splitlines():
        if line.startswith("- "):
            names.add(line[2:].split(" — ")[0].strip())
    return names


def _company(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", tmp_path / "research")
    monkeypatch.setattr(research_store, "DATA_DIR", tmp_path)
    return "generalist-inc"


def _seed(company: str) -> tuple[dict, dict, dict, dict]:
    deck = research_store.upload_file(
        company, filename="deck.pdf", content_type="application/pdf", data=b"%PDF-1.4 x"
    )
    memo = research_store.upload_file(
        company, filename="memo.pdf", content_type="application/pdf", data=b"%PDF-1.4 y"
    )
    deck_analysis = research_store.upload_file(
        company,
        filename="deck_analysis.md",
        content_type="text/markdown",
        data=b"# deck analysis",
    )
    memo_analysis = research_store.upload_file(
        company,
        filename="memo_analysis.md",
        content_type="text/markdown",
        data=b"# memo analysis",
    )
    research_store.update_record(
        company, deck_analysis["id"], analysis_of=deck["id"]
    )
    research_store.update_record(
        company, memo_analysis["id"], analysis_of=memo["id"]
    )
    return deck, memo, deck_analysis, memo_analysis


def test_no_selection_means_every_document(tmp_path, monkeypatch):
    company = _company(tmp_path, monkeypatch)
    _seed(company)
    listed = _listed(
        claude_runner._research_file_listing(
            research_store.RESEARCH_ROOT / company, None
        )
    )
    assert any(n.endswith("deck_analysis.md") for n in listed)
    assert any(n.endswith("memo_analysis.md") for n in listed)
    # Raw sources stay hidden behind their analyses, as before.
    assert not any(n.endswith("deck.pdf") for n in listed)
    assert not any(n.endswith("memo.pdf") for n in listed)


def test_a_dropped_document_takes_its_raw_source_with_it(tmp_path, monkeypatch):
    """Leaving the analysis out but listing the PDF would defeat the choice."""
    company = _company(tmp_path, monkeypatch)
    _deck, _memo, deck_analysis, _memo_analysis = _seed(company)
    listed = _listed(
        claude_runner._research_file_listing(
            research_store.RESEARCH_ROOT / company, {deck_analysis["id"]}
        )
    )
    assert any(n.endswith("deck_analysis.md") for n in listed)
    assert not any(n.endswith("memo_analysis.md") for n in listed)
    assert not any(n.endswith("memo.pdf") for n in listed)
    assert not any(n.endswith("deck.pdf") for n in listed)


def test_an_empty_selection_drops_every_analysed_document(tmp_path, monkeypatch):
    company = _company(tmp_path, monkeypatch)
    _seed(company)
    listed = _listed(
        claude_runner._research_file_listing(
            research_store.RESEARCH_ROOT / company, set()
        )
    )
    assert not any(n.endswith("_analysis.md") for n in listed)
    assert not any(n.endswith(".pdf") for n in listed)


def test_the_choice_is_pinned_into_the_run_folder(tmp_path):
    run_dir = tmp_path / "run"
    assert claude_runner.memo_evidence_selection(run_dir) is None

    claude_runner.write_memo_evidence_selection(run_dir, ["b", "a", "a"])
    path = claude_runner.memo_evidence_selection_path(run_dir)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "analysis_ids": ["a", "b"]
    }
    assert claude_runner.memo_evidence_selection(run_dir) == {"a", "b"}


def test_writing_none_pins_nothing(tmp_path):
    """A caller that never asked keeps the old whole-folder behaviour."""
    run_dir = tmp_path / "run"
    claude_runner.write_memo_evidence_selection(run_dir, None)
    assert not claude_runner.memo_evidence_selection_path(run_dir).exists()
    assert claude_runner.memo_evidence_selection(run_dir) is None


def test_an_unreadable_selection_never_fails_a_run(tmp_path):
    run_dir = tmp_path / "run"
    path = claude_runner.memo_evidence_selection_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert claude_runner.memo_evidence_selection(run_dir) is None


def test_an_empty_pin_survives_the_round_trip(tmp_path):
    """Empty is a real answer — "read none of my documents" — and must not
    read back as "read everything"."""
    run_dir = tmp_path / "run"
    claude_runner.write_memo_evidence_selection(run_dir, [])
    assert claude_runner.memo_evidence_selection(run_dir) == set()
