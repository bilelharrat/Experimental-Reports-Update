"""Round 2, P1b follow-up (I24 spine side): the v1 spine's OPTIONAL
`base_case_outcome` sentence and `calculations` notes.

Both are optional in MEMO_FAST_ENGLISH_SPINE_SCHEMA, asked for in the v1
spine prompt, printed on the shared fact sheet, and copied into
`package["calculations"]` on the v1 path exactly as v2 does. No existing
spine or package may fail. Fake runners only.
"""
from __future__ import annotations

import json
from pathlib import Path

from server import claude_runner, memo_structure

V2 = memo_structure.load_structure("late", 2)


def _v1_spine(with_pins: bool) -> dict:
    facts = {
        "recommendation_sentence": "Recommendation: pass on Generalist — no revenue base.",
        "key_metrics": [{"name": "ARR", "value": "$10M", "as_of": "2026-05-01", "source_ids": ["S1"]}],
        "scenarios": {"bear": "0.8x", "base": "1.5x", "bull": "2.4x"},
        "risks": [
            {"summary": f"Risk {n} is real.", "rating": f"{9 - n}/10", "likelihood": "Medium"}
            for n in range(4)
        ],
        "source_topics": {"S1": "Data room"},
    }
    if with_pins:
        facts["base_case_outcome"] = "Base case: $120M ARR by 2029 at a 10x exit returns 1.5x."
        facts["calculations"] = [
            {
                "id": "C1",
                "label": "Base-case exit value",
                "inputs": [
                    {"name": "ARR 2029", "value": "$120M", "ref": "assumption"},
                    {"name": "Exit multiple", "value": "10x", "ref": "S1"},
                ],
                "formula": "$120M × 10 = $1.2B",
                "result": "$1.2B",
                "meaning": "The base case exits at $1.2B.",
            }
        ]
    return {
        "package_skeleton": {
            "schema_version": 1,
            "company": {"name": "Generalist, Inc."},
            "run": {"run_id": "r1", "language": "en"},
            "sources": [{"id": "S1", "title": {"en": "Data room", "zh": ""}}],
        },
        "shared_facts": facts,
        "section_notes": {},
    }


def test_the_v1_spine_schema_takes_both_pins_as_optional():
    schema = claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA
    facts = schema["properties"]["shared_facts"]
    assert facts["properties"]["base_case_outcome"] == {"type": "string", "maxLength": 240}
    assert facts["properties"]["calculations"] == claude_runner._spine_calculations_schema()
    assert "base_case_outcome" not in facts["required"]
    assert "calculations" not in facts["required"]
    assert claude_runner._schema_errors(_v1_spine(False), schema) == []
    assert claude_runner._schema_errors(_v1_spine(True), schema) == []
    too_long = _v1_spine(True)
    too_long["shared_facts"]["base_case_outcome"] = "x" * 241
    assert claude_runner._schema_errors(too_long, schema)
    # The v2 schema still builds on the same base and keeps the pin.
    v2 = claude_runner.memo_fast_english_spine_schema(V2)
    assert "base_case_outcome" in v2["properties"]["shared_facts"]["properties"]
    assert memo_structure.SPINE_BASE_CASE_OUTCOME_FIELD == "base_case_outcome"


def test_the_v1_spine_prompt_asks_for_both_and_v2_keeps_its_own(tmp_path, monkeypatch):
    prompts: list[tuple[str, str]] = []

    def fake_runner(**kw):
        prompts.append((kw["prompt"], kw.get("role")))
        return {"package_skeleton": {}, "shared_facts": {}}, None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_runner)
    monkeypatch.setenv("BSH_MEMO_SPINE_HANDOFF", "off")
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    for structure in (memo_structure.LATE, V2):
        claude_runner.run_memo_fast_english_spine(
            run_dir=run_dir, company_name="G", common_context="ctx", add_dirs=[],
            structure=structure, handoff=False,
        )
    v1_prompt, v2_prompt = prompts[0][0], prompts[1][0]
    assert "`base_case_outcome` (optional, one sentence" in v1_prompt
    assert "`calculations` (optional)" in v1_prompt
    assert "never\n     send an empty list" in v1_prompt or "never send an empty list" in v1_prompt.replace("\n     ", " ")
    # v2 keeps its required calculation notes block and never asks twice.
    assert "Required notes:" in v2_prompt
    assert "`calculations` (optional)" not in v2_prompt
    assert "`base_case_outcome` (optional" not in v2_prompt


def test_the_fact_sheet_prints_the_pin_only_when_set():
    without = claude_runner._render_shared_facts_block(_v1_spine(False)["shared_facts"])
    assert "Base case outcome" not in without
    with_pins = claude_runner._render_shared_facts_block(_v1_spine(True)["shared_facts"])
    assert (
        "Base case outcome (pinned): Base case: $120M ARR by 2029 at a 10x exit "
        "returns 1.5x. — the executive summary's entry-price paragraph and the "
        "scenarios table's base row both state this sentence verbatim."
    ) in with_pins
    # The v1 sheet renders its calculation notes exactly as v2 does.
    assert "- C1 Base-case exit value: $120M × 10 = $1.2B → $1.2B" in with_pins
    assert "These 1 are the ONLY calculation ids that exist for this memo: [C1]" in with_pins
    # Everything else is byte-identical between the two sheets.
    stripped = "\n".join(
        line for line in with_pins.splitlines()
        if not line.startswith(("Base case outcome", "Calculation notes", "- C1"))
    )
    assert stripped == without


def test_the_v1_package_carries_the_pinned_calculations(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    spine = _v1_spine(True)
    spine["claude_cost_usd"] = 1.0
    spine["claude_duration_ms"] = 10
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", lambda **kw: (spine, None))
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_artifacts",
        lambda **kw: ({"analysis_artifacts": {"claim_register_md": "# Claim Register"}}, None),
    )
    monkeypatch.setattr(
        claude_runner, "_run_english_section",
        lambda **kw: (
            {"section": {"id": kw["section_id"], "blocks": [{"type": "paragraph", "text": {"en": "p [C1]", "zh": ""}}]}},
            None,
        ),
    )
    result, error = claude_runner.run_memo_fast_english_package_parallel(
        run_dir=run_dir, company_name="Generalist, Inc.", company_slug="generalist-inc",
        run_id="r1", settings_path=tmp_path / "s.md", companies_yaml_path=tmp_path / "c.yaml",
        memo_paths={"en": "memo/en.docx"},
    )
    assert error is None
    package = result["memo_package"]
    assert package["structure"] == memo_structure.LATE.meta()
    assert package["calculations"][0]["id"] == "C1"
    assert package["calculations"][0]["label"] == {"en": "Base-case exit value", "zh": ""}
    assert package["calculations"][0]["inputs"][0]["ref"] == "assumption"
    # The pinned sheet on disk keeps the sentence for the pin check.
    spine_payload = json.loads((run_dir / "logs" / "english_units" / "spine.json").read_text())
    assert spine_payload["shared_facts"]["base_case_outcome"].startswith("Base case:")


def test_a_v1_handoff_spine_may_leave_the_calculations_file_unwritten(tmp_path):
    plan = claude_runner._spine_piece_plan(tmp_path, claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA)
    by_stem = {entry[0]: entry for entry in plan}
    assert "base_case_outcome" in by_stem["verdict"][2]
    calc = by_stem["calculations"]
    assert calc[3] == ()  # no required key: optional
    # An absent optional piece is not an error and assembles to nothing.
    assert claude_runner._spine_piece_error(calc[5], calc[0], calc[2], calc[3]) is None
    Path(tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    for entry in plan:
        if entry[3]:
            entry[5].parent.mkdir(parents=True, exist_ok=True)
            entry[5].write_text(json.dumps({key: [] if key in ("sources", "key_metrics", "risks") else {} for key in entry[2]}), encoding="utf-8")
    spine = claude_runner._assemble_spine(plan)
    assert "calculations" not in spine["shared_facts"]
    # A required piece that is absent still fails loudly.
    verdict = by_stem["verdict"]
    verdict[5].unlink()
    assert "was never written" in claude_runner._spine_piece_error(verdict[5], verdict[0], verdict[2], verdict[3])
