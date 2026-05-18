"""Composite: generated art (full-bleed) + crisp coded text overlay.

All copy is rendered by code (not the image model) so it is sharp and
locale-swappable. Rasterized via headless Chrome.
"""
from __future__ import annotations

import html
import shutil
import subprocess
from pathlib import Path

PAGE_W, PAGE_H = 920, 1220  # matches the AlphaSense deck page size

_CHROME = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "",
]


def find_chrome() -> str | None:
    for c in _CHROME:
        if c and Path(c).exists():
            return c
    ms = Path.home() / "Library/Caches/ms-playwright"
    for g in sorted(ms.glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"),
                     reverse=True):
        return str(g)
    return None


def _t(v, loc: str) -> str:
    if isinstance(v, dict):
        v = v.get(loc) or v.get("en") or ""
    return html.escape(str(v or ""), quote=True)


_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:__W__px;height:__H__px;overflow:hidden;
  font-family:Inter,"SF Pro Display",-apple-system,BlinkMacSystemFont,
  "Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:#04070f}
html[lang="zh"] body{font-family:"PingFang SC","Hiragino Sans GB",
  "Noto Sans SC","Microsoft YaHei",Inter,sans-serif}
.page{position:relative;width:__W__px;height:__H__px;overflow:hidden;
  color:#f4f9ff}
.art{position:absolute;inset:0;background-position:center;
  background-size:cover;background-repeat:no-repeat}
.scrim{position:absolute;inset:0;background:
  linear-gradient(115deg,rgba(4,7,15,.92) 0%,rgba(4,7,15,.66) 38%,
  rgba(4,7,15,.10) 70%),
  linear-gradient(0deg,rgba(4,7,15,.85) 0%,rgba(4,7,15,0) 34%)}
.wrap{position:absolute;inset:0;padding:74px 70px;display:flex;
  flex-direction:column}
.top{display:flex;justify-content:space-between;align-items:flex-start}
.kick{font-size:14px;font-weight:800;letter-spacing:.18em;
  text-transform:uppercase;color:#bfe9ff;background:rgba(70,230,255,.10);
  border:1px solid rgba(70,230,255,.30);border-radius:999px;
  padding:9px 16px}
html[lang="zh"] .kick{letter-spacing:.06em}
.pnum{font-size:14px;font-weight:800;color:#cfe4f6;
  background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.14);
  border-radius:999px;padding:8px 14px}
.mid{margin-top:auto;max-width:760px}
h1{font-size:62px;line-height:1.04;letter-spacing:-.035em;
  font-weight:850;text-shadow:0 8px 40px rgba(0,0,0,.6)}
html[lang="zh"] h1{font-size:56px;line-height:1.18;letter-spacing:0}
.bar{width:104px;height:5px;border-radius:999px;margin:26px 0;
  background:linear-gradient(90deg,#46e6ff,#b878ff);
  box-shadow:0 0 22px rgba(70,230,255,.55)}
.dek{font-size:21px;line-height:1.5;color:#d6e4f2;max-width:680px;
  text-shadow:0 4px 24px rgba(0,0,0,.55)}
html[lang="zh"] .dek{line-height:1.66}
.foot{margin-top:40px;font-size:12.5px;color:#8fa6bb;letter-spacing:.02em;
  border-top:1px solid rgba(255,255,255,.10);padding-top:14px}
.hero h1{font-size:76px;max-width:820px}
html[lang="zh"] .hero h1{font-size:64px}
"""


def page_html(page: dict, art_path: Path, loc: str, total: int,
              hero: bool) -> str:
    css = _CSS.replace("__W__", str(PAGE_W)).replace("__H__", str(PAGE_H))
    cls = "page hero" if hero else "page"
    return f"""<!doctype html><html lang="{loc}"><head><meta charset="utf-8">
<style>{css}</style></head><body>
<div class="{cls}">
  <div class="art" style="background-image:url('file://{art_path}')"></div>
  <div class="scrim"></div>
  <div class="wrap">
    <div class="top">
      <div class="kick">{_t(page.get('kicker'), loc)}</div>
      <div class="pnum">{page.get('page')}/{total}</div>
    </div>
    <div class="mid">
      <h1>{_t(page.get('headline'), loc)}</h1>
      <div class="bar"></div>
      <div class="dek">{_t(page.get('dek'), loc)}</div>
      <div class="foot">{_t(page.get('footer'), loc)}</div>
    </div>
  </div>
</div></body></html>"""


def rasterize(chrome: str, html_file: Path, out_png: Path,
              scale: int = 2) -> bool:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--hide-scrollbars", "--allow-file-access-from-files",
             f"--screenshot={out_png}",
             f"--window-size={PAGE_W},{PAGE_H}",
             f"--force-device-scale-factor={scale}",
             "--virtual-time-budget=3000", f"file://{html_file}"],
            capture_output=True, timeout=90)
        return r.returncode == 0 and out_png.exists()
    except Exception:  # noqa: BLE001
        return False
