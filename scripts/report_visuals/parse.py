"""Parse an HTML report deck into a per-page content model.

Tuned for the AlphaSense Visual Memo shape (one
``<section class="page" data-page="N">`` per page with .kicker / h1 /
.subtitle / footer) but tolerant of missing pieces.
"""
from __future__ import annotations

import html
import re
from pathlib import Path


def _strip(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _first(pattern: str, block: str) -> str:
    m = re.search(pattern, block, re.S)
    return _strip(m.group(1)) if m else ""


def parse_deck(source: Path) -> list[dict]:
    raw = Path(source).read_text(encoding="utf-8", errors="ignore")
    pages: list[dict] = []
    for m in re.finditer(
        r'<section[^>]*data-page="(\d+)"[^>]*>(.*?)</section>', raw, re.S
    ):
        n = int(m.group(1))
        b = m.group(2)
        kicker = _first(r'class="kicker">(.*?)</div>', b)
        headline = _first(r"<h1[^>]*>(.*?)</h1>", b)
        dek = _first(r'class="subtitle">(.*?)</p>', b)
        foot = _first(r"<footer[^>]*>(.*?)</footer>", b)
        # main text content (panels, metrics) minus the chrome we already took
        body = b
        for pat in (r'class="kicker">.*?</div>', r"<h1[^>]*>.*?</h1>",
                    r'class="subtitle">.*?</p>', r"<footer[^>]*>.*?</footer>"):
            body = re.sub(pat, " ", body, flags=re.S)
        content = _strip(body)
        pages.append({
            "page": n,
            "kicker": kicker,
            "headline": headline,
            "dek": dek,
            "footer": foot,
            "content": content[:1200],
        })
    pages.sort(key=lambda p: p["page"])
    return pages
