"""The evidence matrix returns its rows under ``claims``; the signal score and the numbers lint read them from there."""
from __future__ import annotations

from server import evidence_matrix, numbers_lint, research_store, signal_score, storage


def _seed_company() -> None:
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [{"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private"}],
    )


def _evidence(components: list[dict]) -> dict:
    return next(c for c in components if c["name"] == "Evidence")


def test_supported_claims_score_evidence_and_feed_the_numbers_corpus():
    _seed_company()
    assert _evidence(signal_score.compute("acme-ai")["components"])["available"] is False

    record = research_store.upload_file(
        "acme-ai", filename="deck.pdf", content_type="application/pdf", data=b"%PDF-1.4 deck"
    )
    research_store.update_record(
        "acme-ai",
        record["id"],
        quick_summary={
            "source_traces": [
                {"claim": "ARR reached $4.2M in Q2 2026", "excerpt": "ARR reached $4.2M in Q2 2026", "confidence": "high"}
            ]
        },
    )

    claims = evidence_matrix.build_company_evidence_matrix("acme-ai")["claims"]
    assert [c["status"] for c in claims] == ["supported"]

    evidence = _evidence(signal_score.compute("acme-ai")["components"])
    assert evidence["available"] is True
    assert evidence["points"] == 20.0
    assert "1 supported, 0 partial, 0 contradicted of 1 claims" in evidence["basis"]

    texts, _sources = numbers_lint._corpus("acme-ai")
    result = numbers_lint.lint_blocks([("Traction", "ARR is $4.2M")], texts)
    assert result["unsupported"] == 0
    assert result["supported"] >= 1
