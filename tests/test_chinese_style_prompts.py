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
