"""English-only leaves ({"en": ...} with no zh key) must be translated,
not skipped as "already translated" (ZaiNar 2026-09-23__071431: six Company
Overview paragraphs came back that way and the Chinese failed validation)."""
from __future__ import annotations

import json

from server import claude_runner


def _package():
    return {
        "company": {"name": {"en": "Acme", "zh": "Acme"}},
        "sections": [
            {
                "id": "company_overview",
                "blocks": [
                    {"type": "heading", "text": {"en": "Company Overview", "zh": "公司概况"}},
                    {"type": "paragraph", "text": {"en": "Founded in 2017."}},
                    {"type": "paragraph", "text": {"en": "Sells software.", "zh": "销售软件。"}},
                ],
            }
        ],
        "generated_with": {"engine": "claude"},
    }


def test_ensure_zh_slots_adds_only_to_english_only_leaves():
    package = _package()
    assert claude_runner.ensure_zh_slots(package) == 1
    assert package["sections"][0]["blocks"][1]["text"] == {"en": "Founded in 2017.", "zh": ""}
    # untouched: complete leaves and non-localized dicts
    assert package["sections"][0]["blocks"][2]["text"]["zh"] == "销售软件。"
    assert package["generated_with"] == {"engine": "claude"}
    assert claude_runner.ensure_zh_slots(package) == 0


def test_a_missing_slot_now_counts_as_needing_translation():
    package = _package()
    claude_runner.ensure_zh_slots(package)
    assert claude_runner._has_blank_zh(package["sections"][0])
    assert claude_runner._count_blank_zh(package) == 1


def test_the_parallel_chinese_pass_does_not_skip_an_english_only_section(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    en_path = run_dir / "logs" / "memo_package.en.json"
    en_path.write_text(json.dumps(_package()), encoding="utf-8")
    dispatched: list[str] = []

    def fake_unit(**kwargs):
        dispatched.append(str(kwargs.get("unit_label") or kwargs.get("label") or ""))
        raise RuntimeError("stop after dispatch")

    # Stop at the first unit translation: all that matters is that the
    # section was queued rather than reported as already translated.
    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", lambda **kw: fake_unit(**kw))
    try:
        claude_runner.run_memo_fast_bilingual_package_parallel(
            run_dir=run_dir, company_name="Acme", run_id="r", english_package_path=en_path,
            only_missing=True,
        )
    except Exception:  # noqa: BLE001
        pass
    assert dispatched, "the English-only section was skipped as already translated"


def test_the_registry_filter_drops_the_placeholder_note():
    from server import memo_inputs

    entry, excluded = memo_inputs.filtered_registry_entry(
        {"id": "x", "demo_data_note": "Placeholder values from the v2 design mock", "name": "X"}
    )
    assert "demo_data_note" not in entry
    assert any("demo_data_note" in item for item in excluded)
