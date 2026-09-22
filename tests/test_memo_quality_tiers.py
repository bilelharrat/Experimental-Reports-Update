"""Per-run quality tiers: the user-facing Quality toggle routes memo
subprocess roles to cheaper models.

- The tier table stays well-formed: known levels, known roles, and the
  writing wave (SPINE/SECTION/ARTIFACTS/REPAIR) uniform per tier so the
  shared prompt cache survives.
- Env overrides (BSH_MEMO_MODEL[_ROLE] / BSH_MEMO_EFFORT[_ROLE]) always
  win over the registered tier.
- Every tier pins effort explicitly, so a run's cost never depends on
  the operator's ~/.claude/settings.json.
- An unregistered run (no run context) still applies nothing.
- bootstrap validates and stamps the level; the API rejects unknowns.
"""
from __future__ import annotations

import pytest

from server import claude_runner

_ROLES = (
    "ANALYSIS_PASS",
    "ENGLISH",
    "SPINE",
    "SECTION",
    "ARTIFACTS",
    "SPINE_CHECK",
    "TRANSLATION",
    "REPAIR",
)
_EFFORTS = (None, "low", "medium", "high", "xhigh", "max")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for role in _ROLES:
        monkeypatch.delenv(f"BSH_MEMO_MODEL_{role}", raising=False)
        monkeypatch.delenv(f"BSH_MEMO_EFFORT_{role}", raising=False)
    monkeypatch.delenv("BSH_MEMO_MODEL", raising=False)
    monkeypatch.delenv("BSH_MEMO_EFFORT", raising=False)


# ---- tier table -------------------------------------------------------------


def test_tier_table_shape():
    assert claude_runner.MEMO_QUALITY_LEVELS == ("best", "balanced", "economy")
    tiers = claude_runner._MEMO_QUALITY_TIERS
    assert set(tiers) == set(claude_runner.MEMO_QUALITY_LEVELS)
    for level in claude_runner.MEMO_QUALITY_LEVELS:
        assert set(tiers[level]) == set(_ROLES), level
    for level, mapping in tiers.items():
        for role, (model, effort) in mapping.items():
            assert role in _ROLES, (level, role)
            assert model is None or (isinstance(model, str) and model)
            assert effort in _EFFORTS, (level, role, effort)


def test_writing_wave_uniform_per_tier():
    """Prompt caches are (model, effort)-scoped. Any tier that touches
    the writing wave must give SPINE/SECTION/ARTIFACTS/REPAIR one shared
    pair, or the section wave forfeits its shared-context cache."""
    wave = ("SPINE", "SECTION", "ARTIFACTS", "REPAIR")
    for level, mapping in claude_runner._MEMO_QUALITY_TIERS.items():
        pairs = {mapping.get(role, (None, None)) for role in wave}
        assert len(pairs) == 1, (level, pairs)


# ---- resolution and precedence ----------------------------------------------


def test_no_run_context_applies_nothing():
    """Callers outside a memo run keep the CLI defaults."""
    assert claude_runner._memo_role_model("SECTION", None) is None
    assert claude_runner._memo_role_effort("SECTION", None) is None


def test_an_unregistered_run_falls_back_to_best(tmp_path):
    assert claude_runner._memo_role_model("SECTION", tmp_path) is None
    assert claude_runner._memo_role_effort("SECTION", tmp_path) == "high"


def test_best_keeps_the_top_model_for_everything_the_founder_reads(tmp_path):
    """The founder reads the English prose, so the writing wave stays on
    the default model at high effort. The spine checker — a mechanical
    gate — and translation, which renders prose already decided, run on
    Sonnet."""
    claude_runner.register_memo_run_quality(tmp_path, "best")
    for role in ("SPINE", "SECTION", "ARTIFACTS", "REPAIR", "ENGLISH"):
        assert claude_runner._memo_role_model(role, tmp_path) is None
        assert claude_runner._memo_role_effort(role, tmp_path) == "high"
    assert claude_runner._memo_role_model("SPINE_CHECK", tmp_path) == "sonnet"
    # Translation is transformation, not authorship: Sonnet on every tier,
    # which the owner's server had pinned by env (2026-09-22).
    assert claude_runner._memo_role_model("TRANSLATION", tmp_path) == "sonnet"
    assert claude_runner._memo_role_effort("TRANSLATION", tmp_path) == "medium"


def test_best_spends_less_thinking_on_the_analysis_passes(tmp_path):
    """The passes extract and classify evidence from a fixed corpus. On the
    2026-09-14 run 64% of their output tokens were thinking and they filled
    every schema cap anyway, so the top model at medium effort is the deal."""
    claude_runner.register_memo_run_quality(tmp_path, "best")
    assert claude_runner._memo_role_model("ANALYSIS_PASS", tmp_path) is None
    assert claude_runner._memo_role_effort("ANALYSIS_PASS", tmp_path) == "medium"


def test_every_tier_pins_its_effort(tmp_path):
    """An unpinned role inherits ~/.claude/settings.json, which made a
    personal UI preference decide what a server-side run costs."""
    for level in claude_runner.MEMO_QUALITY_LEVELS:
        for role, (_model, effort) in claude_runner._MEMO_QUALITY_TIERS[
            level
        ].items():
            assert effort is not None, (level, role)


def test_economy_routes_every_role(tmp_path):
    claude_runner.register_memo_run_quality(tmp_path, "economy")
    for role in _ROLES:
        assert claude_runner._memo_role_model(role, tmp_path) == "sonnet"
    assert claude_runner._memo_role_effort("TRANSLATION", tmp_path) == "medium"
    assert claude_runner._memo_role_effort("SECTION", tmp_path) == "medium"
    assert claude_runner._memo_role_effort("ANALYSIS_PASS", tmp_path) == "low"


def test_balanced_keeps_the_writing_wave_on_the_default_model_at_medium(tmp_path):
    """The writing wave stays on the CLI default model (no --model flag)
    but runs at medium effort; research goes to Sonnet at default effort."""
    claude_runner.register_memo_run_quality(tmp_path, "balanced")
    for role in ("SPINE", "SECTION", "ARTIFACTS", "REPAIR", "ENGLISH"):
        assert claude_runner._memo_role_model(role, tmp_path) is None
        assert claude_runner._memo_role_effort(role, tmp_path) == "medium"
    assert claude_runner._memo_role_model("ANALYSIS_PASS", tmp_path) == "sonnet"
    assert claude_runner._memo_role_effort("ANALYSIS_PASS", tmp_path) == "medium"
    assert claude_runner._memo_role_model("TRANSLATION", tmp_path) == "sonnet"
    assert claude_runner._memo_role_model("SPINE_CHECK", tmp_path) == "sonnet"


def test_env_override_beats_tier(monkeypatch, tmp_path):
    claude_runner.register_memo_run_quality(tmp_path, "economy")
    monkeypatch.setenv("BSH_MEMO_MODEL_SECTION", "opus")
    monkeypatch.setenv("BSH_MEMO_MODEL", "haiku")
    monkeypatch.setenv("BSH_MEMO_EFFORT_TRANSLATION", "high")
    # Role-specific env wins for its role; the blanket env wins for the
    # rest; the tier never overrides either.
    assert claude_runner._memo_role_model("SECTION", tmp_path) == "opus"
    assert claude_runner._memo_role_model("SPINE", tmp_path) == "haiku"
    assert claude_runner._memo_role_effort("TRANSLATION", tmp_path) == "high"


def test_runs_are_isolated(tmp_path):
    run_a = tmp_path / "a"
    run_b = tmp_path / "b"
    claude_runner.register_memo_run_quality(run_a, "economy")
    claude_runner.register_memo_run_quality(run_b, "best")
    assert claude_runner._memo_role_model("SECTION", run_a) == "sonnet"
    assert claude_runner._memo_role_model("SECTION", run_b) is None
    assert claude_runner._memo_role_effort("SECTION", run_b) == "high"


def test_unknown_tier_registers_as_best(tmp_path):
    claude_runner.register_memo_run_quality(tmp_path, "turbo")
    best = claude_runner._MEMO_QUALITY_TIERS["best"]
    for role in _ROLES:
        assert claude_runner._memo_role_model(role, tmp_path) == best[role][0]
        assert claude_runner._memo_role_effort(role, tmp_path) == best[role][1]


# ---- run plumbing -----------------------------------------------------------


def test_bootstrap_rejects_unknown_quality():
    from server import memo_prep

    with pytest.raises(ValueError, match="quality"):
        memo_prep.bootstrap_memo_run("whatever", quality="turbo")
