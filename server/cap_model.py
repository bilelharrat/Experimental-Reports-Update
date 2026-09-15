"""Round & dilution model — pure arithmetic over user-entered inputs.

Inputs are stored per company at ``data/companies/<id>/cap_model.json``.
Nothing is estimated: every output is a function of the numbers typed in.
"""
from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()


class CapModelUnreadable(RuntimeError):
    """The stored cap model cannot be parsed; refuse to overwrite it."""


_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "pre_money_musd": (0.0, None),
    "new_money_musd": (0.0, None),
    "our_check_musd": (0.0, None),
    "option_pool_pct_post": (0.0, 100.0),
    "liquidation_preference_x": (0.0, None),
}

DEFAULT_INPUTS: dict[str, Any] = {
    "pre_money_musd": None,
    "new_money_musd": None,
    "our_check_musd": None,
    "option_pool_pct_post": None,      # target pool as % of post-money
    "liquidation_preference_x": 1.0,   # 1.0 = non-participating 1x
    "participating": False,
    "exit_values_musd": [250, 500, 1000, 3000],
    "notes": "",
}


def _path(company_id: str) -> Path:
    return storage.DATA_DIR / "companies" / company_id / "cap_model.json"


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "" or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _input(key: str, value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{key} must be a finite number")
    lo, hi = _BOUNDS[key]
    if lo is not None and number < lo:
        raise ValueError(f"{key} must be at least {lo:g}")
    if hi is not None and number > hi:
        raise ValueError(f"{key} must be at most {hi:g}")
    return number


def _read_saved(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    saved = json.loads(raw)
    if not isinstance(saved, dict):
        raise ValueError("cap model file is not an object")
    return saved


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_inputs(company_id: str) -> dict:
    inputs = dict(DEFAULT_INPUTS)
    path = _path(company_id)
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                inputs.update({k: v for k, v in saved.items() if k in DEFAULT_INPUTS or k == "updated_at"})
        except Exception as exc:  # noqa: BLE001
            logger.warning("cap model for %s unreadable: %s", company_id, exc)
    return inputs


def save_inputs(company_id: str, patch: dict) -> dict:
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")
    clean: dict[str, Any] = {}
    for key in _BOUNDS:
        if key in patch:
            clean[key] = _input(key, patch.get(key))
    if "participating" in patch:
        clean["participating"] = bool(patch.get("participating"))
    if "exit_values_musd" in patch:
        raw_values = patch.get("exit_values_musd") or []
        if not isinstance(raw_values, (list, tuple)):
            raise ValueError("exit_values_musd must be a list of numbers")
        values = [v for v in (_float(x) for x in raw_values) if v is not None and v > 0]
        clean["exit_values_musd"] = sorted(values)[:8] or DEFAULT_INPUTS["exit_values_musd"]
    if "notes" in patch:
        clean["notes"] = str(patch.get("notes") or "")[:2000]
    path = _path(company_id)
    with _LOCK:
        try:
            saved = _read_saved(path)
        except (OSError, ValueError) as exc:
            raise CapModelUnreadable(f"cap model file for {company_id} is unreadable: {exc}") from exc
        inputs = dict(DEFAULT_INPUTS)
        if saved:
            inputs.update({k: v for k, v in saved.items() if k in DEFAULT_INPUTS or k == "updated_at"})
        inputs.update(clean)
        inputs["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_atomic(path, inputs)
    return inputs


def compute(inputs: dict) -> dict:
    """Post-money, ownership and a simple preferred-stock waterfall for our check."""
    pre = _float(inputs.get("pre_money_musd"))
    new_money = _float(inputs.get("new_money_musd"))
    check = _float(inputs.get("our_check_musd"))
    pool_pct = _float(inputs.get("option_pool_pct_post")) or 0.0
    raw_pref = _float(inputs.get("liquidation_preference_x"))
    pref_x = 1.0 if raw_pref is None else max(0.0, raw_pref)
    participating = bool(inputs.get("participating"))

    if pre is None or new_money is None or pre <= 0 or new_money < 0:
        return {"ready": False, "reason": "Enter pre-money and new money to compute the round."}

    post = pre + new_money
    round_ownership_pct = 100 * new_money / post
    our_ownership_pct = 100 * check / post if check else None
    # Option pool created pre-money dilutes existing holders (standard "pool shuffle").
    existing_ownership_pct = 100 * pre / post - pool_pct
    existing_ownership_pct = max(0.0, existing_ownership_pct)

    waterfall = []
    for exit_musd in inputs.get("exit_values_musd") or []:
        exit_v = _float(exit_musd)
        if exit_v is None:
            continue
        if check:
            pref = min(exit_v, check * pref_x)
            as_converted = exit_v * (check / post)
            if participating:
                proceeds = min(exit_v, pref + max(0.0, exit_v - new_money * pref_x) * (check / post))
            else:
                proceeds = max(pref, as_converted)
            waterfall.append({
                "exit_musd": exit_v,
                "our_proceeds_musd": round(proceeds, 2),
                "multiple_on_check": round(proceeds / check, 2) if check else None,
                "converted": proceeds == as_converted and not participating,
            })
        else:
            waterfall.append({"exit_musd": exit_v, "our_proceeds_musd": None, "multiple_on_check": None, "converted": None})

    return {
        "ready": True,
        "post_money_musd": round(post, 2),
        "round_ownership_pct": round(round_ownership_pct, 2),
        "our_ownership_pct": round(our_ownership_pct, 2) if our_ownership_pct is not None else None,
        "existing_ownership_pct_after": round(existing_ownership_pct, 2),
        "option_pool_pct_post": pool_pct,
        "liquidation_preference_x": pref_x,
        "participating": participating,
        "waterfall": waterfall,
    }


def get_model(company_id: str) -> dict:
    inputs = load_inputs(company_id)
    return {"company_id": company_id, "inputs": inputs, "result": compute(inputs)}


def update_model(company_id: str, patch: dict) -> dict:
    inputs = save_inputs(company_id, patch)
    return {"company_id": company_id, "inputs": inputs, "result": compute(inputs)}
