"""The research desk's numbers card handles a Buffett-method memo.

``memo_fact_check.check_company`` used to walk every package as the
late-stage section/block schema, so a company whose latest memo was a
Buffett-method memo showed an empty card. It now routes those packages to
``buffett_checks.fact_check`` (report only, writes nothing).
"""
import json

import pytest

from server import comps, memo_fact_check as fc, research_store
from tests.test_buffett_memo import _package as _buffett_package

COMPANY = "demo-listed-co"


@pytest.fixture(autouse=True)
def _roots(tmp_path, monkeypatch):
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", tmp_path / "research")
    monkeypatch.setattr(fc.numbers_lint, "_corpus", lambda cid: ([], []))


def _latest(monkeypatch, tmp_path, package: dict):
    path = tmp_path / "memos" / COMPANY / "run" / "logs" / "memo_package.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(package), encoding="utf-8")
    monkeypatch.setattr(comps, "_latest_memo_package", lambda cid, reports=None: (path, package))
    return path


def test_buffett_package_is_detected():
    assert fc._is_buffett_package(_buffett_package())
    assert fc._is_buffett_package({"markdown_en": "text"})
    assert not fc._is_buffett_package({"sections": [{"id": "exec"}], "markdown_en": "text"})


def test_check_company_traces_a_buffett_memo(tmp_path, monkeypatch):
    path = _latest(monkeypatch, tmp_path, _buffett_package())
    before = sorted(p.name for p in tmp_path.rglob("*"))
    payload = fc.check_company(COMPANY)
    assert payload["memo_package"] == str(path)
    assert payload["memo_kind"] == "buffett_investment_memo"
    # Nothing on file to check against: the card says so instead of
    # showing a misleading percentage.
    assert payload["thin_corpus"] is True
    assert payload["supported"] == payload["checked"] - payload["unsupported"]
    assert payload["summary"]["coverage_pct"] is None
    assert "thin" in payload["note"]
    # Report only: checking the card writes nothing.
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


def test_unreadable_buffett_package_says_so(tmp_path, monkeypatch):
    broken = {"kind": "buffett_investment_memo", "markdown_en": "too short"}
    _latest(monkeypatch, tmp_path, broken)
    payload = fc.check_company(COMPANY)
    assert payload["checked"] == 0
    assert "could not be read" in payload["note"]


def test_nt_dollar_amounts_are_figures():
    figures = fc.extract_figures("TSMC's quarterly revenue was NT$839.25 billion, up 39%.")
    raws = [f.raw for f in figures]
    assert any(raw.startswith("NT$") for raw in raws), raws
