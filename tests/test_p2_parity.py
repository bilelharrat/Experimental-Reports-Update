"""Chinese parity round 2 (I23): Latin-only lines in Chinese cells and
paragraphs, source tags glued to the word before them, and drift from the
run's frozen glossary. All P1/P2 — none may block — and quiet on a clean
pair."""
from __future__ import annotations

import json

import pytest

import test_memo_docx_renderer as base
from server import memo_chinese_parity as parity
from server import memo_docx_renderer


@pytest.fixture(autouse=True)
def no_style_glossary(monkeypatch, tmp_path):
    monkeypatch.setattr(parity, "ZH_STYLE_PATH", tmp_path / "absent_zh_style.md")


def _codes(result, code):
    return [f for f in result.findings if f.code == code]


def _package_with(blocks):
    return {"sections": [{"id": "company_overview", "blocks": blocks}, {"id": "sources", "blocks": [
        {"type": "paragraph", "text": {"en": "secondary press report", "zh": "secondary press report"}}
    ]}]}


def test_latin_only_lines_and_leading_english_labels_are_p1():
    package = _package_with([
        {"type": "paragraph", "text": {"en": "Business model — 7/10.", "zh": "business model and unit economics — 7/10, adequate。纯软件授权可产生 75% 的毛利率 [S1]。"}},
        {"type": "paragraph", "text": {"en": "Ticker and figures.", "zh": "NASDAQ: NN · $4.02M · S7 · 2026-06-30"}},
        {"type": "table", "rows": [[{"en": "Owner", "zh": "负责人"}, {"en": "deal lead", "zh": "deal lead"}]]},
        {"type": "paragraph", "text": {"en": "Fine.", "zh": "正常的中文句子。"}},
    ])
    findings = parity.untranslated_zh_lines(package)
    assert [f.severity for f in findings] == ["P1", "P1"]
    assert findings[0].location == "company_overview blocks[0].text"
    assert "English label" in findings[0].suggestion
    assert findings[1].location.endswith("rows[0][1]")
    # The sources section is never checked.
    assert all("sources" not in f.location for f in findings)


def test_glossary_terms_are_allowed_latin():
    package = _package_with([
        {"type": "paragraph", "text": {"en": "Arm Total Design membership.", "zh": "Arm Total Design 生态成员。"}},
        {"type": "table", "rows": [[{"en": "Program", "zh": "项目"}, {"en": "Arm Total Design", "zh": "Arm Total Design"}]]},
    ])
    glossary = [{"en": "Arm Total Design", "zh": "Arm Total Design"}, {"en": "sounding reference signal", "zh": "探测参考信号"}]
    # A proper noun (capitalised words) passes with or without a glossary.
    assert parity.untranslated_zh_lines(package) == []
    assert parity.untranslated_zh_lines(package, glossary=glossary) == []
    # A lowercase glossary term left in English is allowed only because the
    # glossary lists it; without the glossary it is flagged.
    lower = _package_with([{"type": "table", "rows": [[{"en": "x", "zh": "x"}, {"en": "sounding reference signal", "zh": "sounding reference signal"}]]}])
    assert len(parity.untranslated_zh_lines(lower)) == 1
    assert parity.untranslated_zh_lines(lower, glossary=glossary) == []


def test_glued_citation_tags_are_p2_in_package_and_document(tmp_path):
    package = _package_with([
        {"type": "paragraph", "text": {"en": "SAM [C7] is $12.5B [S3].", "zh": "软件SAM[C7] 为 125 亿美元 [S3]。"}},
        {"type": "paragraph", "text": {"en": "Watch [S1].", "zh": "保持观望S1。"}},
        {"type": "paragraph", "text": {"en": "Spaced [S1].", "zh": "保持观望 [S1]。"}},
    ])
    findings = parity.glued_citation_findings(package)
    assert [f.severity for f in findings] == ["P2"] and findings[0].code == "citation_glued"
    assert "软件SAM[C7]" in findings[0].snippet

    class Block:
        def __init__(self, text, kind="paragraph", section_id="company_overview"):
            self.text, self.kind, self.section_id, self.location = text, kind, section_id, "paragraph 3"

    class Shape:
        blocks = [Block("软件SAMC7 为 125 亿美元 S3。"), Block("资本承诺S1。"), Block("观望 S1。"), Block("标题S1", kind="heading")]

    doc_findings = parity.glued_citation_findings(Shape())
    assert len(doc_findings) == 2 and {f.code for f in doc_findings} == {"citation_glued"}


def test_term_drift_needs_the_runs_glossary(tmp_path):
    package = _package_with([
        {"type": "paragraph", "text": {"en": "Phase-based time synchronisation.", "zh": "分阶段时间同步。"}},
        {"type": "paragraph", "text": {"en": "The phase-based approach again.", "zh": "阶段式方法。"}},
        {"type": "paragraph", "text": {"en": "And phase-based once more.", "zh": "按阶段再次。"}},
    ])
    assert parity.glossary_term_drift(package, None) == []
    findings = parity.glossary_term_drift(package, [{"en": "phase-based", "zh": "分阶段"}])
    assert len(findings) == 1 and findings[0].severity == "P1" and findings[0].code == "term_drift"
    assert "2 of 3" in findings[0].suggestion and findings[0].location == "company_overview blocks[1].text"
    # One rendering everywhere: no drift.
    consistent = _package_with([
        {"type": "paragraph", "text": {"en": "Phase-based sync.", "zh": "分阶段同步。"}},
        {"type": "paragraph", "text": {"en": "phase-based again.", "zh": "分阶段再次。"}},
    ])
    assert parity.glossary_term_drift(consistent, [{"en": "phase-based", "zh": "分阶段"}]) == []


def test_load_run_glossary_reads_logs_and_never_raises(tmp_path):
    assert parity.load_run_glossary(tmp_path) == []
    assert parity.load_run_glossary(None) == []
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "glossary.json").write_text("not json", encoding="utf-8")
    assert parity.load_run_glossary(tmp_path) == []
    (tmp_path / "logs" / "glossary.json").write_text(
        json.dumps({"terms": [{"en": "CSI", "zh": "信道状态信息"}, {"zh": "孤儿"}, "junk"]}), encoding="utf-8"
    )
    assert parity.load_run_glossary(tmp_path) == [{"en": "CSI", "zh": "信道状态信息"}]


def test_pair_lint_uses_the_glossary_next_to_the_memo_and_stays_quiet_when_clean(tmp_path):
    package = base._package()
    package["company"]["stage"] = {"en": "Late-stage / pre-IPO", "zh": "后期 / IPO 前"}
    package["company"]["round"] = {"en": "Series D context", "zh": "D 轮背景"}
    out_en = tmp_path / "run" / "memo" / "en.docx"
    out_zh = tmp_path / "run" / "memo" / "zh.docx"
    memo_docx_renderer.render_memos(package, out_en=out_en, out_zh=out_zh)
    clean = parity.lint_chinese_memo_pair(out_en, out_zh, package=package)
    assert not any(f.code in {"zh_line_untranslated", "citation_glued", "term_drift"} for f in clean.findings)

    # A glossary in <run>/logs (the default run dir is two levels above the memo).
    package["sections"][0]["blocks"].append(
        {"type": "paragraph", "text": {"en": "The embodied AI stack is new.", "zh": "该具身智能体系是新的。"}}
    )
    (tmp_path / "run" / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "run" / "logs" / "glossary.json").write_text(
        json.dumps([{"en": "embodied AI", "zh": "具身 AI"}]), encoding="utf-8"
    )
    memo_docx_renderer.render_memos(package, out_en=out_en, out_zh=out_zh)
    result = parity.lint_chinese_memo_pair(out_en, out_zh, package=package)
    drift = _codes(result, "term_drift")
    assert len(drift) == 1 and drift[0].severity == "P1"
    assert not result.has_blocking_findings
    # An explicit glossary wins over the file; an empty one switches the check off.
    assert _codes(parity.lint_chinese_memo_pair(out_en, out_zh, package=package, glossary=[]), "term_drift") == []
    assert _codes(parity.lint_chinese_memo_pair(out_en, out_zh, package=package, run_dir=tmp_path / "elsewhere"), "term_drift") == []


# ---- Gemini's Chinese, 2026-09-23 round 3 ------------------------------------------------


def test_an_english_sentence_inside_chinese_is_untranslated():
    """Gemini's translator kept pinned sentences in English, sometimes with
    a Chinese gloss in brackets; the whole-block rule could not see them
    because the block also held Chinese."""
    from server import memo_chinese_parity as m

    copied = (
        "后续核实要点：采纳进展。Impact: Delays in carrier core network certification can extend "
        "enterprise deployment cycles past 18 months and demand margin-dilutive revenue shares [S4]。（影响：认证延误）"
    )
    assert m.embedded_english_sentence(copied).startswith("Impact: Delays in carrier")
    assert m.english_left_untranslated(copied)
    assert m.embedded_english_sentence("工具与载体：No vehicle or terms on file (pipeline stage: sourced, no allocation offered)。")
    # Names, programme titles and lists of names stay English and are fine.
    for fine in (
        "2026 年 9 月，Arm 将 ZaiNar 列为 Arm Total Design for Physical AI 的创始定位合作伙伴",
        "投资方包括 SoftBank、Samsung Electronics、Future Ventures、AME Cloud Ventures 与 Evolution VC Partners",
        "投资者包括 Future Ventures, AME Cloud Ventures, Evolution VC Partners, SoftBank Vision Fund and Samsung Electronics Co Ltd 的支持",
        "Memorial Hermann Health System 正在开展设备追踪试点",
    ):
        assert m.embedded_english_sentence(fine) is None, fine
        assert not m.english_left_untranslated(fine)


def test_a_translation_that_swaps_a_figure_is_caught():
    from server import memo_chinese_parity as m

    # ZaiNar 2026-09-23 (Gemini): both were live translation errors.
    assert m.translation_changes_a_number(
        "ZaiNar must actively assert its 95+ issued patents [S1, S7].", "ZaiNar 必须积极运用其 90 余项已授权专利 [S1, S7]。"
    )
    assert m.translation_changes_a_number(
        "Recognized ARR must expand past $100M to $130M.", "确认的 ARR 必须扩张突破 1.0 亿至 1.35 亿美元。"
    )
    assert m.translation_changes_a_number("the 25% dilution", "40% 的稀释")
    # Same values in the other money form, dates, rounding, spelled-out and added figures.
    for en, zh in (
        ("Revenue of $1,500M in 2031 [C4]", "2031 年收入 15 亿美元 [C4]"),
        ("closed on February 19, 2026 at $579.37M post-money", "于 2026 年 2 月 19 日以约 5.79 亿美元投后估值完成"),
        ("a quarter of the $450M aggregate", "$450M 合计金额的四分之一（约 $112.5M）"),
        ("$5.0B GPS-alternative pipeline (as of 2026-02-20) [S4]", "50亿美元GPS替代商业管线（截至2026年2月20日）[S4]"),
        ("$18.35B in 2026 to $50.10B by 2031, a 22.3% CAGR", "2026 年 $18.35B，到 2031 年增长至 $50.10B，CAGR 为 22.3%"),
        ("a tenfold spread", "十倍差距"),
    ):
        assert not m.translation_changes_a_number(en, zh), en


def test_adoption_rejects_a_swapped_figure_and_keeps_the_slot_for_the_chaser():
    from server import claude_runner

    source = {"en": "Its 95+ issued patents [S7].", "zh": ""}
    claude_runner._adopt_zh_translations(source, {"en": source["en"], "zh": "其 90 余项已授权专利 [S7]。"})
    assert source["zh"] == ""
    claude_runner._adopt_zh_translations(source, {"en": source["en"], "zh": "其 95 项以上已授权专利 [S7]。"})
    assert source["zh"] == "其 95 项以上已授权专利 [S7]。"


def test_chinese_money_keeps_the_english_form_when_rendered():
    """Gemini wrote "$30M" in one section and "3000万美元" in the next."""
    from server import memo_docx_renderer as r

    assert r.normalize_zh_money("签署了逾 3,000 万美元的数据授权合同") == "签署了逾 $30M 的数据授权合同"
    assert r.normalize_zh_money("对应 5.7937 亿美元投后估值") == "对应 $579.37M 投后估值"
    assert r.normalize_zh_money("合理估值区间：4 亿至 7.5 亿美元") == "合理估值区间：$400M 至 $750M"
    assert r.normalize_zh_money("退出估值 41.60 亿美元，净额 9560万美元") == "退出估值 $4.16B，净额 $95.6M"
    assert r.normalize_zh_money("50亿美元GPS替代管线") == "$5B GPS替代管线"
    assert r.normalize_zh_money("每股 23.09 美元") == "每股 $23.09"
    # Chinese-numeral amounts and an idiomatic "1 美元" are left alone.
    for unchanged in ("数亿美元与十亿美元级别", "每 1 美元仍只能拿回 72 美分", "估值 $1.0B"):
        assert r.normalize_zh_money(unchanged) == unchanged
    # The renderer's Chinese path applies it with the placeholders.
    assert r._loc({"en": "x", "zh": "拟投 3000万美元，Proposed amount: [TO BE DETERMINED BY IC]"}, "zh") == (
        "拟投 $30M，Proposed amount: 【待投委会确定】"
    )


@pytest.mark.parametrize(
    "en, zh",
    [
        # 万/亿 count anything, not only dollars.
        ("1.2 million users", "120万用户"),
        ("RMB 5 billion", "50亿元人民币"),
        ("HK$ 3.5 billion", "35亿港元"),
        ("12,000 units", "1.2万台"),
        ("about 2.5 million users", "用户约 250 万"),
        # A range shares its second number's scale or unit.
        ("a fair-value range of $400-750M", "合理估值区间：4 亿至 7.5 亿美元"),
        ("gross margin of 20-30%", "毛利率 20%至30%"),
        # A number right after a Chinese character is whole.
        ("1,200 enterprise customers", "拥有1,200家企业客户"),
        # Metres and tonnes are units, not millions and trillions.
        ("range of 50 m", "50 米的范围"),
        ("a 5,000 m² facility", "5000 平方米的设施"),
        ("a 100 t payload", "100吨有效载荷"),
    ],
)
def test_faithful_translations_keep_their_numbers(en, zh):
    assert not parity.translation_changes_a_number(en, zh)


@pytest.mark.parametrize(
    "en, zh",
    [
        ("the company holds 95+ issued patents", "公司拥有90余项已授权专利"),
        ("gross margin of 62%", "毛利率为26%"),
        ("2,000 employees", "3000名员工"),
    ],
)
def test_a_swap_right_after_a_chinese_character_is_caught(en, zh):
    assert parity.translation_changes_a_number(en, zh)


@pytest.mark.parametrize(
    "zh",
    [
        "该公司发布了《State of the Market for Indoor Positioning in the Enterprise》报告。",
        "投资方包括 Bank of America, The Carlyle Group and Temasek 等机构。",
        "运营商核心网认证（Carrier Core Network Certification for the Enterprise Market）",
        "见 https://example.com/the_company_is_raising_a_series_b_of_the_year 。",
    ],
)
def test_names_titles_and_urls_are_not_embedded_sentences(zh):
    assert parity.embedded_english_sentence(zh) is None
