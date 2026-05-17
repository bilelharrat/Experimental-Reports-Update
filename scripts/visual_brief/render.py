"""Compose the bilingual deck and write a versioned run folder."""
from __future__ import annotations

import datetime as _dt
import html
import json
from pathlib import Path
from typing import Any

from . import components, tokens

REPO = Path(__file__).resolve().parents[2]
OUT_ROOT = REPO / "data" / "visual_briefs"


def _t(d: Any, loc: str) -> str:
    if isinstance(d, dict):
        return str(d.get(loc) or d.get("en") or "")
    return str(d or "")


def _e(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _page_html(page: dict, idx: int, total: int, meta: dict, loc: str) -> str:
    page = dict(page)
    page["_posture"] = _t(meta.get("posture", ""), loc)
    page["_posture_label"] = "投资立场" if loc == "zh" else "IC POSTURE"
    body = components.render_body(page, loc)
    srcs = page.get("sources") or []
    src_html = " ".join(
        f'<span><b>{_e(s.get("label",""))}</b></span>' for s in srcs)
    disc = _t(meta.get("disclaimer", {}), loc)
    foot_mid = _t(page.get("footer", {}), loc)
    return f'''<section class="page">
  <div class="page-grid"></div><div class="page-aura"></div>
  <div class="page-mark">{_e(meta.get("ticker",""))}</div>
  <div class="row">
    <div class="kicker"><span class="dot"></span>{_e(_t(page.get("kicker",{}), loc))}</div>
    <div class="pnum">{idx}/{total}</div>
  </div>
  <h1 class="head">{_e(_t(page.get("headline",{}), loc))}</h1>
  <div class="accent-bar"></div>
  <p class="dek">{_e(_t(page.get("dek",{}), loc))}</p>
  <main class="body">{body}</main>
  <footer class="foot">
    <div class="src">{src_html}</div>
    <div style="text-align:right">
      <div>{_e(foot_mid)}</div>
      <div style="color:#56708a;margin-top:4px">{_e(meta.get("ticker",""))} ·
        {_e(meta.get("as_of",""))} · {_e(disc)}</div>
    </div>
  </footer>
</section>'''


def build_deck(brief: dict, loc: str) -> str:
    meta = brief.get("meta", {})
    pages = brief.get("pages", [])
    body = "".join(
        _page_html(p, i + 1, len(pages), meta, loc)
        for i, p in enumerate(pages))
    name = _t(meta.get("name", {}), loc)
    title = f'{meta.get("ticker","")} — {name}'
    return f'''<!doctype html>
<html lang="{loc}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_e(title)} · Visual Stock Brief</title>
<style>{tokens.GLOBAL_CSS}</style>
</head>
<body><div class="deck">{body}</div></body>
</html>'''


def build_page_docs(brief: dict, loc: str) -> list[str]:
    """Standalone single-page HTML docs (for per-page rasterization)."""
    meta = brief.get("meta", {})
    pages = brief.get("pages", [])
    docs = []
    for i, p in enumerate(pages):
        sec = _page_html(p, i + 1, len(pages), meta, loc)
        docs.append(f'''<!doctype html><html lang="{loc}"><head>
<meta charset="utf-8"/><style>{tokens.GLOBAL_CSS}
.deck{{padding:0;gap:0}}.page{{border-radius:0;box-shadow:none}}
.page::before{{display:none}}</style></head>
<body><div class="deck">{sec}</div></body></html>''')
    return docs


def write_run(fixture_path: Path, locales: list[str]) -> Path:
    brief = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    ticker = brief.get("meta", {}).get("ticker", "BRIEF")
    ts = _dt.datetime.now().strftime("%Y-%m-%d__%H%M%S")
    run = OUT_ROOT / ticker / ts
    (run / "pages").mkdir(parents=True, exist_ok=True)
    (run / "brief.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    for loc in locales:
        deck = build_deck(brief, loc)
        (run / f"brief-{loc}.html").write_text(deck, encoding="utf-8")
    print(f"[render] {ticker} · {','.join(locales)} → {run}")
    return run
