"""Round 2, P1b: Gemini per-role models (I16) and the writer model pin (I18)."""
from __future__ import annotations

import pytest

from server import claude_runner, memo_engine

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "BSH_MEMO_GEMINI_MODEL",
        "BSH_MEMO_GEMINI_MODEL_PRO",
        "BSH_GEMINI_MODEL",
        "BSH_MEMO_WRITER_MODEL",
        "BSH_MEMO_MODEL",
        "BSH_MEMO_MODEL_SECTION",
    ):
        monkeypatch.delenv(name, raising=False)


# ---- I16 -----------------------------------------------------------------------


def test_without_a_pro_model_every_gemini_role_runs_on_flash():
    # No gemini-3.8-pro exists (Google's list, 2026-09-23): unset, nothing
    # may be sent a guessed model name.
    for role in ("ENGLISH", "SECTION", "TRANSLATION", None):
        for quality in ("best", "balanced", "economy"):
            assert memo_engine.gemini_model_for_role(role, quality) == "gemini-3.8-flash"


def test_gemini_writers_run_on_pro_and_the_rest_on_flash_below_best(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_GEMINI_MODEL_PRO", "gemini-3.8-pro")
    for role in ("ENGLISH", "SPINE", "SECTION", "REPAIR", "ARTIFACTS"):
        for quality in ("best", "balanced", "economy"):
            assert memo_engine.gemini_model_for_role(role, quality) == "gemini-3.8-pro"
    for role in ("ANALYSIS_PASS", "SPINE_CHECK", "TRANSLATION", None):
        assert memo_engine.gemini_model_for_role(role, "best") == "gemini-3.8-pro"
        assert memo_engine.gemini_model_for_role(role, "balanced") == "gemini-3.8-flash"
        assert memo_engine.gemini_model_for_role(role, "economy") == "gemini-3.8-flash"
    # Unknown tier reads as "best".
    assert memo_engine.gemini_model_for_role("TRANSLATION", "weird") == "gemini-3.8-pro"


def test_gemini_model_overrides(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_GEMINI_MODEL_PRO", "gemini-4-pro")
    assert memo_engine.gemini_model_for_role("SECTION", "economy") == "gemini-4-pro"
    assert memo_engine.gemini_model_for_role("TRANSLATION", "economy") == "gemini-3.8-flash"
    monkeypatch.setenv("BSH_GEMINI_MODEL", "gemini-3.8-flash-lite")
    assert memo_engine.gemini_model_for_role("TRANSLATION", "economy") == "gemini-3.8-flash-lite"
    # The owner's blanket pin still wins for every role.
    monkeypatch.setenv("BSH_MEMO_GEMINI_MODEL", "gemini-pinned")
    for role in ("SECTION", "TRANSLATION", None):
        for quality in ("best", "economy"):
            assert memo_engine.gemini_model_for_role(role, quality) == "gemini-pinned"
    assert memo_engine.memo_gemini_model() == "gemini-pinned"


def test_a_gemini_stage_uses_and_records_its_role_model(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_GEMINI_MODEL_PRO", "gemini-3.8-pro")
    seen: list[dict] = []
    monkeypatch.setattr(memo_engine.gemini_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        memo_engine.gemini_runner, "run_structured_prompt_with_meta",
        lambda **kw: (seen.append(kw) or ({"ok": True}, {}, None)),
    )
    run_dir = tmp_path / "r"
    (run_dir / "logs").mkdir(parents=True)
    memo_engine.register_run_engine(run_dir, "gemini")
    claude_runner.register_memo_run_quality(run_dir, "economy")
    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact_inner",
        lambda **kw: pytest.fail("gemini run must not spawn the CLI"),
    )
    for role in ("TRANSLATION", "SECTION"):
        claude_runner._run_memo_local_json_artifact(
            prompt="p", schema=SCHEMA, run_dir=run_dir, progress=None,
            progress_message="m", timeout_label="t", timeout_sec=60,
            model="sonnet", effort="medium", role=role,
        )
    assert [kw["model"] for kw in seen] == ["gemini-3.8-flash", "gemini-3.8-pro"]
    assert claude_runner.memo_run_models(run_dir) == {
        "TRANSLATION": "gemini-3.8-flash",
        "SECTION": "gemini-3.8-pro",
    }
    memo_engine.clear_run_engine(run_dir)


# ---- I18 -----------------------------------------------------------------------


def test_writer_pin_is_a_no_op_unless_set(tmp_path):
    claude_runner.register_memo_run_quality(tmp_path, "best")
    assert claude_runner.memo_writer_model() is None
    for role in claude_runner.MEMO_WRITER_ROLES:
        assert claude_runner._memo_role_model(role, tmp_path) is None
    assert claude_runner._memo_role_model("TRANSLATION", tmp_path) == "sonnet"


def test_writer_pin_covers_the_five_writer_roles_only(tmp_path, monkeypatch):
    claude_runner.register_memo_run_quality(tmp_path, "economy")
    monkeypatch.setenv("BSH_MEMO_WRITER_MODEL", "opus")
    assert claude_runner.MEMO_WRITER_ROLES == {"ENGLISH", "SPINE", "SECTION", "REPAIR", "ARTIFACTS"}
    for role in claude_runner.MEMO_WRITER_ROLES:
        assert claude_runner._memo_role_model(role, tmp_path) == "opus"
    # Research, checks and translation are untouched by the writer pin.
    assert claude_runner._memo_role_model("ANALYSIS_PASS", tmp_path) == "sonnet"
    assert claude_runner._memo_role_model("SPINE_CHECK", tmp_path) == "sonnet"
    assert claude_runner._memo_role_model("TRANSLATION", tmp_path) == "sonnet"
    # Effort is not the pin's business.
    assert claude_runner._memo_role_effort("SECTION", tmp_path) == "medium"


def test_writer_pin_precedence(tmp_path, monkeypatch):
    claude_runner.register_memo_run_quality(tmp_path, "economy")
    monkeypatch.setenv("BSH_MEMO_WRITER_MODEL", "opus")
    monkeypatch.setenv("BSH_MEMO_MODEL", "haiku")
    # Writer pin beats the blanket override for writers; the blanket still
    # covers everyone else.
    assert claude_runner._memo_role_model("SPINE", tmp_path) == "opus"
    assert claude_runner._memo_role_model("TRANSLATION", tmp_path) == "haiku"
    # A role's own override beats the pin.
    monkeypatch.setenv("BSH_MEMO_MODEL_SECTION", "sonnet")
    assert claude_runner._memo_role_model("SECTION", tmp_path) == "sonnet"
    assert claude_runner._memo_role_model("SPINE", tmp_path) == "opus"
    # A blank pin is no pin.
    monkeypatch.setenv("BSH_MEMO_WRITER_MODEL", "  ")
    assert claude_runner._memo_role_model("SPINE", tmp_path) == "haiku"
