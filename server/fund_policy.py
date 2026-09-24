"""The fund's return policy: the bar every late-stage verdict answers to.

Stored at ``data/settings/fund_policy.yaml`` (path resolved at call time).
Per stage (early, growth, late) the owner sets a target MOIC and IRR, the
longest hold the target assumes, the largest single position as a share of
the fund, and whether the bar is gross or net of SPV fees and carry.

DEFAULT IS UNSET. Nothing reaches a memo prompt until the owner saves a
policy: ``prompt_block`` returns "" for an unset policy or stage, so prompts
stay byte-identical until then. The thesis and reserves files hold what
look like automatically written placeholders, so they are read here only
as context for the Settings page (fund size, check size) and never enter a
prompt on their own.
"""
from __future__ import annotations

import copy
import math
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

STAGES = ("early", "growth", "late")
BASES = ("gross", "net")

# field -> (label for errors, minimum, maximum)
_NUMERIC_FIELDS: dict[str, tuple[str, float, float]] = {
    "target_moic": ("target MOIC", 1.0, 50.0),
    "target_irr_pct": ("target IRR %", 0.0, 500.0),
    "max_hold_years": ("maximum hold (years)", 0.5, 30.0),
    "max_position_pct": ("maximum position (% of fund)", 0.0, 100.0),
}
STAGE_FIELDS = (*_NUMERIC_FIELDS, "basis")

_STAGE_LABELS = {"early": "Early stage", "growth": "Growth stage", "late": "Late stage"}

_LOCK = threading.RLock()


def _path() -> Path:
    return storage.DATA_DIR / "settings" / "fund_policy.yaml"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _number(field: str, value: Any) -> float | None:
    if value is None or value == "":
        return None
    label, low, high = _NUMERIC_FIELDS[field]
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    try:
        number = float(str(value).strip().rstrip("xX%").strip()) if isinstance(value, str) else float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not math.isfinite(number) or number < low or number > high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}")
    return round(number, 4)


def _clean_stage(stage: str, raw: Any) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"stages.{stage} must be an object")
    unknown = sorted(set(raw) - set(STAGE_FIELDS))
    if unknown:
        raise ValueError(f"stages.{stage} has unknown field(s): {', '.join(unknown)}")
    out: dict[str, Any] = {}
    for field in _NUMERIC_FIELDS:
        value = _number(field, raw.get(field))
        if value is not None:
            out[field] = value
    basis = raw.get("basis")
    if basis not in (None, ""):
        basis = str(basis).strip().lower()
        if basis not in BASES:
            raise ValueError(f"stages.{stage}.basis must be 'gross' or 'net'")
        out["basis"] = basis
    return out or None


def _stage_is_set(entry: Any) -> bool:
    return isinstance(entry, dict) and (
        entry.get("target_moic") is not None or entry.get("target_irr_pct") is not None
    )


def _read_raw() -> dict:
    data = storage._read_yaml_lenient(_path(), {}) or {}
    return data if isinstance(data, dict) else {}


def _context() -> dict:
    """Fund size and check size, read-only, from the files that own them."""
    context: dict[str, Any] = {
        "fund_size_musd": None,
        "check_size_min_musd": None,
        "check_size_max_musd": None,
    }
    try:
        from . import portfolio

        context["fund_size_musd"] = portfolio.get_reserves_settings().get("fund_size_musd")
    except Exception:  # noqa: BLE001 — context only; never block the policy
        pass
    try:
        from . import thesis_store

        thesis = thesis_store.get_thesis()
        context["check_size_min_musd"] = thesis.get("check_size_min_musd")
        context["check_size_max_musd"] = thesis.get("check_size_max_musd")
    except Exception:  # noqa: BLE001
        pass
    return context


def get_policy() -> dict:
    """The stored policy plus read-only fund context.

    ``set`` is True only when at least one stage carries a MOIC or IRR
    target; until then memos get no hurdle at all.
    """
    with _LOCK:
        raw = _read_raw()
    stages_raw = raw.get("stages") if isinstance(raw.get("stages"), dict) else {}
    stages: dict[str, dict | None] = {}
    for stage in STAGES:
        entry = stages_raw.get(stage)
        stages[stage] = copy.deepcopy(entry) if isinstance(entry, dict) and entry else None
    return {
        "set": any(_stage_is_set(entry) for entry in stages.values()),
        "stages": stages,
        "updated_at": raw.get("updated_at"),
        "updated_by": raw.get("updated_by"),
        "context": _context(),
    }


def save_policy(patch: dict, *, updated_by: str | None = None) -> dict:
    """Merge a patch ``{"stages": {"late": {...} | null, ...}}``.

    A stage object replaces that stage entirely; ``null`` clears it. A
    top-level ``{"clear": true}`` removes the whole policy (back to unset).
    """
    if not isinstance(patch, dict):
        raise ValueError("Body must be an object")
    unknown = sorted(set(patch) - {"stages", "clear"})
    if unknown:
        raise ValueError(f"Unknown field(s): {', '.join(unknown)}")
    with _LOCK:
        raw = _read_raw()
        stages = raw.get("stages") if isinstance(raw.get("stages"), dict) else {}
        stages = {k: v for k, v in stages.items() if k in STAGES and isinstance(v, dict)}
        if patch.get("clear"):
            stages = {}
        incoming = patch.get("stages")
        if incoming is not None:
            if not isinstance(incoming, dict):
                raise ValueError("stages must be an object")
            bad = sorted(set(incoming) - set(STAGES))
            if bad:
                raise ValueError(
                    f"Unknown stage(s): {', '.join(bad)}; use {', '.join(STAGES)}"
                )
            for stage, entry in incoming.items():
                cleaned = _clean_stage(stage, entry)
                if cleaned is None:
                    stages.pop(stage, None)
                else:
                    stages[stage] = cleaned
        payload = {
            "version": 1,
            "stages": stages,
            "updated_at": _now(),
            "updated_by": updated_by or None,
        }
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        storage._write_yaml(path, payload)
    return get_policy()


def stage_policy(stage: str | None) -> dict | None:
    """The saved policy for one stage, or None when that stage has no MOIC
    or IRR target (an unset stage never produces a hurdle)."""
    key = str(stage or "").strip().lower()
    if key not in STAGES:
        return None
    entry = get_policy()["stages"].get(key)
    return entry if _stage_is_set(entry) else None


def _fmt_number(value: float) -> str:
    return f"{value:g}"


def hurdle_text(stage: str | None) -> str:
    """One line for a pin or a Settings summary, e.g. "2.0x gross MOIC /
    20% gross IRR over at most 5 years (late stage)". "" when unset."""
    entry = stage_policy(stage)
    if not entry:
        return ""
    basis = entry.get("basis") or "gross"
    parts = []
    if entry.get("target_moic") is not None:
        parts.append(f"{_fmt_number(entry['target_moic'])}x {basis} MOIC")
    if entry.get("target_irr_pct") is not None:
        parts.append(f"{_fmt_number(entry['target_irr_pct'])}% {basis} IRR")
    text = " / ".join(parts)
    if entry.get("max_hold_years") is not None:
        text += f" over at most {_fmt_number(entry['max_hold_years'])} years"
    return f"{text} ({_STAGE_LABELS[str(stage).strip().lower()].lower()})"


def prompt_block(stage: str | None) -> str:
    """The fund-policy block for a memo prompt at ``stage``.

    Returns "" when no policy is saved for that stage, so a prompt that
    appends it is unchanged until the owner sets a hurdle.
    """
    entry = stage_policy(stage)
    if not entry:
        return ""
    key = str(stage).strip().lower()
    basis = entry.get("basis") or "gross"
    lines = [
        "## Fund return policy (set by the firm)",
        "",
        f"- Stage: {_STAGE_LABELS[key]}.",
    ]
    if entry.get("target_moic") is not None:
        lines.append(f"- Target return multiple: {_fmt_number(entry['target_moic'])}x ({basis}).")
    if entry.get("target_irr_pct") is not None:
        lines.append(f"- Target IRR: {_fmt_number(entry['target_irr_pct'])}% ({basis}).")
    if entry.get("max_hold_years") is not None:
        lines.append(f"- Longest hold the target assumes: {_fmt_number(entry['max_hold_years'])} years.")
    if entry.get("max_position_pct") is not None:
        lines.append(
            f"- Largest single position: {_fmt_number(entry['max_position_pct'])}% of the fund."
        )
    # Fund size and check size stay out of the prompt: they come from the
    # reserves/thesis files, which the owner has not confirmed by saving
    # this policy.
    lines.extend([
        "",
        "This is the firm's own bar for this stage. Judge the recommendation "
        "against it and say plainly whether the base case clears it.",
    ])
    return "\n".join(lines)
