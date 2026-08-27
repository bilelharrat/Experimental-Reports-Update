"""Summarize a memo run's phase timings and cost from its stream log.

Usage:
    python scripts/memo_phase_report.py <run_dir>

Reads <run_dir>/logs/stream.jsonl (the run's append-only progress log),
prints a markdown table of every terminal `phase_timing` row (finished /
failed / skipped) with wall-clock minutes and cost, then derived totals:
English attempts used, chase efficiency when present, and the quality
verdicts from logs/memo_quality_lint.md and logs/memo_chinese_parity.md.

Stdlib only; used by the benchmark protocol in docs/memo-benchmarks.md.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TERMINAL = {"finished", "failed", "skipped"}


def _load_phase_rows(stream_path: Path) -> list[dict]:
    rows: list[dict] = []
    with stream_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "phase_timing":
                continue
            if entry.get("status") in TERMINAL:
                rows.append(entry)
    return rows


def _fmt_minutes(duration_ms) -> str:
    try:
        return f"{int(duration_ms) / 60000:.1f}"
    except (TypeError, ValueError):
        return ""


def _fmt_cost(cost) -> str:
    try:
        return f"${float(cost):.2f}"
    except (TypeError, ValueError):
        return ""


def _grep_quality(run_dir: Path) -> list[str]:
    lines: list[str] = []
    lint_path = run_dir / "logs" / "memo_quality_lint.md"
    if lint_path.exists():
        text = lint_path.read_text(encoding="utf-8", errors="replace")
        for key in ("status", "p0_count", "p1_count"):
            match = re.search(rf"^- {key}:\s*(.+)$", text, re.MULTILINE)
            if match:
                lines.append(f"- quality lint {key}: {match.group(1).strip()}")
    parity_path = run_dir / "logs" / "memo_chinese_parity.md"
    if parity_path.exists():
        text = parity_path.read_text(encoding="utf-8", errors="replace")
        blocking = len(re.findall(r"^- \[P0\]", text, re.MULTILINE))
        advisory = len(re.findall(r"^- \[P1\]", text, re.MULTILINE))
        lines.append(f"- chinese parity findings: P0={blocking} P1={advisory}")
    return lines


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 2
    run_dir = Path(sys.argv[1]).expanduser()
    stream_path = run_dir / "logs" / "stream.jsonl"
    if not stream_path.exists():
        print(f"no stream log at {stream_path}")
        return 1

    rows = _load_phase_rows(stream_path)
    print(f"# Phase report — {run_dir.name}\n")
    print("| phase | status | attempt | minutes | cost |")
    print("|---|---|---|---|---|")
    for row in rows:
        print(
            "| {phase} | {status} | {attempt} | {minutes} | {cost} |".format(
                phase=row.get("phase", ""),
                status=row.get("status", ""),
                attempt=row.get("attempt", ""),
                minutes=_fmt_minutes(row.get("duration_ms")),
                cost=_fmt_cost(row.get("cost_usd")),
            )
        )

    attempts = [
        row for row in rows if row.get("phase") == "memo_fast_english_package_attempt"
    ]
    total = next(
        (row for row in rows if row.get("phase") == "memo_background_run"), None
    )
    print("\n## Derived")
    if attempts:
        print(f"- english synthesis attempts: {len(attempts)}")
    chase = next((row for row in rows if row.get("phase") == "memo_zh_chase"), None)
    if chase is not None:
        adopted = chase.get("strings_adopted")
        chased = chase.get("units_chased")
        missed = chase.get("units_missed")
        print(
            f"- chase efficiency: units_chased={chased} units_missed={missed} "
            f"strings_adopted={adopted} cost={_fmt_cost(chase.get('cost_usd'))}"
        )
    if total is not None:
        print(
            f"- run total: {_fmt_minutes(total.get('duration_ms'))} min, "
            f"{_fmt_cost(total.get('cost_usd'))}"
        )
    for line in _grep_quality(run_dir):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
