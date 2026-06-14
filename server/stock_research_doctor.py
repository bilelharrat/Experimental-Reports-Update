"""CLI entry point for the Stock Research data doctor."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import stock_research


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m server.stock_research_doctor",
        description="Run read-only Stock Research artifact health checks.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write the full doctor payload as JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when the doctor reports any error or warning.",
    )
    parser.add_argument(
        "--max-idle-seconds",
        type=int,
        default=stock_research.ACTIVE_JOB_MAX_IDLE_SECONDS,
        help="Idle threshold before unterminated progress logs are stale.",
    )
    return parser


def _print_text(payload: dict) -> None:
    summary = payload.get("summary") or {}
    print(
        "Stock Research doctor: "
        f"{payload.get('status')} "
        f"({summary.get('error_count', 0)} errors, "
        f"{summary.get('warning_count', 0)} warnings)"
    )
    for issue in payload.get("issues") or []:
        path = f" [{issue.get('path')}]" if issue.get("path") else ""
        print(
            f"- {issue.get('severity')}: {issue.get('type')} - "
            f"{issue.get('message')}{path}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    max_idle_seconds = max(0, int(args.max_idle_seconds))
    payload = stock_research.stock_research_doctor(
        max_idle_seconds=max_idle_seconds,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        _print_text(payload)
    summary = payload.get("summary") or {}
    issue_count = int(summary.get("error_count", 0)) + int(
        summary.get("warning_count", 0)
    )
    return 1 if args.strict and issue_count else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
