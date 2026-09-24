"""Page one names the engine, model and template a memo was written with.

The owner compares memos written by different engines and templates side
by side; the cover line is how two memos on the same company are told
apart without opening the run folder.
"""
import copy

import docx

from server import memo_docx_renderer
from tests.memo_v2_fixture import late_compact_package
from tests.test_memo_docx_renderer import _package as v1_package


def _stamp(package: dict, **generated) -> dict:
    package = copy.deepcopy(package)
    package.setdefault("run", {})["generated_with"] = generated
    return package


def test_the_line_names_engine_model_template_quality_and_code():
    package = _stamp(
        late_compact_package(),
        engine="claude",
        writer_model="claude-opus-5-5",
        translation_model="claude-sonnet-5",
        quality="balanced",
        template="ic_v2",
        structure={"stage": "late_compact", "version": 1, "mode": "compact"},
        code_version="f248004",
    )
    en = memo_docx_renderer.generated_with_line(package, "en")
    assert en == (
        "Generated with Claude (claude-opus-5-5) · Founder's IC template (v2, compact)"
        " · Balanced quality · code f248004"
    )
    zh = memo_docx_renderer.generated_with_line(package, "zh")
    assert zh.startswith("生成：Claude（claude-opus-5-5） · 创始人投委会模板（v2，精简版）")
    assert "中文翻译：claude-sonnet-5" in zh


def test_gemini_on_the_standard_memo():
    package = _stamp(v1_package(), engine="gemini", writer_model="gemini-3.8-pro", template="standard")
    assert memo_docx_renderer.generated_with_line(package, "en") == (
        "Generated with Gemini (gemini-3.8-pro) · Standard memo (v1)"
    )


def test_an_older_package_still_names_its_template():
    package = copy.deepcopy(v1_package())
    package["structure"] = {"stage": "late", "version": 1, "mode": None}
    assert memo_docx_renderer.generated_with_line(package, "en") == "Standard memo (v1)"
    package["structure"] = {"stage": "late_compact", "version": 1, "mode": None}
    assert memo_docx_renderer.generated_with_line(package, "zh") == "创始人投委会模板（v2，精简版）"
    package.pop("structure")
    assert memo_docx_renderer.generated_with_line(package, "en") == ""


def test_the_line_is_on_page_one(tmp_path):
    package = _stamp(
        v1_package(), engine="claude", writer_model="claude-opus-5-5", template="standard", quality="best"
    )
    en_path, zh_path = tmp_path / "en.docx", tmp_path / "zh.docx"
    memo_docx_renderer.render_memos(package, out_en=en_path, out_zh=zh_path, strict_sources=False)
    for path, needle in ((en_path, "Generated with Claude (claude-opus-5-5)"), (zh_path, "生成：Claude（claude-opus-5-5）")):
        text = "\n".join(p.text for p in docx.Document(path).paragraphs[:12])
        assert needle in text, text
