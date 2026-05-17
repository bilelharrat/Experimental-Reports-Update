"""Rasterize the deck via headless Chrome — crisp PNG + vector PDF.

Best-effort: if no Chrome/Chromium is found the harness still produces
the HTML decks and just skips rasterization.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import render, tokens

_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def _find_chrome() -> str | None:
    for c in _CANDIDATES:
        if c and Path(c).exists():
            return c
    ms = Path.home() / "Library/Caches/ms-playwright"
    if ms.exists():
        for hs in sorted(ms.glob("chromium_headless_shell-*/chrome-mac/headless_shell"),
                          reverse=True):
            return str(hs)
        for ch in sorted(ms.glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"),
                          reverse=True):
            return str(ch)
    return None


def _run(chrome: str, args: list[str]) -> bool:
    try:
        r = subprocess.run([chrome, "--headless=new", "--disable-gpu",
                            "--no-sandbox", "--hide-scrollbars", *args],
                           capture_output=True, timeout=120)
        return r.returncode == 0
    except Exception as exc:  # noqa: BLE001
        print(f"[rasterize] chrome error: {exc}")
        return False


def rasterize_run(run: Path, locales: list[str], scale: int = 3) -> None:
    chrome = _find_chrome()
    if not chrome:
        print("[rasterize] no Chrome found — skipping PNG/PDF (HTML still produced)")
        return
    print(f"[rasterize] chrome: {chrome}")
    brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
    src = run / ".src"
    for loc in locales:
        # full-deck PDF (vector)
        deck_file = run / f"brief-{loc}.html"
        _run(chrome, [f"--print-to-pdf={run}/brief-{loc}.pdf",
                      "--no-pdf-header-footer",
                      f"--virtual-time-budget=4000",
                      f"file://{deck_file}"])
        # per-page PNG at <scale>x
        docs = render.build_page_docs(brief, loc)
        pdir = run / "pages" / loc
        pdir.mkdir(parents=True, exist_ok=True)
        sdir = src / loc
        sdir.mkdir(parents=True, exist_ok=True)
        for i, doc in enumerate(docs, 1):
            f = sdir / f"page-{i:02d}.html"
            f.write_text(doc, encoding="utf-8")
            out = pdir / f"page-{i:02d}.png"
            _run(chrome, [
                f"--screenshot={out}",
                f"--window-size={tokens.PAGE_W},{tokens.PAGE_H}",
                f"--force-device-scale-factor={scale}",
                "--default-background-color=00000000",
                "--virtual-time-budget=4000",
                f"file://{f}"])
        n = len(list(pdir.glob("*.png")))
        print(f"[rasterize] {loc}: {n} page PNGs @ {scale}x → {pdir}")
    shutil.rmtree(src, ignore_errors=True)
