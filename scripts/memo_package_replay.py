"""Replay the English-package gate over every stored memo package.

Usage:
    uv run python scripts/memo_package_replay.py [--data-dir DIR] [--triage]
        [--first-only] [--json] [--quiet]

Finds every ``memos/<company>/<run>/logs/memo_package.en.attempt-*.json``
and ``.../logs/memo_package.json`` under the data dir (default: this
checkout's ``data/``) and runs, per package, exactly what a run applies
before it accepts an English package — no model calls:

1. ``memo_docx_renderer.repair_package_structure`` (the deterministic
   repairs),
2. ``memo_fact_check.attach_source_urls(..., write_report=False)`` (URLs
   from the run's own analysis artifacts, the company's source cache and
   its Memo Studio session),
3. ``memo_docx_renderer.english_package_validation_errors``.

Prints the pass rate — overall, first attempts, and per engine (read from
the model names in the run's stream log) — and the error classes that
failed packages, most frequent first. ``--triage`` validates with the
risk-card wording checks moved out of the gate (``editorial_risk_checks=
False``) and counts them as warnings instead, to show what R11's triage
would pass. Buffett packages (no ``sections``) are skipped.

READ-ONLY: every package is deep-copied, the source-URL report is not
written, and nothing is created under the data dir.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_ATTEMPT_RE = re.compile(r"memo_package\.en\.attempt-(\d+)\.json$")
_MODEL_RE = re.compile(r'"model"\s*:\s*"([^"]+)"')


def find_packages(data_dir: Path) -> list[Path]:
    """Stored attempts and final packages, oldest run first."""
    memos = data_dir / "memos"
    found = list(memos.glob("*/*/logs/memo_package.en.attempt-*.json"))
    found += list(memos.glob("*/*/logs/memo_package.json"))

    def order(path: Path) -> tuple:
        match = _ATTEMPT_RE.search(path.name)
        return (str(path.parent.parent), 0 if match else 1, int(match.group(1)) if match else 0)

    return sorted(set(found), key=order)


def run_engine(run_dir: Path) -> str:
    """"claude" / "gemini" from the model names the run's stream log
    recorded; "unknown" when there is no log."""
    stream = run_dir / "logs" / "stream.jsonl"
    try:
        text = stream.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "unknown"
    models = {model.lower() for model in _MODEL_RE.findall(text)}
    if any(model.startswith("gemini") for model in models):
        return "gemini"
    if any("claude" in model or model in {"opus", "sonnet", "haiku"} for model in models):
        return "claude"
    return "unknown"


def error_class(message: str) -> str:
    """A message with its locations, ids, quoted text and numbers blanked,
    so the same rule failing in different places counts once."""
    text = str(message or "")
    text = re.sub(r"^[a-z0-9_]+ blocks\[\d+\]", "<section> blocks[*]", text)
    text = re.sub(r"^section [a-z0-9_]+", "section <id>", text)
    text = re.sub(r"\[\d+\]", "[*]", text)
    text = re.sub(r"'[^']*'|\"[^\"]*\"|“[^”]*”", "'…'", text)
    text = re.sub(r"\bS\d+\b|\bC\d+\b", "<id>", text)
    text = re.sub(r"\d+", "N", text)
    text = re.sub(r"^[a-z0-9_]+: ", "<section>: ", text)
    return text[:160]


def replay_package(path: Path, *, triage: bool = False) -> dict[str, Any]:
    from server import memo_docx_renderer, memo_fact_check

    run_dir = path.parent.parent
    company_id = run_dir.parent.name
    result: dict[str, Any] = {
        "path": str(path),
        "run": run_dir.name,
        "company": company_id,
        "file": path.name,
        "attempt": None,
        "engine": run_engine(run_dir),
    }
    match = _ATTEMPT_RE.search(path.name)
    if match:
        result["attempt"] = int(match.group(1))
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {**result, "status": "unreadable", "errors": [f"unreadable package: {exc}"]}
    if not isinstance(stored, dict) or not isinstance(stored.get("sections"), list):
        return {**result, "status": "skipped", "errors": [], "reason": "not a late-stage package"}
    package, repairs = memo_docx_renderer.repair_package_structure(copy.deepcopy(stored))
    try:
        attached = memo_fact_check.attach_source_urls(
            package, company_id=company_id, run_dir=run_dir, write_report=False
        )
    except Exception as exc:  # noqa: BLE001 — attachment is best effort, as in a run
        attached = [f"(attachment failed: {type(exc).__name__}: {exc})"]
    try:
        structure = memo_docx_renderer._structure_for(package)
        structure_name = f"{structure.stage} v{structure.version}"
    except Exception as exc:  # noqa: BLE001
        structure_name = f"unknown ({type(exc).__name__})"
    errors = memo_docx_renderer.english_package_validation_errors(
        package, editorial_risk_checks=not triage
    )
    warnings = memo_docx_renderer.risk_card_quality_findings(package) if triage else []
    return {
        **result,
        "status": "pass" if not errors else "fail",
        "structure": structure_name,
        "repairs": len(repairs),
        "urls_attached": len(attached),
        "errors": errors,
        "warnings": warnings,
    }


def summarize(rows: list[dict]) -> dict[str, Any]:
    judged = [row for row in rows if row["status"] in {"pass", "fail"}]
    first = [row for row in judged if row.get("attempt") == 1]
    by_engine: dict[str, list[dict]] = defaultdict(list)
    for row in judged:
        by_engine[row["engine"]].append(row)
    classes: Counter = Counter()
    packages_per_class: dict[str, set] = defaultdict(set)
    for row in judged:
        for message in row["errors"]:
            key = error_class(message)
            classes[key] += 1
            packages_per_class[key].add(row["path"])

    def rate(items: list[dict]) -> dict[str, Any]:
        passed = sum(1 for row in items if row["status"] == "pass")
        return {
            "packages": len(items),
            "pass": passed,
            "pass_rate": round(passed / len(items), 3) if items else None,
        }

    return {
        "overall": rate(judged),
        "first_attempts": rate(first),
        "by_engine": {engine: rate(items) for engine, items in sorted(by_engine.items())},
        "skipped": sum(1 for row in rows if row["status"] == "skipped"),
        "unreadable": sum(1 for row in rows if row["status"] == "unreadable"),
        "error_classes": [
            {"count": count, "packages": len(packages_per_class[key]), "class": key}
            for key, count in classes.most_common()
        ],
    }


def _pct(rate: dict) -> str:
    if not rate["packages"]:
        return "—"
    return f"{rate['pass']}/{rate['packages']} ({rate['pass_rate'] * 100:.0f}%)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--data-dir", type=Path, default=REPO / "data")
    parser.add_argument("--triage", action="store_true", help="risk-card wording checks as warnings (R11 FIX 1)")
    parser.add_argument("--first-only", action="store_true", help="attempt-1 files only")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    parser.add_argument("--quiet", action="store_true", help="summary only, no per-package rows")
    args = parser.parse_args(argv)

    data_dir = args.data_dir.resolve()
    if not (data_dir / "memos").is_dir():
        print(f"no memos/ under {data_dir}", file=sys.stderr)
        return 2
    # Point the stores the URL attachment reads at this data dir for the
    # replay — reads only; nothing is written — and put them back after.
    from server import research_store, serena_analysis

    saved = (research_store.RESEARCH_ROOT, serena_analysis.ANALYSIS_ROOT)
    research_store.RESEARCH_ROOT = data_dir / "research"
    serena_analysis.ANALYSIS_ROOT = data_dir / "serena_analysis"
    try:
        paths = find_packages(data_dir)
        if args.first_only:
            paths = [path for path in paths if path.name.endswith(".attempt-1.json")]
        rows = [replay_package(path, triage=args.triage) for path in paths]
    finally:
        research_store.RESEARCH_ROOT, serena_analysis.ANALYSIS_ROOT = saved
    summary = summarize(rows)
    if args.json:
        print(json.dumps({"data_dir": str(data_dir), "triage": args.triage, "summary": summary, "packages": rows}, ensure_ascii=False, indent=1))
        return 0

    from server import memo_docx_renderer

    print(f"# Memo package replay — {data_dir} (read-only)")
    print(
        f"renderer {memo_docx_renderer.RENDERER_VERSION} · repair → attach_source_urls"
        f"(write_report=False) → english_package_validation_errors"
        + (" (triage: risk-card wording as warnings)" if args.triage else "")
    )
    if not args.quiet:
        print()
        print("| run | file | engine | structure | repairs | urls | errors | warnings | result |")
        print("|---|---|---|---|---|---|---|---|---|")
        for row in rows:
            print(
                f"| {row['company']}/{row['run'][:18]} | {row['file']} | {row['engine']} | "
                f"{row.get('structure', '—')} | {row.get('repairs', '—')} | {row.get('urls_attached', '—')} | "
                f"{len(row['errors'])} | {len(row.get('warnings') or [])} | {row['status']} |"
            )
    print()
    print(f"- packages judged: {summary['overall']['packages']} (skipped {summary['skipped']}, unreadable {summary['unreadable']})")
    print(f"- pass: {_pct(summary['overall'])}")
    print(f"- first attempts: {_pct(summary['first_attempts'])}")
    for engine, rate in summary["by_engine"].items():
        print(f"- {engine}: {_pct(rate)}")
    if summary["error_classes"]:
        print()
        print("## Error classes (count · packages)")
        for item in summary["error_classes"]:
            print(f"- {item['count']} · {item['packages']} — {item['class']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
