"""The annotated research-folder listing memo prompts read.

Pins the enriched format: upload dates + labels + folder grouping from
the store index, analysis files flagged as the preferred distilled read,
machine-written digests bare, progress sidecars excluded, and the
time-decay guidance line (old files are trajectory context, not noise).
"""
from __future__ import annotations

from server import claude_runner, research_store, storage


def _seed(tmp_path, monkeypatch, company_id="generalist"):
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [{"id": company_id, "name": "Generalist", "status": "private"}],
    )
    return company_id


def test_missing_and_empty_dirs(tmp_path):
    assert "No research directory" in claude_runner._research_file_listing(None)
    empty = tmp_path / "research" / "generalist"
    empty.mkdir(parents=True)
    assert (
        claude_runner._research_file_listing(empty) == "- No research files found."
    )


def test_indexed_files_carry_dates_labels_and_folders(tmp_path, monkeypatch):
    cid = _seed(tmp_path, monkeypatch)
    plain = research_store.upload_file(
        cid,
        filename="deck.md",
        content_type="text/markdown",
        data=b"# deck",
        label="Board deck",
    )
    folder_id = research_store.mint_folder_id()
    research_store.upload_file(
        cid,
        filename="note.md",
        content_type="text/markdown",
        data=b"# note",
        folder_id=folder_id,
        folder_name="meeting notes",
    )
    research_dir = research_store.RESEARCH_ROOT / cid
    # Machine-written digest (un-indexed) + a progress sidecar.
    (research_dir / "recent_news.md").write_text("# news", encoding="utf-8")
    research_store.analysis_progress_path(cid, plain["id"]).write_text(
        "{}\n", encoding="utf-8"
    )

    listing = claude_runner._research_file_listing(research_dir)
    uploaded = plain["uploaded_at"][:10]
    assert f'- {plain["stored_name"]} — uploaded {uploaded}, label "Board deck"' in listing
    assert 'part of folder "meeting notes"' in listing
    assert "- recent_news.md\n" in listing + "\n"  # bare digest line
    assert ".progress.jsonl" not in listing
    assert "trajectory context" in listing
    assert "read them, don't" in listing


def test_analysis_files_are_flagged_as_preferred(tmp_path, monkeypatch):
    cid = _seed(tmp_path, monkeypatch)
    source = research_store.upload_file(
        cid, filename="report.md", content_type="text/markdown", data=b"# r"
    )
    analysis = research_store.upload_file(
        cid,
        filename="report_analysis.md",
        content_type="text/markdown",
        data=b"# a",
    )
    research_store.update_record(cid, analysis["id"], analysis_of=source["id"])

    folder_id = research_store.mint_folder_id()
    research_store.upload_file(
        cid,
        filename="n1.md",
        content_type="text/markdown",
        data=b"# n",
        folder_id=folder_id,
        folder_name="notes",
    )
    folder_analysis = research_store.upload_file(
        cid,
        filename="notes_analysis.md",
        content_type="text/markdown",
        data=b"# fa",
    )
    research_store.update_record(
        cid, folder_analysis["id"], analysis_of=folder_id
    )

    listing = claude_runner._research_file_listing(
        research_store.RESEARCH_ROOT / cid
    )
    assert "distilled analysis of report.md" in listing
    assert 'distilled analysis of folder "notes"' in listing
    assert listing.count("prefer this over reprocessing the raw file") == 2


def test_index_failure_falls_back_to_bare_names(tmp_path, monkeypatch):
    cid = _seed(tmp_path, monkeypatch)
    research_store.upload_file(
        cid, filename="doc.md", content_type="text/markdown", data=b"# d"
    )
    research_dir = research_store.RESEARCH_ROOT / cid

    def _boom(*_a, **_kw):
        raise RuntimeError("index unreadable")

    monkeypatch.setattr(research_store, "list_files", _boom)
    listing = claude_runner._research_file_listing(research_dir)
    assert "__doc.md" in listing  # bare stored name still listed
    assert "uploaded" not in listing
