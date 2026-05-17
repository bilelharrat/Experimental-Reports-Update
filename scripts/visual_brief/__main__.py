"""CLI: python -m scripts.visual_brief AMD [--fixture PATH] [--locale en,zh]
            [--no-raster] [--scale N] [--lint] [--critique] [--qa]
            [--run PATH]   # QA an existing run without re-rendering
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import critique, lint, rasterize, render

REPO = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser(prog="visual_brief")
    ap.add_argument("ticker", nargs="?", default="AMD")
    ap.add_argument("--fixture", default=None,
                    help="path to brief.json (default tests/fixtures/brief_<ticker>.json)")
    ap.add_argument("--locale", default="en,zh")
    ap.add_argument("--no-raster", action="store_true")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--lint", action="store_true",
                    help="run the deterministic visual linter")
    ap.add_argument("--critique", action="store_true",
                    help="run the LLM vision critique (costs tokens)")
    ap.add_argument("--qa", action="store_true", help="--lint and --critique")
    ap.add_argument("--run", default=None,
                    help="QA an existing run dir instead of rendering")
    args = ap.parse_args()

    do_lint = args.lint or args.qa
    do_crit = args.critique or args.qa
    locales = [x.strip() for x in args.locale.split(",") if x.strip()]

    if args.run:
        run = Path(args.run).resolve()
        if not run.exists():
            raise SystemExit(f"run not found: {run}")
    else:
        fixture = (Path(args.fixture) if args.fixture
                   else REPO / "tests" / "fixtures" / f"brief_{args.ticker.lower()}.json")
        if not fixture.exists():
            raise SystemExit(f"fixture not found: {fixture}")
        run = render.write_run(fixture, locales)
        if not args.no_raster:
            rasterize.rasterize_run(run, locales, scale=args.scale)
        print(f"[done] open: {run}/brief-{locales[0]}.html")

    code = 0
    if do_lint:
        code |= lint.lint_run(run)
    if do_crit:
        c = critique.critique_run(run)
        code |= (1 if c == 1 else 0)  # parse/exec failure is hard-fail
    sys.exit(code)


if __name__ == "__main__":
    main()
