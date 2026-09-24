"""The Chinese parity gate's report-only content checks (R33 FIX 1, R22
FIX 4, R12 glossary): untranslated cover fields, Chinese text identical to
the English, English figures the Chinese lost, glossary drift. All P1/P2 —
none of them may ever block a run — and all quiet on a clean pair."""
from __future__ import annotations

import copy

import pytest

import test_memo_docx_renderer as base
from server import memo_chinese_parity as parity
from server import memo_docx_renderer


def _render(tmp_path, package):
    out_en = tmp_path / "memo" / "en.docx"
    out_zh = tmp_path / "memo" / "zh.docx"
    memo_docx_renderer.render_memos(package, out_en=out_en, out_zh=out_zh)
    return out_en, out_zh


def _codes(result, code):
    return [f for f in result.findings if f.code == code]


def _clean_package():
    package = base._package()
    company = package["company"]
    company["stage"] = {"en": "Late-stage / pre-IPO", "zh": "后期 / IPO 前"}
    company["round"] = {"en": "Series D context", "zh": "D 轮背景"}
    return package


@pytest.fixture(autouse=True)
def no_glossary(monkeypatch, tmp_path):
    # Each test opts into a glossary explicitly.
    monkeypatch.setattr(parity, "ZH_STYLE_PATH", tmp_path / "absent_zh_style.md")


def test_a_clean_pair_has_no_content_findings(tmp_path):
    package = _clean_package()
    en, zh = _render(tmp_path, package)
    for kwargs in ({}, {"package": package}):
        result = parity.lint_chinese_memo_pair(en, zh, **kwargs)
        assert result.findings == [], [f.to_dict() for f in result.findings]


def test_english_cover_fields_in_the_chinese_memo_are_p1_whatever_their_length(tmp_path):
    package = base._package()  # stage and round are plain English strings
    en, zh = _render(tmp_path, package)
    result = parity.lint_chinese_memo_pair(en, zh)
    cover = _codes(result, "cover_field_untranslated")
    assert [f.snippet for f in cover] == ["阶段: Late-stage / pre-IPO", "轮次: Series D context"]
    assert {f.severity for f in cover} == {"P1"}
    assert not result.has_blocking_findings
    # names, tickers and figures may stay as written: sector "AI Robotics"
    # and location "San Francisco, CA" are not findings
    assert not any("AI Robotics" in f.snippet or "San Francisco" in f.snippet for f in cover)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Late-stage / pre-IPO", True),
        ("Energy software", True),
        ("x capital", True),
        ("San Francisco, CA", False),
        ("Bank of America", False),
        ("iPhone 17", False),
        ("2026-06", False),
        ("$24M [S3]", False),
        ("https://www.reuters.com/business/x", False),
        ("后期 / IPO 前", False),
        ("NVDA", False),
    ],
)
def test_needs_translation(text, expected):
    assert parity.needs_translation(text) is expected


def test_a_short_chinese_block_identical_to_the_english_is_p1(tmp_path):
    package = _clean_package()
    snapshot = package["sections"][0]["blocks"][2]
    snapshot["rows"][0][1] = {"en": "Company figure, unaudited", "zh": "Company figure, unaudited"}
    en, zh = _render(tmp_path, package)
    docx_mode = parity.lint_chinese_memo_pair(en, zh)
    found = _codes(docx_mode, "zh_identical_to_en")
    assert len(found) == 1 and found[0].severity == "P1"
    assert found[0].snippet == "Company figure, unaudited"
    package_mode = parity.lint_chinese_memo_pair(en, zh, package=package)
    found = _codes(package_mode, "zh_identical_to_en")
    assert [f.location for f in found] == ["executive_summary blocks[2].rows[0][1]"]
    # a language-neutral value repeated in both is not a finding
    snapshot["rows"][0][1] = {"en": "$24M (2025)", "zh": "$24M (2025)"}
    en, zh = _render(tmp_path / "b", package)
    assert not _codes(parity.lint_chinese_memo_pair(en, zh), "zh_identical_to_en")


@pytest.mark.parametrize(
    "english, chinese, mismatch",
    [
        ("Revenue reached $2.4B in 2025.", "2025 年收入达到 $2.4B。", False),
        ("Revenue reached $2.4B in 2025.", "2025 年收入达到 24 亿美元。", False),
        ("Revenue reached $2.4B in 2025.", "2025 年收入达到 $2.6B。", True),
        ("Revenue grew 72% to $86M.", "收入增长 71% 至 $86M。", True),
        ("The entry is 27.9x revenue.", "入场价为收入的 28 倍。", False),  # one rounding step
        ("The entry is 27.9x revenue.", "入场价为收入的 21 倍。", True),
        ("Fair value is $1.4B–$1.8B.", "公允价值为 14 亿至 18 亿美元。", False),
        ("Anchors imply $34 billion, $56 billion and $110 billion.", "分别隐含 340 亿、560 亿与 1100 亿美元收入。", False),
        ("Group revenue EUR 4.14 billion.", "集团收入 EUR 41.4 亿。", False),
        ("Revenue fell 4.5% organically.", "有机增长 -4.5%。", False),  # sign wording differs
        ("It is about 24 times sales.", "约为 24 倍市销率。", False),
        ("Storage grows sixfold by 2030.", "储能到 2030 年增长六倍。", False),
        ("Selected 17 to 18 times.", "入选 17 至 18 次。", False),  # a count, not a multiple
        ("Margins reach the high 50s.", "毛利率升至 50% 后段。", False),  # Chinese extras never report
    ],
)
def test_english_figures_must_survive_the_translation(tmp_path, english, chinese, mismatch):
    package = _clean_package()
    package["sections"][1]["blocks"][0]["text"] = {"en": english, "zh": chinese}
    en, zh = _render(tmp_path, package)
    for kwargs in ({}, {"package": package}):
        found = _codes(parity.lint_chinese_memo_pair(en, zh, **kwargs), "number_mismatch")
        assert bool(found) is mismatch, (kwargs.keys(), [f.snippet for f in found])
        assert all(f.severity == "P1" for f in found)
    if mismatch:
        found = _codes(parity.lint_chinese_memo_pair(en, zh, package=package), "number_mismatch")
        assert found[0].location == "company_overview blocks[0].text"


def test_figure_findings_are_capped(tmp_path):
    package = _clean_package()
    package["sections"][1]["blocks"][0]["text"] = {
        "en": "Figures: $1.1B, $2.2B, $3.3B, $4.4B and $5.5B.",
        "zh": "数字：$9.1B、$9.2B、$9.3B、$9.4B 与 $9.5B。",
    }
    en, zh = _render(tmp_path, package)
    found = _codes(parity.lint_chinese_memo_pair(en, zh), "number_mismatch")
    assert len(found) == parity._NUMBER_FINDING_CAP
    assert found[-1].snippet.endswith("(+2 more)")


def test_figures_parse_money_multiples_and_percentages():
    def kinds(text, **kw):
        return sorted((f.kind, float(f.value)) for f in parity.figures(text, **kw))

    assert kinds("$24M and 30–36x at 12.5%") == [("%", 12.5), ("money:USD", 24e6), ("x", 30.0), ("x", 36.0)]
    assert kinds("RMB 3.2bn / HK$1.2B / €4.10bn") == [("money:CNY", 3.2e9), ("money:EUR", 4.1e9), ("money:HKD", 1.2e9)]
    assert kinds("32 亿元人民币，550–660 亿美元", chinese=True) == [
        ("money:CNY", 3.2e9), ("money:USD", 5.5e10), ("money:USD", 6.6e10)
    ]
    # never a figure: model names, rounds, dates, 4x4, x86, [S3] citations
    assert kinds("Series B, B200, GPT-4, 5G, 2026-Q2, 4x4, x86, 2x2, [S3]") == []
    assert all(not f.reportable for f in parity.figures("两倍，24 亿美元", chinese=True))


def test_the_sources_section_is_not_compared(tmp_path):
    package = _clean_package()
    package["sources"][0]["treatment"] = {"en": "Revenue of $9.9B.", "zh": "收入数据。"}
    en, zh = _render(tmp_path, package)
    assert not _codes(parity.lint_chinese_memo_pair(en, zh), "number_mismatch")


GLOSSARY = """## Chinese memo style guide

### Glossary
| English | 中文 | Avoid |
|---|---|---|
| run-rate (revenue) | 年化收入 | 运行率、年化运行率 |
| valuation | 估值 | — |
| cash runway | 现金可支撑时间 | 跑道、现金跑道 |
| bear case (to confirm / 待团队确认) | 悲观情形 | 熊市情形 |

### After the table
| not | a | glossary |
"""


def test_parse_glossary_reads_the_style_guide_table():
    terms = parity.parse_glossary(GLOSSARY)
    assert [(t.english, t.chinese, t.avoid) for t in terms] == [
        ("run-rate (revenue)", "年化收入", ("运行率", "年化运行率")),
        ("cash runway", "现金可支撑时间", ("跑道", "现金跑道")),
        ("bear case", "悲观情形", ("熊市情形",)),
    ]
    assert parity.parse_glossary("no table here") == []


def test_the_real_style_guide_parses_when_present():
    from pathlib import Path

    real = Path(parity.__file__).resolve().parents[1] / "skills" / "memo" / "zh_style.md"
    if not real.exists():
        pytest.skip("skills/memo/zh_style.md not written yet")
    terms = parity.parse_glossary(real.read_text(encoding="utf-8"))
    assert terms and all(t.chinese and t.avoid for t in terms)
    assert all("—" not in t.avoid for t in terms)


def test_glossary_drift_is_p2_and_absent_guide_means_nothing(tmp_path, monkeypatch):
    package = _clean_package()
    package["sections"][1]["blocks"][0]["text"] = {
        "en": "The run-rate reached $24M and the cash runway is 18 months.",
        "zh": "年化运行率达到 $24M，现金跑道为 18 个月。运行率仍在上升。",
    }
    en, zh = _render(tmp_path, package)
    assert not _codes(parity.lint_chinese_memo_pair(en, zh), "glossary_variant")
    guide = tmp_path / "zh_style.md"
    guide.write_text(GLOSSARY, encoding="utf-8")
    monkeypatch.setattr(parity, "ZH_STYLE_PATH", guide)
    found = _codes(parity.lint_chinese_memo_pair(en, zh), "glossary_variant")
    assert {f.severity for f in found} == {"P2"}
    # "运行率" inside "年化运行率" is reported as the longer variant, plus the
    # bare one in the next sentence; "跑道" inside "现金跑道" likewise
    messages = sorted(f.suggestion for f in found)
    assert any("avoids 年化运行率" in m for m in messages)
    assert any("avoids 现金跑道" in m for m in messages)
    assert any(m.endswith("avoids 运行率.") for m in messages)
    assert not any(m.endswith("avoids 跑道.") for m in messages)
    assert not parity.lint_chinese_memo_pair(en, zh).has_blocking_findings


def test_glossary_skips_the_structures_own_titles(tmp_path, monkeypatch):
    from server import memo_structure

    guide = tmp_path / "zh_style.md"
    guide.write_text(
        "| English | 中文 | Avoid |\n|---|---|---|\n| cash burn | 现金消耗 | 烧钱 |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(parity, "ZH_STYLE_PATH", guide)
    shape = parity._DocShape(
        path=tmp_path / "zh.docx",
        locale="zh",
        blocks=[
            parity._DocBlock("paragraph", "5. 增长更健康还是更烧钱", "paragraph 1", "financial_analysis"),
            parity._DocBlock("paragraph", "公司仍在烧钱。", "paragraph 2", "financial_analysis"),
        ],
        section_ids=[],
        table_count=0,
        paragraph_count=2,
        callout_like_table_count=0,
    )
    v2 = memo_structure.load_structure("late", 2)
    found = parity._glossary_findings(shape, v2)
    assert [f.location for f in found] == ["paragraph 2"]


def test_a_blank_corner_header_cell_passes_the_chinese_gate(tmp_path):
    package = _clean_package()
    table = copy.deepcopy(package["sections"][0]["blocks"][2])
    table.pop("component", None)
    table["title"] = {"en": "Revenue by year", "zh": "分年度收入"}
    table["headers"] = ["", "2025", "2026"]
    table["rows"] = [[{"en": "Revenue", "zh": "收入"}, "$86M", "$118M"]]
    package["sections"][1]["blocks"].append(table)
    memo_docx_renderer.validate_package(package)
    en, zh = _render(tmp_path, package)
    result = parity.lint_chinese_memo_pair(en, zh)
    assert result.findings == [], [f.to_dict() for f in result.findings]


def test_the_content_checks_never_fail_the_gate(tmp_path, monkeypatch):
    en, zh = _render(tmp_path, _clean_package())

    def boom(*_args, **_kwargs):
        raise RuntimeError("regex exploded")

    monkeypatch.setattr(parity, "_content_findings", boom)
    result = parity.lint_chinese_memo_pair(en, zh)
    assert [f.code for f in result.findings] == ["parity_content_check_error"]
    assert result.findings[0].severity == "P2" and not result.has_blocking_findings
