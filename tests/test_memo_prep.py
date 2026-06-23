from __future__ import annotations

from server import claude_runner, memo_prep


def test_early_stage_round_is_scope_warning_not_failure():
    assessment = memo_prep._assess_stage(
        {"latest_funding": {"round": "Series A"}}
    )

    assert assessment["outcome"] == "warn"
    assert assessment["classification"] == "early-stage"
    assert "series a" in assessment["reason"]


def test_low_total_funding_is_scope_warning_not_failure():
    assessment = memo_prep._assess_stage({"total_funding_usd": "$3M"})

    assert assessment["outcome"] == "warn"
    assert assessment["classification"] == "early-stage"


def test_nonprofit_scope_check_remains_hard_failure():
    assessment = memo_prep._assess_stage({"status": "nonprofit"})

    assert assessment["outcome"] == "fail"
    assert assessment["classification"] == "out-of-scope"


def test_investment_memo_prompt_carries_scope_warning_override(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
        scope_check={
            "outcome": "warn",
            "classification": "early-stage",
            "reason": "Latest funding round 'series a' is early-stage.",
        },
        warnings=["Latest funding round 'series a' is early-stage."],
    )

    assert "Scope-warning override from prep" in prompt
    assert "Proceed with the memo anyway" in prompt
    assert "Do **not** stop or decline solely because" in prompt


def test_investment_memo_prompt_includes_human_exec_voice_contract(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
    )

    assert "Human Executive Memo Voice Contract" in prompt
    assert "exec-ready LP-facing sell-side investment memo" in prompt
    assert "investment case under uncertainty" in prompt
    assert "bsh_allocation" not in prompt
    assert "BSH target allocation" not in prompt
    assert "The memo therefore..." in prompt
    assert "Top 3 Decision Questions" in prompt
    assert "Proceed if confirmed" in prompt
    assert "would be misleading to forecast precisely" in prompt
    assert "not revenue-recognized" in prompt
    assert "Final Prose QA Requirements" in prompt


def test_investment_memo_prompt_uses_fixed_docx_renderer(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
    )

    assert "Fixed DOCX renderer contract" in prompt
    assert "logs/memo_package.json" in prompt
    assert "worker will invoke `server.memo_docx_renderer` directly" in prompt
    assert "Do not run `python -m" in prompt
    assert "Do **not** write or edit a per-run renderer script" in prompt
    assert "build_memo.py" in prompt
    assert "job is to author a complete `memo_package.json`" in prompt
    assert "not rendering code" in prompt


def test_investment_memo_prompt_bans_source_tokens_and_scaffold_labels(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="ZaiNar, Inc.",
        company_slug="zainar-inc",
        run_id="2026-06-22__093627",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
    )

    assert "supersedes any older skill instruction" in prompt
    assert "inline source markers" in prompt
    assert "Sources, Source Classes, and Fact Reference Index" in prompt
    assert "Memo spine requirement" in prompt
    assert "Critical Reality Check" in prompt
    assert "present-state" in prompt
    assert "upside-state" in prompt
    assert "soft instrument" in prompt
    assert "hard IP wall" in prompt
    assert "em dash bridging" in prompt
    assert "must include at least one inline citation marker" not in prompt
    assert "Render a **Critical Reality Check" not in prompt
    assert "Critical Reality Check (for BSH)** evidence-summary callout" not in prompt


def test_investment_memo_prompt_includes_serena_lessons(tmp_path):
    lessons_path = tmp_path / "serena_training" / "generalist" / "serena_memo_lessons.md"
    lessons_path.parent.mkdir(parents=True)
    lessons_path.write_text("# Lessons\n- Lead with evidence.\n", encoding="utf-8")

    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
        lessons_path=lessons_path,
    )

    assert str(lessons_path) in prompt
    assert "Current company evidence" in prompt
    assert "override stale or contradictory lessons" in prompt
