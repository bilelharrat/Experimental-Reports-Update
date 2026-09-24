"""The right template first (R29 A(a)(b)): listed companies are recognised
from the registry's own rule (status, else a ticker — the exchange is blank
on most listed records), a subsidiary is named as one with the security
that would own it, and every run records what an outside investor could
actually buy (``actionability``) next to its scope check."""
from __future__ import annotations

import pytest

from server import memo_prep


@pytest.mark.parametrize(
    "company, classification, signal",
    [
        ({"id": "amd", "name": "AMD", "ticker": "AMD"}, "public", "public (ticker AMD)"),
        ({"id": "ko", "name": "Coca-Cola", "status": "public"}, "public", "public (registry status)"),
        ({"id": "tsm", "name": "TSMC", "ticker": "TSM", "exchange": "NYSE"}, "public", "public on NYSE"),
        # The registry's status wins over a stray ticker.
        ({"id": "x", "name": "X", "status": "private", "ticker": "XX"}, "indeterminate", None),
    ],
)
def test_listed_companies_are_recognised_without_an_exchange(company, classification, signal):
    assessment = memo_prep._classify_stage(company)
    assert assessment["classification"] == classification
    if signal:
        assert assessment["signals"] == [signal]
        assert memo_prep.classify_structure_stage(company) == {
            "stage": "late",
            "source": "public listing",
            "signals": [signal],
        }


def test_a_subsidiary_names_the_security_that_would_own_it():
    cienet = {"id": "cienet", "name": "CIeNET", "status": "subsidiary", "parent_company": "ALTEN"}
    assessment = memo_prep._classify_stage(cienet)
    assert assessment["outcome"] == "warn"  # proceeds; never a new hard gate
    assert assessment["classification"] == "subsidiary"
    assert assessment["investable_security"] == "parent (ALTEN)"
    assert "subsidiary of ALTEN" in assessment["reason"]
    # The Auto type keeps the subsidiary reason instead of the generic
    # stage-calibration text.
    auto = memo_prep._assess_stage(cienet, calibrate_only=True)
    assert "parent (ALTEN)" in auto["reason"] and auto["calibrate_only"] is True
    unknown = memo_prep._classify_stage({"id": "s", "name": "S", "status": "subsidiary"})
    assert unknown["investable_security"] == "parent (unknown until researched)"
    # A subsidiary with its own listing is listed.
    listed = {"id": "l", "name": "L", "status": "subsidiary", "exchange": "HKEX", "ticker": "0001"}
    assert memo_prep._classify_stage(listed)["classification"] == "public"


def test_actionability_says_what_an_outside_investor_could_buy():
    assert memo_prep.classify_actionability({"status": "subsidiary", "parent_company": "ALTEN"}) == {
        "source": "registry",
        "kind": "subsidiary",
        "investable_security": "parent (ALTEN)",
        "parent": "ALTEN",
    }
    assert memo_prep.classify_actionability({"ticker": "AMD", "exchange": "NASDAQ"}) == {
        "source": "registry",
        "kind": "listed",
        "investable_security": "listed equity (AMD on NASDAQ)",
        "ticker": "AMD",
    }
    assert memo_prep.classify_actionability({"status": "private"})["kind"] == "private_round"
    assert memo_prep.classify_actionability({"status": "nonprofit"})["kind"] == "nonprofit"
