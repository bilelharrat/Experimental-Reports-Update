from pathlib import Path

from server import (
    claude_runner,
    companies_ai_public,
    deck_summary,
    text_analysis,
    weekly_stocks,
)
from server.chinese_style import INVESTMENT_RESEARCH_CHINESE_STYLE


def test_shared_chinese_style_mentions_bad_calques():
    assert "tailwind" in INVESTMENT_RESEARCH_CHINESE_STYLE
    assert "顺风" in INVESTMENT_RESEARCH_CHINESE_STYLE
    assert "credible second wave" in INVESTMENT_RESEARCH_CHINESE_STYLE
    assert "可信第二波" in INVESTMENT_RESEARCH_CHINESE_STYLE
    assert "keep the English" in INVESTMENT_RESEARCH_CHINESE_STYLE


def test_core_generation_prompts_include_chinese_style_guide():
    for prompt in (
        companies_ai_public.SYSTEM_PROMPT,
        deck_summary.SYSTEM_PROMPT,
        deck_summary.QUALITY_BAR,
        text_analysis.SYSTEM_PROMPT,
        weekly_stocks.SYSTEM_PROMPT,
    ):
        assert "CHINESE LOCALIZATION QUALITY BAR" in prompt
        assert "tailwind" in prompt
        assert "可信第二波" in prompt


def _repo_text(relative: str) -> str:
    return (Path(__file__).resolve().parents[1] / relative).read_text(
        encoding="utf-8"
    )


def test_console_language_directive_includes_chinese_style():
    text = claude_runner._console_language_directive("zh")
    assert "CHINESE LOCALIZATION QUALITY BAR" in text
    assert "tailwind" in text
    assert "可信第二波" in text


def test_markdown_skill_prompts_have_chinese_localization_rules():
    files = [
        "server/skills/bsh_investment_memo_latestage.md",
        "skills/memo/buffett.md",
        "server/skills/bsh_company_console.md",
        "server/skills/bsh_company_console_public.md",
        "server/skills/bsh_hormuz_console.md",
        "server/skills/bsh_hormuz_appendix.md",
        "pres/prompts/translate_zh.txt",
    ]
    for relative in files:
        text = _repo_text(relative)
        assert "tailwind" in text, relative
        assert "顺风" in text, relative


def test_investment_memo_skill_has_chinese_localization_rules():
    text = _repo_text("server/skills/bsh_investment_memo_latestage.md")
    assert "Chinese Localization Quality Bar" in text
    assert "tailwind" in text
    assert "顺风" in text
    assert "credible second wave" in text
    assert "可信第二波" in text


def test_buffett_memo_skill_has_chinese_localization_rules():
    text = _repo_text("skills/memo/buffett.md")
    assert "Chinese Localization Quality Bar" in text
    assert "tailwind" in text
    assert "顺风" in text
    assert "credible second wave" in text
    assert "可信第二波" in text
    assert "Warren" in text
    assert "Buy" in text
    assert "Too Hard" in text
    # BSH Research's voice, not Buffett's: "we" is BSH, 我们 in Chinese.
    assert "The first person is 我们 (BSH 研究)" in text
    assert "no 奥马哈 dateline" in text
    assert "暂不买入（买入价 ≤ X）" in text
    assert "台积电（TSMC）" in text
    # The Chinese team's editing surface exists and is loaded nowhere.
    twin = _repo_text("skills/memo/zh/buffett.md")
    assert twin.startswith("---\nen_sha256: ")
    assert "中文本地化质量标准" in twin


def test_buffett_skill_is_loaded_from_skills_memo_without_front_matter():
    text = claude_runner._load_buffett_skill_text()
    assert claude_runner._BUFFETT_SKILL_PATH.parent.name == "memo"
    assert not text.startswith("---")
    assert "name: bsh-buffett-investment-memo-v1" not in text
    assert text.lstrip().startswith("# Buffett-Method Memo")
    assert not (Path(__file__).resolve().parents[1] / "server/skills/bsh_buffett_investment_memo.md").exists()
