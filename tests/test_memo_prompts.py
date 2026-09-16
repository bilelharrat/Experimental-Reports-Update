"""skills/memo/: the editorial prompt files load byte-for-byte into the
constants the pipeline uses, and passes.md drives the Phase 2 pass list."""

from __future__ import annotations

from server import claude_runner, memo_analysis, memo_prompts

PROMPT_FILES = {
    "voice_contract.md": "HUMAN_EXEC_MEMO_VOICE_CONTRACT",
    "structure_addendum.md": "MEMO_STRUCTURE_V2_ADDENDUM",
    "risk_card_v2.md": "MEMO_RISK_REGISTER_CONTRACT_V2",
    "risk_card_compact.md": "MEMO_RISK_REGISTER_CONTRACT_COMPACT",
}

EXPECTED_PASS_ORDER = [
    "numbers_integrity",
    "growth_bridge",
    "valuation_exit",
    "market_sizing",
    "competitive_position",
    "adoption_distribution",
    "team_governance",
    "alternative_explanations",
]


def test_prompt_files_back_the_constants():
    for filename, constant in PROMPT_FILES.items():
        path = memo_prompts.MEMO_SKILLS_DIR / filename
        assert path.exists(), filename
        text = memo_prompts.load_prompt(filename)
        assert text.strip(), filename
        assert not text.startswith("---"), f"{filename}: front matter leaked"
        assert getattr(claude_runner, constant) == text


def test_strip_front_matter_only_removes_a_leading_block():
    assert memo_prompts.strip_front_matter("---\nen_sha256: abc\n---\nbody\n") == "body\n"
    assert memo_prompts.strip_front_matter("body --- not front matter\n") == (
        "body --- not front matter\n"
    )


def test_passes_file_drives_the_phase2_pass_list():
    specs = memo_analysis._FAST_MEMO_PASSES
    assert [spec.pass_id for spec in specs] == EXPECTED_PASS_ORDER
    for spec in specs:
        assert spec.label and spec.artifact_filename.endswith(".md")
        assert spec.focus == " ".join(spec.focus.split())
        assert len(spec.focus) > 120, spec.pass_id
    market = next(s for s in specs if s.pass_id == "market_sizing")
    assert "NEVER discard an estimate" in market.focus


def test_parse_passes_round_trips_a_minimal_file():
    parsed = memo_prompts.parse_passes(
        "---\nkind: x\n---\n# Title\n\n## pass: alpha\n```yaml\nlabel: Alpha pass\n"
        "artifact: alpha.md\n```\nFirst line of\n  focus text.\n\n## pass: beta\n"
        "```yaml\nlabel: Beta\nartifact: beta.md\n```\nBeta focus.\n"
    )
    assert parsed == [
        {
            "pass_id": "alpha",
            "label": "Alpha pass",
            "artifact_filename": "alpha.md",
            "focus": "First line of focus text.",
        },
        {"pass_id": "beta", "label": "Beta", "artifact_filename": "beta.md", "focus": "Beta focus."},
    ]
