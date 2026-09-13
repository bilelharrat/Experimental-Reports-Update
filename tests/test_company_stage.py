"""Company-stage publishing: the evidence-confirmed stage a run's spine
pins after Phase 2 replaces the old prep-time scope warning in the UI.

- The spine hook publishes report.company_stage once, from the pinned
  ``shared_facts.stage``, and emits a ``company_stage`` stream event.
- Spines without a stage pin (late v1 / studio-composed) publish nothing.
- The prep stage assessment no longer lands in user-facing warnings.
"""
from __future__ import annotations

from server import memo_analysis


class _FakeStream:
    def __init__(self):
        self.events = []

    def emit(self, *args, **kwargs):
        self.events.append((args, kwargs))


def test_hook_publishes_once(monkeypatch):
    updates = []
    monkeypatch.setattr(
        memo_analysis.storage,
        "update_report",
        lambda report_id, **kw: updates.append((report_id, kw)),
    )
    stream = _FakeStream()
    hook = memo_analysis._company_stage_spine_hook("r1", stream)

    payload = {"shared_facts": {"stage": "Late"}}
    hook(payload)
    hook(payload)  # a respun spine re-fires the hook; publish only once

    assert updates == [
        ("r1", {"company_stage": {"stage": "late", "source": "memo_spine"}})
    ]
    stage_events = [
        kw for args, kw in stream.events if kw.get("stage") == "company_stage"
    ]
    assert len(stage_events) == 1
    assert stage_events[0]["classification"] == "late"


def test_hook_ignores_spines_without_a_stage_pin(monkeypatch):
    updates = []
    monkeypatch.setattr(
        memo_analysis.storage,
        "update_report",
        lambda report_id, **kw: updates.append((report_id, kw)),
    )
    stream = _FakeStream()
    hook = memo_analysis._company_stage_spine_hook("r1", stream)

    hook(None)
    hook({})
    hook({"shared_facts": {}})
    hook({"shared_facts": {"stage": "pre-ipo"}})  # not a pinned enum value

    assert updates == []
    assert stream.events == []
    # A later valid payload still publishes — the misses did not burn
    # the once-only latch.
    hook({"shared_facts": {"stage": "growth"}})
    assert updates[0][1]["company_stage"]["stage"] == "growth"


def test_compose_spine_hooks():
    assert memo_analysis._compose_spine_hooks(None, None) is None

    calls = []
    one = lambda p: calls.append(("one", p))  # noqa: E731
    two = lambda p: calls.append(("two", p))  # noqa: E731
    assert memo_analysis._compose_spine_hooks(one, None) is one

    composed = memo_analysis._compose_spine_hooks(one, two)
    composed("payload")
    assert calls == [("one", "payload"), ("two", "payload")]


def test_stage_assessment_warn_is_not_a_user_warning():
    """The prep-time stage classification is agent calibration, not a
    user-facing warning — the bootstrap warnings block must not append
    it. Canary on the source so a revert is caught without needing the
    full bootstrap fixture stack."""
    import inspect

    from server import memo_prep

    source = inspect.getsource(memo_prep.bootstrap_memo_run)
    assert 'warnings.append(stage_assessment' not in source
    assert "warnings: list[str] = []" in source
