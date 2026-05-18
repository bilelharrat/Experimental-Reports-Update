"""CLI: python -m scripts.report_visuals
        [--source PATH] [--locale en,zh] [--pages 1,3,5] [--scale N]

Art is generated text-free via codex $imagegen; all copy is overlaid
in code. Output: data/report_visuals/<deck>/<ts>/.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

from . import imagegen, prompts, render, translate
from .parse import parse_deck

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SRC = Path("/Users/rparker/Downloads/preview (1).html")


def main() -> None:
    ap = argparse.ArgumentParser(prog="report_visuals")
    ap.add_argument("--source", default=str(DEFAULT_SRC))
    ap.add_argument("--deck", default="alphasense")
    ap.add_argument("--locale", default="en")
    ap.add_argument("--pages", default="", help="comma list, e.g. 1,3,5 (default: all)")
    ap.add_argument("--scale", type=int, default=2)
    args = ap.parse_args()

    src = Path(args.source)
    if not src.exists():
        raise SystemExit(f"source not found: {src}")
    locales = [x.strip() for x in args.locale.split(",") if x.strip()]
    want = {int(x) for x in args.pages.split(",") if x.strip()} if args.pages else None

    pages = parse_deck(src)
    if want:
        pages = [p for p in pages if p["page"] in want]
    if not pages:
        raise SystemExit("no pages parsed")
    total = max(p["page"] for p in parse_deck(src))

    if "zh" in locales:
        print(f"[i18n] translating {len(pages)} pages → zh via Claude Code …")
        translate.bilingualize(pages, locales=locales)
        done = sum(1 for p in pages if isinstance(p.get("headline"), dict))
        print(f"[i18n] {done}/{len(pages)} pages bilingual")

    ts = _dt.datetime.now().strftime("%Y-%m-%d__%H%M%S")
    run = REPO / "data" / "report_visuals" / args.deck / ts
    art_dir = run / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    chrome = render.find_chrome()
    manifest = {"source": str(src), "ts": ts, "pages": []}

    for p in pages:
        n = p["page"]
        hero = n == 1
        prompt = prompts.art_prompt(p, hero=hero)
        art = art_dir / f"page-{n:02d}.png"
        (art_dir / f"page-{n:02d}.prompt.txt").write_text(prompt, encoding="utf-8")
        print(f"[art] page {n} ({'hero' if hero else 'std'}) → codex $imagegen …")
        ok, note = imagegen.generate(prompt, art)
        print(f"[art] page {n}: {'OK' if ok else 'FAIL'} ({note})")
        rec = {"page": n, "art": str(art), "art_ok": ok, "note": note,
               "renders": {}}
        if ok and chrome:
            for loc in locales:
                doc = render.page_html(p, art, loc, total, hero)
                src_html = run / "_src" / f"{loc}-page-{n:02d}.html"
                src_html.parent.mkdir(parents=True, exist_ok=True)
                src_html.write_text(doc, encoding="utf-8")
                out = run / "pages" / loc / f"page-{n:02d}.png"
                if render.rasterize(chrome, src_html, out, scale=args.scale):
                    rec["renders"][loc] = str(out)
                    print(f"[render] page {n} [{loc}] → {out.name}")
        manifest["pages"].append(rec)

    # preview pages that rendered, per locale
    for loc in locales:
        imgs = sorted(
            (run / "pages" / loc).glob("page-*.png")) if (run / "pages" / loc).exists() else []
        if not imgs:
            continue
        body = "".join(
            f'<img src="pages/{loc}/{i.name}" '
            f'style="display:block;width:920px;margin:0 auto 28px;'
            f'border-radius:14px">' for i in imgs)
        (run / f"preview-{loc}.html").write_text(
            f'<!doctype html><body style="background:#02040a;padding:40px 0">'
            f'{body}</body>', encoding="utf-8")

    (run / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    import shutil
    shutil.rmtree(run / "_src", ignore_errors=True)
    print(f"[done] {run}")
    for loc in locales:
        if (run / f"preview-{loc}.html").exists():
            print(f"  open: {run}/preview-{loc}.html")


if __name__ == "__main__":
    main()
