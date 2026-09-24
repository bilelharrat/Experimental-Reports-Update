"""Demo and registry figures must never be labelled as BSH diligence.

The ZaiNar record carries values from the v2 design mock. The seed now
labels them "demo placeholder (v2 design mock)"; these tests keep the two
readers that re-label source classes from turning that back into
"BSH primary diligence" or "third-party market data".
"""
from server import context_store, memo_editor_store


def test_context_store_keeps_a_demo_label_as_written():
    label = "demo placeholder (v2 design mock)"
    assert context_store._source_class(label) == label
    assert context_store._source_class("Demo record (v2 design mock)") == "Demo record (v2 design mock)"
    # Known classes still map as before.
    assert context_store._source_class("bsh diligence") == "BSH primary diligence"
    assert context_store._source_class("") == "third-party market data"


def _company(metric_class: str) -> dict:
    return {
        "id": "demo-co",
        "name": "Demo Co",
        "metrics": [
            {"label": "ARR", "value": "~$24M", "source_class": metric_class},
            {"label": "Growth", "value": "+180%", "source_class": metric_class},
        ],
    }


def test_metrics_card_takes_its_class_from_the_metrics():
    cards = memo_editor_store._fallback_thesis_cards(_company("demo placeholder (v2 design mock)"))
    metrics_card = next(c for c in cards if c["title"].startswith("Disclosed metrics"))
    assert metrics_card["source_class"] == "unknown/pending"

    cards = memo_editor_store._fallback_thesis_cards(_company("public filing"))
    metrics_card = next(c for c in cards if c["title"].startswith("Disclosed metrics"))
    assert metrics_card["source_class"] == "public filing"


def test_fallback_cards_never_claim_bsh_diligence():
    company = _company("demo placeholder (v2 design mock)")
    cards = memo_editor_store._fallback_thesis_cards(company) + memo_editor_store._fallback_risk_cards(company)
    for card in cards:
        assert card["source_class"] != "BSH primary diligence", card["title"]
        for bullet in card.get("bullets") or []:
            assert bullet.get("source_class") != "BSH primary diligence", card["title"]
        for ref in card.get("source_refs") or []:
            assert "PRD reference package" not in str(ref.get("title") or "")
