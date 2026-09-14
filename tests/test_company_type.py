"""Company type (Phase 1 -> 2 -> 3): registry `vertical` wins, a tool-free
classifier is the fallback, the type file steers Phase 2 research focus,
the Phase 3 lens and an optional scorecard weight overlay, and the API
exposes the type (and the previously dropped company stage) to the UI."""

from __future__ import annotations

import pytest

from server import (
    api,
    claude_runner,
    memo_analysis,
    memo_prep,
    memo_structure,
    storage,
)
from server.company_verticals_seed import COMPANY_VERTICALS


@pytest.fixture(autouse=True)
def _v2_on(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    memo_structure.load_structure.cache_clear()
    memo_structure.load_company_type.cache_clear()
    yield
    memo_structure.load_structure.cache_clear()
    memo_structure.load_company_type.cache_clear()


# ---- type profiles ----------------------------------------------------------


@pytest.mark.parametrize("key", memo_structure.COMPANY_TYPE_KEYS)
def test_every_type_has_a_profile(key):
    profile = memo_structure.load_company_type(key)
    assert profile is not None and profile.type == key
    assert profile.label["en"] and profile.label["zh"]
    assert profile.body.startswith("## ")
    assert profile.research_focus.get("all")
    for family, weights in profile.scorecard.items():
        assert family in {"early", "growth", "late"}
        assert set(weights) == set(memo_structure.SCORECARD_DIMENSION_KEYS)
        assert sum(weights.values()) == 100


def test_unknown_or_missing_type_loads_nothing():
    assert memo_structure.load_company_type(None) is None
    assert memo_structure.load_company_type("pets") is None


def test_seed_map_uses_only_known_types():
    assert set(COMPANY_VERTICALS.values()) <= set(memo_structure.COMPANY_TYPE_KEYS)
    assert COMPANY_VERTICALS["anthropic-pbc"] == "ai_foundation_model"
    assert COMPANY_VERTICALS["figure-ai-inc"] == "robotics"


# ---- structure overlay -----------------------------------------------------


def test_overlay_replaces_weights_and_stamps_meta():
    base = memo_structure.load_structure("late", 2)
    typed = memo_structure.load_structure("late", 2, "robotics")
    overlay = memo_structure.load_company_type("robotics").scorecard["late"]
    assert typed.scorecard == overlay
    assert typed.scorecard != base.scorecard
    assert typed.meta() == {"stage": "late", "version": 2, "company_type": "robotics"}
    assert base.meta() == {"stage": "late", "version": 2}
    assert typed.section_ids == base.section_ids
    assert typed.profile_digest() != base.profile_digest()
    # Round trip through the package stamp resolves the same weights.
    package = {"structure": typed.meta()}
    assert memo_structure.for_package(package).scorecard == overlay


def test_compact_profile_uses_the_parent_stage_overlay():
    typed = memo_structure.load_structure("late_compact", 1, "ai_video_short_drama")
    overlay = memo_structure.load_company_type("ai_video_short_drama").scorecard[
        "late"
    ]
    assert typed.pin_stage == "late"
    assert typed.scorecard == overlay


def test_type_without_overlay_keeps_stage_weights():
    base = memo_structure.load_structure("late", 2)
    typed = memo_structure.load_structure("late", 2, "ai_infra")
    assert typed.scorecard == base.scorecard
    assert typed.company_type == "ai_infra"
    # v1 (no scorecard) never gains one from a type file.
    v1 = memo_structure.load_structure("late", 1, "robotics")
    assert v1.scorecard == {}


def test_active_structure_threads_the_type(monkeypatch):
    typed = memo_structure.active_structure("late", "full", "ai_foundation_model")
    assert typed.company_type == "ai_foundation_model"
    assert typed.scorecard["moat"] == 17
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "0")
    assert memo_structure.active_structure("late", "full", "robotics") is (
        memo_structure.LATE
    )


# ---- Phase 2 / Phase 3 injection --------------------------------------------


def test_research_focus_combines_all_and_pass_text():
    typed = memo_structure.load_structure("late", 2, "robotics")
    focus = memo_structure.company_type_research_focus(typed, "deployment_behavior")
    assert "announced partner -> pilot" in focus
    assert "Deployment reality" in focus  # the `all` block rides every pass
    generic = memo_structure.company_type_research_focus(typed, "time_base")
    assert "Deployment reality" in generic and "announced partner" not in generic
    untyped = memo_structure.load_structure("late", 2)
    assert memo_structure.company_type_research_focus(untyped, "market_sizing") == ""


def test_pass_prompt_carries_the_type_focus(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_run(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return None, "stub"

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_run)
    common = dict(
        run_dir=tmp_path,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        pass_id="market_sizing",
        pass_label="Market sizing / TAM",
        artifact_filename="market_sizing.md",
        focus="Size the market.",
        settings_path=tmp_path / "settings.md",
        companies_yaml_path=tmp_path / "companies.yaml",
    )
    claude_runner.run_memo_fast_analysis_pass(
        **common, type_focus="Show three market lenses.", type_label="AI foundation model"
    )
    assert (
        "Company-type research focus (AI foundation model):\nShow three market lenses."
        in captured["prompt"]
    )
    claude_runner.run_memo_fast_analysis_pass(**common)
    assert "Company-type research focus" not in captured["prompt"]


def _common_context(structure):
    return claude_runner._memo_english_common_context(
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        run_dir=memo_structure.TYPES_DIR.parent,
        companies_yaml_path=memo_structure.TYPES_DIR / "missing.yaml",
        memo_paths={},
        research_dir=None,
        analysis_session_path=None,
        scope_check=None,
        warnings=None,
        structure=structure,
    )


def test_common_context_appends_the_lens_for_v2_only():
    untyped = _common_context(memo_structure.load_structure("late", 2))
    typed = _common_context(memo_structure.load_structure("late", 2, "ai_infra"))
    assert "## Company type lens — AI infrastructure" in typed
    assert "## Company type lens" not in untyped
    assert typed.startswith(untyped)
    v1_typed = _common_context(memo_structure.load_structure("late", 1, "ai_infra"))
    v1 = _common_context(memo_structure.LATE)
    assert v1_typed == v1


def test_spine_prompt_names_the_type(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_run(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return None, "stub"

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_run)
    claude_runner.run_memo_fast_english_spine(
        run_dir=tmp_path,
        company_name="Acme",
        common_context="",
        add_dirs=[],
        progress=None,
        structure=memo_structure.load_structure("late", 2, "robotics"),
    )
    assert "This run's company type is Robotics" in captured["prompt"]


# ---- Phase 1 classification ---------------------------------------------------


def test_registry_vertical_wins():
    assert memo_prep.classify_company_type({"vertical": "ai_infra"}) == {
        "type": "ai_infra",
        "source": "registry",
    }
    assert memo_prep.classify_company_type({"vertical": "pets"}) is None
    assert memo_prep.classify_company_type({}) is None


def test_classifier_call_is_tool_free_sonnet(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"type": "robotics", "confidence": 0.9, "rationale": "humanoids"}, None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_run)
    info = claude_runner.run_memo_company_type_classifier(
        run_dir=tmp_path, company={"name": "Figure", "industry": "Humanoid robotics"}
    )
    assert info == {
        "type": "robotics",
        "source": "classifier",
        "confidence": 0.9,
        "rationale": "humanoids",
    }
    assert captured["tools"] == "" and captured["allowed_tools"] == ""
    assert captured["model"] == "sonnet"
    assert "Humanoid robotics" in captured["prompt"]

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", lambda **k: (None, "boom")
    )
    assert (
        claude_runner.run_memo_company_type_classifier(run_dir=tmp_path, company={})
        is None
    )


class _Stream:
    def __init__(self):
        self.events: list[dict] = []

    def emit(self, event_type, **payload):
        self.events.append({"type": event_type, **payload})


def test_resolve_company_type_prefers_registry_then_classifier(tmp_path, monkeypatch):
    stream = _Stream()
    calls: list = []
    monkeypatch.setattr(
        claude_runner,
        "run_memo_company_type_classifier",
        lambda **k: calls.append(k) or None,
    )
    updates: list = []
    monkeypatch.setattr(
        storage, "update_report", lambda rid, **patch: updates.append((rid, patch))
    )
    monkeypatch.setattr(storage, "get_company", lambda cid: {"id": cid})
    registry = {"company_type": {"type": "ai_infra", "source": "registry"}}
    assert memo_analysis._resolve_company_type("r1", registry, tmp_path, stream) == (
        registry["company_type"]
    )
    assert calls == [] and updates == []
    # No registry value and a failing classifier -> other, published once.
    info = memo_analysis._resolve_company_type(
        "r1", {"company_id": "acme"}, tmp_path, stream
    )
    assert info == {"type": "other", "source": "classifier_failed"}
    assert len(calls) == 1
    assert updates == [("r1", {"company_type": info})]
    assert stream.events[-1]["stage"] == "company_type"
    assert stream.events[-1]["company_type"] == "other"


def test_backfill_verticals_fills_seeded_records_only(tmp_path, monkeypatch):
    companies_file = tmp_path / "companies.yaml"
    monkeypatch.setattr(storage, "COMPANIES_FILE", companies_file)
    storage._write_yaml(
        companies_file,
        [
            {"id": "anthropic-pbc", "name": "Anthropic"},
            {"id": "figure-ai-inc", "name": "Figure", "vertical": "ai_application"},
            {"id": "msft", "name": "Microsoft"},
        ],
    )
    storage._backfill_verticals()
    records = {c["id"]: c for c in storage._read_yaml(companies_file, [])}
    assert records["anthropic-pbc"]["vertical"] == "ai_foundation_model"
    assert records["figure-ai-inc"]["vertical"] == "ai_application"  # yaml wins
    assert "vertical" not in records["msft"]


# ---- API surface -------------------------------------------------------------


def test_report_detail_exposes_type_and_stage(monkeypatch):
    monkeypatch.setattr(api.memo_prep, "is_memo_kind", lambda kind: False)
    detail = api._report_detail(
        {
            "id": "r1",
            "company_type": {"type": "robotics", "source": "registry"},
            "company_stage": {"stage": "growth", "source": "memo_spine"},
        }
    )
    assert detail["company_type"] == {"type": "robotics", "source": "registry"}
    assert detail["company_stage"] == {"stage": "growth", "source": "memo_spine"}
    model = api.ReportDetail(
        id="r1",
        report_type="memo",
        status="complete",
        created_at="2026-09-13T00:00:00Z",
        updated_at="2026-09-13T00:00:00Z",
        company_type=detail["company_type"],
        company_stage=detail["company_stage"],
    )
    assert model.company_type["type"] == "robotics"
    assert model.company_stage["stage"] == "growth"


def test_company_view_exposes_vertical():
    view = api._company_view({"id": "figure-ai-inc", "name": "Figure", "vertical": "robotics"})
    assert view["vertical"] == "robotics"
    assert api._company_view({"id": "x", "name": "X", "vertical": "pets"})["vertical"] is None
