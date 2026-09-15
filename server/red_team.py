"""Red-team memo: an adversarial pass over the latest memo, run by Claude on request.

The prompt is built only from what is on record (memo package text, contradicted
evidence rows, reference-call concerns, decision record). The output is stored as-is
with its generation time and the memo it argued against; nothing runs automatically.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import claude_runner, company_paths, comps, decisions_store, ic_room, job_progress, storage

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "counter_thesis": {"type": "string"},
        "kill_risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string"},
                    "why": {"type": "string"},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "evidence_needed": {"type": "string"},
                    "memo_section": {"type": ["string", "null"]},
                },
                "required": ["risk", "why", "severity", "evidence_needed"],
            },
        },
        "questionable_assumptions": {"type": "array", "items": {"type": "string"}},
        "what_would_change_my_mind": {"type": "array", "items": {"type": "string"}},
        "pre_mortem": {"type": "string"},
        "questions_for_founders": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["counter_thesis", "kill_risks", "questionable_assumptions", "what_would_change_my_mind", "pre_mortem", "questions_for_founders"],
}

SYSTEM_PROMPT = (
    "You are the designated dissenter on a venture capital investment committee. Your job is to argue "
    "against the investment as forcefully and specifically as an honest sceptic would, using only the "
    "memo text and records provided plus anything you verify on the web. Quote the memo section you are "
    "attacking. Never invent numbers; if a figure is missing say what evidence would settle it."
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _company_dir(company_id: str) -> Path:
    return company_paths.company_dir(company_id)


def result_path(company_id: str) -> Path:
    return _company_dir(company_id) / "red_team.json"


def progress_path(company_id: str) -> Path:
    return _company_dir(company_id) / "red_team.progress.jsonl"


def build_prompt(company_id: str, *, max_memo_chars: int = 24000) -> tuple[str, dict]:
    """User prompt + a provenance dict describing exactly what went in."""
    company = storage.get_company(company_id) or {"id": company_id, "name": company_id}
    path, package = comps._latest_memo_package(company_id)
    blocks = comps._memo_text_blocks(package) if package else []
    memo_lines: list[str] = []
    used = 0
    for title, text in blocks:
        line = f"[{title}] {text}"
        if used + len(line) > max_memo_chars:
            break
        memo_lines.append(line)
        used += len(line)
    refs = ic_room.list_reference_calls(company_id)
    concerns = [f"{item['contact']} ({item['relation']}): {c}" for item in refs["items"] for c in item.get("concerns") or []]
    decision_md = decisions_store.render_decision_record_md(company_id, max_chars=1500) or ""
    contradictions: list[str] = []
    try:
        from . import copilot

        contradictions = [row["claim"] for row in copilot._evidence_contradictions(company_id, limit=8)]
    except Exception:  # noqa: BLE001
        contradictions = []

    parts = [
        f"Company: {company.get('name') or company_id}",
        f"Description on record: {storage and (company.get('description') or '—')}",
        "",
        "=== MEMO (latest package, English blocks, section in brackets) ===",
        "\n".join(memo_lines) if memo_lines else "(no memo package on record — argue from the description and public sources only, and say so)",
        "",
        "=== EVIDENCE ROWS THE MATRIX MARKS CONTRADICTED ===",
        "\n".join(f"- {c}" for c in contradictions) if contradictions else "(none)",
        "",
        "=== REFERENCE-CALL CONCERNS ===",
        "\n".join(f"- {c}" for c in concerns) if concerns else "(no reference calls recorded)",
        "",
        "=== DECISION RECORD ===",
        decision_md or "(no decision yet)",
        "",
        "Write the strongest case against investing. Every kill risk must name the memo section it attacks "
        "(memo_section) or null when it comes from outside the memo.",
    ]
    provenance = {
        "memo_package": str(path) if path else None,
        "memo_blocks_used": len(memo_lines),
        "memo_chars_used": used,
        "contradicted_rows": len(contradictions),
        "reference_concerns": len(concerns),
        "has_decision_record": bool(decision_md),
    }
    return "\n".join(parts), provenance


def load_result(company_id: str) -> dict:
    path = result_path(company_id)
    state = job_progress.scan_progress_state(progress_path(company_id))
    running = bool(state.get("exists") and not state.get("terminated"))
    if not path.exists():
        return {"company_id": company_id, "status": "running" if running else "none", "result": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"company_id": company_id, "status": "running" if running else "none", "result": None}
    data["status"] = "running" if running else data.get("status", "done")
    return data


def _runner(system_prompt: str, user_prompt: str, progress) -> tuple[dict | None, str | None]:
    return claude_runner.run_web_research_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=SCHEMA,
        name="red_team",
        timeout_sec=900,
        silence_timeout_sec=180,
        progress=progress,
    )


def _write_result(company_id: str, payload: dict) -> None:
    result_path(company_id).parent.mkdir(parents=True, exist_ok=True)
    result_path(company_id).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run(company_id: str, *, requested_by: str | None = None, runner=None) -> dict:
    """Synchronous run (the API wraps it in a thread). `runner` is injectable for tests.

    The stored result is replaced with a running payload first, so a rerun
    never reports the previous run's error or result while it is working.
    """
    runner = runner or _runner
    progress = job_progress.ProgressLog(progress_path(company_id))
    progress.emit("job_init", job="red_team", company_id=company_id)
    _write_result(company_id, {
        "company_id": company_id,
        "generated_at": None,
        "started_at": _now(),
        "requested_by": requested_by or "",
        "provenance": None,
        "status": "running",
        "error": None,
        "result": None,
    })
    provenance = None
    try:
        progress.emit("stage", stage="prompt", message="Assembling memo, contradicted evidence and reference concerns")
        user_prompt, provenance = build_prompt(company_id)
        progress.emit("stage", stage="claude", message="Claude is arguing the other side")
        result, error = runner(SYSTEM_PROMPT, user_prompt, progress)
    except Exception as exc:  # noqa: BLE001
        result, error = None, f"Red team failed: {type(exc).__name__}: {exc}"
    payload = {
        "company_id": company_id,
        "generated_at": _now(),
        "requested_by": requested_by or "",
        "provenance": provenance,
        "status": "done" if result else "error",
        "error": error,
        "result": result,
    }
    _write_result(company_id, payload)
    if result:
        progress.emit("done", message="Red-team memo ready")
    else:
        progress.emit("error", message=error or "Red team failed")
    return payload


def start(company_id: str, *, requested_by: str | None = None) -> dict:
    state = job_progress.scan_progress_state(progress_path(company_id))
    if state.get("exists") and not state.get("terminated"):
        return {"company_id": company_id, "status": "already_running"}
    threading.Thread(target=run, args=(company_id,), kwargs={"requested_by": requested_by}, name=f"red_team:{company_id}", daemon=True).start()
    return {"company_id": company_id, "status": "queued"}
