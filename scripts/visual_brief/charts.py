"""Hand-built SVG chart kit.

Every chart is a pure function of its typed payload → an SVG string.
No charting library: every coordinate is computed here so output is
deterministic and golden-testable. Colours come from tokens.PALETTE.
"""
from __future__ import annotations

import html
import math
from typing import Any

from . import tokens

C = tokens.PALETTE


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _nice(x: float, round_: bool = True) -> float:
    if x <= 0:
        return 1.0
    exp = math.floor(math.log10(x))
    f = x / (10 ** exp)
    if round_:
        nf = 1 if f < 1.5 else 2 if f < 3 else 5 if f < 7 else 10
    else:
        nf = 1 if f <= 1 else 2 if f <= 2 else 5 if f <= 5 else 10
    return nf * (10 ** exp)


def _ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    rng = _nice(hi - lo, False)
    step = _nice(rng / (n - 1))
    start = math.floor(lo / step) * step
    end = math.ceil(hi / step) * step
    out, v = [], start
    while v <= end + 1e-9:
        out.append(round(v, 6))
        v += step
    return out


def _num(v: float) -> str:
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.1f}"


def _fmt(v: float, unit: str = "") -> str:
    """unit: "" | "%" | "$" | "$B"/"$M" | "B"/"M"/"x"/"pts" (prefix $, suffix rest)."""
    if v is None:
        return "—"
    s = _num(abs(v))
    sign = "-" if v < 0 else ""
    if unit == "%":
        return f"{sign}{s}%"
    if unit.startswith("$"):
        return f"{sign}${s}{unit[1:]}"
    return f"{sign}{s}{unit}"


def _smooth_path(pts: list[tuple[float, float]]) -> str:
    """Catmull-Rom → cubic Bézier, tension clamped to avoid overshoot."""
    if len(pts) < 2:
        return ""
    d = [f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(
            f"C {c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} "
            f"{p2[0]:.2f} {p2[1]:.2f}"
        )
    return " ".join(d)


# ---- area / line chart -------------------------------------------------
def area_chart(payload: dict, *, accent: str = "cyan", locale: str = "en",
               w: int = 1010, h: int = 600) -> str:
    series = payload.get("series") or []
    unit = payload.get("unit", "")
    pts = [(p["x"], p["y"]) for p in series if p.get("y") is not None]
    if len(pts) < 2:
        return f'<svg viewBox="0 0 {w} {h}"></svg>'
    ml, mr, mt, mb = 70, 22, 60, 46
    ys = [p[1] for p in pts]
    lo, hi = min(ys), max(ys)
    tks = _ticks(lo - (hi - lo) * 0.06, hi + (hi - lo) * 0.07)
    ylo, yhi = tks[0], tks[-1]
    n = len(pts)

    def X(i): return ml + (w - ml - mr) * i / (n - 1)
    def Y(v): return mt + (h - mt - mb) * (1 - (v - ylo) / (yhi - ylo))

    col = C[accent]
    sp = [(X(i), Y(v)) for i, (_, v) in enumerate(pts)]
    line = _smooth_path(sp)
    area = (f'{line} L {sp[-1][0]:.2f} {h-mb:.2f} '
            f'L {sp[0][0]:.2f} {h-mb:.2f} Z')

    col2 = C["violet"]
    grid = []
    for t in tks:
        gy = Y(t)
        grid.append(
            f'<line x1="{ml}" y1="{gy:.1f}" x2="{w-mr}" y2="{gy:.1f}" '
            f'stroke="rgba(255,255,255,.06)"/>'
            f'<text x="{ml-14}" y="{gy+5:.1f}" text-anchor="end" '
            f'fill="#7f97ad" font-size="14">{_esc(_fmt(t, unit))}</text>'
        )
    xl = []
    every = max(1, n // 7)
    for i, (xx, _) in enumerate(pts):
        if i % every == 0 or i == n - 1:
            gx = X(i)
            grid.append(
                f'<line x1="{gx:.1f}" y1="{mt}" x2="{gx:.1f}" y2="{h-mb}" '
                f'stroke="rgba(255,255,255,.035)"/>')
            xl.append(
                f'<text x="{gx:.1f}" y="{h-14}" text-anchor="middle" '
                f'fill="#7f97ad" font-size="13.5">{_esc(xx)}</text>'
            )
    last = sp[-1]
    mk = (
        f'<line x1="{last[0]:.1f}" y1="{mt}" x2="{last[0]:.1f}" y2="{h-mb}" '
        f'stroke="{col}" stroke-opacity=".30" stroke-dasharray="2 6"/>'
        f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="20" '
        f'fill="{col}" opacity=".10"/>'
        f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="12" '
        f'fill="{col}" opacity=".22"/>'
        f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="6.5" fill="#eaf9ff" '
        f'stroke="{col}" stroke-width="3"/>'
        f'<text x="{last[0]-16:.1f}" y="{last[1]-18:.1f}" text-anchor="end" '
        f'fill="#eaf9ff" font-size="20" font-weight="850">'
        f'{_esc(_fmt(pts[-1][1], unit))}</text>'
    )
    # event markers — leader line from a top label down to the actual
    # data point, with a value pill at the point. (Markers come from
    # brief.json; no derived/computed series are drawn.)
    xstr = [str(p["x"]) for p in series if p.get("y") is not None]
    msvg = []
    slots = []
    for mkr in payload.get("markers", []):
        xs = str(mkr.get("x"))
        if xs not in xstr:
            continue
        i = xstr.index(xs)
        gx, gy = X(i), Y(pts[i][1])
        lab = mkr.get("label", "")
        if isinstance(lab, dict):
            lab = lab.get(locale) or lab.get("en") or ""
        ly = mt - 34
        slots.append((gx, gy, lab, pts[i][1]))
    for gx, gy, lab, yval in slots:
        msvg.append(
            f'<line x1="{gx:.1f}" y1="{mt-22:.1f}" x2="{gx:.1f}" '
            f'y2="{gy-12:.1f}" stroke="{C["gold"]}" stroke-opacity=".5" '
            f'stroke-dasharray="3 5"/>'
            f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="6" fill="{C["gold"]}" '
            f'stroke="#06101f" stroke-width="2"/>'
            f'<text x="{gx:.1f}" y="{mt-30:.1f}" text-anchor="middle" '
            f'fill="#dfe9f4" font-size="14" font-weight="800">{_esc(lab)}</text>'
            f'<text x="{gx:.1f}" y="{gy-22:.1f}" text-anchor="middle" '
            f'fill="{C["gold"]}" font-size="13" font-weight="800">'
            f'{_esc(_fmt(yval, unit))}</text>')
    return f'''<svg viewBox="0 0 {w} {h}" width="100%"
  font-family="Inter,system-ui,sans-serif">
 <defs>
  <linearGradient id="ac_area" x1="0" y1="0" x2="0" y2="1">
   <stop offset="0" stop-color="{col}" stop-opacity=".42"/>
   <stop offset=".55" stop-color="{col2}" stop-opacity=".14"/>
   <stop offset="1" stop-color="{col2}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="ac_line" x1="0" y1="0" x2="1" y2="0">
   <stop offset="0" stop-color="{col}"/>
   <stop offset="1" stop-color="{col2}"/>
  </linearGradient>
  <filter id="ac_glow" x="-20%" y="-40%" width="140%" height="180%">
   <feDropShadow dx="0" dy="7" stdDeviation="9"
     flood-color="{col}" flood-opacity=".55"/>
  </filter>
 </defs>
 {''.join(grid)}
 <path d="{area}" fill="url(#ac_area)"/>
 <path d="{line}" fill="none" stroke="url(#ac_line)" stroke-width="4"
   stroke-linecap="round" stroke-linejoin="round" filter="url(#ac_glow)"/>
 {''.join(msvg)}{''.join(xl)}{mk}
</svg>'''


# ---- donut -------------------------------------------------------------
def donut(payload: dict, *, locale: str = "en", w: int = 360) -> str:
    slices = [s for s in (payload.get("slices") or []) if s.get("value")]
    total = sum(s["value"] for s in slices) or 1
    unit = payload.get("unit", "$B")
    cx = cy = w / 2
    r, rin = w * 0.40, w * 0.255
    ang = -90.0
    arcs = []
    for s in slices:
        frac = s["value"] / total
        a0 = math.radians(ang)
        ang += frac * 360
        a1 = math.radians(ang - 1.4)  # gap
        large = 1 if (a1 - a0) > math.pi else 0
        x0o, y0o = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1o, y1o = cx + r * math.cos(a1), cy + r * math.sin(a1)
        x0i, y0i = cx + rin * math.cos(a1), cy + rin * math.sin(a1)
        x1i, y1i = cx + rin * math.cos(a0), cy + rin * math.sin(a0)
        col = C.get(s.get("accent", "cyan"), C["cyan"])
        arcs.append(
            f'<path d="M {x0o:.2f} {y0o:.2f} '
            f'A {r:.2f} {r:.2f} 0 {large} 1 {x1o:.2f} {y1o:.2f} '
            f'L {x0i:.2f} {y0i:.2f} '
            f'A {rin:.2f} {rin:.2f} 0 {large} 0 {x1i:.2f} {y1i:.2f} Z" '
            f'fill="{col}"/>'
        )
    ctr = payload.get("center", {})
    cl = _esc(ctr.get(locale, ctr.get("en", "")))
    return f'''<svg viewBox="0 0 {w} {w}" width="{w}"
  font-family="Inter,system-ui,sans-serif">
 <defs>
  <filter id="dn_glow" x="-30%" y="-30%" width="160%" height="160%">
   <feGaussianBlur stdDeviation="6" result="b"/>
   <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <radialGradient id="dn_sheen" cx="38%" cy="32%" r="72%">
   <stop offset="0" stop-color="#ffffff" stop-opacity=".16"/>
   <stop offset=".5" stop-color="#ffffff" stop-opacity="0"/>
  </radialGradient>
 </defs>
 <circle cx="{cx}" cy="{cy}" r="{(r+rin)/2:.1f}" fill="none"
   stroke="rgba(255,255,255,.04)" stroke-width="{r-rin:.1f}"/>
 <g filter="url(#dn_glow)">{''.join(arcs)}</g>
 <circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="url(#dn_sheen)"/>
 <circle cx="{cx}" cy="{cy}" r="{rin-1:.1f}" fill="#070f1d"
   stroke="rgba(126,205,255,.16)" stroke-width="1"/>
 <text x="{cx}" y="{cy-6}" text-anchor="middle" fill="#eaf5ff"
   font-size="34" font-weight="900" letter-spacing="-1">{_esc(_fmt(total,unit))}</text>
 <text x="{cx}" y="{cy+22}" text-anchor="middle" fill="#90a8bd"
   font-size="13" font-weight="800" letter-spacing="2">{cl}</text>
</svg>'''


def donut_legend(payload: dict, *, locale: str = "en") -> str:
    slices = [s for s in (payload.get("slices") or []) if s.get("value")]
    total = sum(s["value"] for s in slices) or 1
    unit = payload.get("unit", "$B")
    rows = []
    for s in slices:
        col = C.get(s.get("accent", "cyan"), C["cyan"])
        lbl = s.get("label", {})
        lbl = _esc(lbl.get(locale, lbl.get("en", "")) if isinstance(lbl, dict) else lbl)
        pct = s["value"] / total * 100
        rows.append(
            f'<div style="display:grid;grid-template-columns:16px 1fr auto;'
            f'align-items:center;column-gap:18px;padding:15px 4px;'
            f'border-top:1px solid rgba(255,255,255,.07)">'
            f'<i style="width:16px;height:16px;border-radius:5px;background:{col}"></i>'
            f'<span style="font-size:15.5px;color:#c7d8e8;font-weight:650;'
            f'line-height:1.3">{lbl}</span>'
            f'<span style="text-align:right;line-height:1.15">'
            f'<b style="display:block;font-size:18px;color:#eaf5ff;'
            f'font-weight:850">{_fmt(s["value"],unit)}</b>'
            f'<span style="font-size:13px;color:#8fa6bb;font-weight:700">'
            f'{pct:.0f}%</span></span></div>'
        )
    return ('<div style="display:flex;flex-direction:column">'
            + "".join(rows) + "</div>")


# ---- waterfall ---------------------------------------------------------
def waterfall(payload: dict, *, w: int = 1010, h: int = 640) -> str:
    start = payload["start"]
    steps = payload.get("steps", [])
    end = payload["end"]
    unit = payload.get("unit", "$")
    bars = [("base", start["label"], start["value"], 0, start["value"])]
    cum = start["value"]
    peak = cum
    for st in steps:
        v = st["value"]
        if v >= 0:
            bars.append((st.get("kind", "add"), st["label"], v, cum, cum + v))
            cum += v
        else:
            bars.append((st.get("kind", "subtract"), st["label"], v, cum + v, cum))
            cum += v
        peak = max(peak, cum)
    bars.append(("end", end["label"], end["value"], 0, end["value"]))
    peak = max(peak, end["value"]) * 1.12

    ml, mr, mt, mb = 64, 16, 30, 60
    n = len(bars)
    bw = (w - ml - mr) / n
    iw = bw * 0.62
    fill = {"base": C["blue"], "end": C["green"], "add": C["cyan"],
            "subtract": C["red"], "acquired": C["violet"]}
    defs = "".join(
        f'<linearGradient id="wf_{k}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{c}" stop-opacity="1"/>'
        f'<stop offset="1" stop-color="{c}" stop-opacity=".62"/></linearGradient>'
        for k, c in fill.items())

    def Y(v): return mt + (h - mt - mb) * (1 - v / peak)

    grid = []
    for t in _ticks(0, peak, 5):
        gy = Y(t)
        grid.append(
            f'<line x1="{ml}" y1="{gy:.1f}" x2="{w-mr}" y2="{gy:.1f}" '
            f'stroke="rgba(255,255,255,.06)"/>'
            f'<text x="{ml-12}" y="{gy+5:.1f}" text-anchor="end" '
            f'fill="#7f97ad" font-size="13">{_esc(_fmt(t,unit))}</text>')
    out, prev_top = [], None
    for i, (kind, lab, val, b, t) in enumerate(bars):
        x = ml + i * bw + (bw - iw) / 2
        yt, yb = Y(t), Y(b)
        col = fill.get(kind, C["cyan"])
        if prev_top is not None:
            out.append(
                f'<line x1="{x-(bw-iw)/2+2:.1f}" y1="{prev_top:.1f}" '
                f'x2="{x:.1f}" y2="{prev_top:.1f}" '
                f'stroke="rgba(255,255,255,.55)" stroke-width="2" '
                f'stroke-dasharray="5 4"/>')
        bh = max(3, yb - yt)
        out.append(
            f'<rect x="{x:.1f}" y="{yt:.1f}" width="{iw:.1f}" '
            f'height="{bh:.1f}" rx="7" fill="url(#wf_{kind})" '
            f'filter="drop-shadow(0 8px 20px {col}45)"/>'
            f'<rect x="{x:.1f}" y="{yt:.1f}" width="{iw:.1f}" height="4" '
            f'rx="2" fill="#ffffff" opacity=".30"/>'
            f'<text x="{x+iw/2:.1f}" y="{yt-14:.1f}" text-anchor="middle" '
            f'fill="#eaf5ff" font-size="17" font-weight="850">'
            f'{_esc(("+" if val>0 and kind not in("base","end") else "")+_fmt(val,unit))}</text>'
            f'<text x="{x+iw/2:.1f}" y="{h-mb+26:.1f}" text-anchor="middle" '
            f'fill="#9fb6cb" font-size="13.5" font-weight="600">{_esc(lab)}</text>')
        prev_top = Y(t)
    base_y = Y(start["value"])
    baseline = (f'<line x1="{ml}" y1="{base_y:.1f}" x2="{w-mr}" y2="{base_y:.1f}" '
                f'stroke="{C["blue"]}" stroke-opacity=".35" stroke-dasharray="2 7"/>')
    net = end["value"] - start["value"]
    net_s = ("+" if net >= 0 else "") + _fmt(net, unit)
    nx = ml + (w - ml - mr) * 0.5
    netcall = (
        f'<g transform="translate({nx:.0f},2)">'
        f'<rect x="-120" y="0" width="240" height="42" rx="13" '
        f'fill="rgba(55,240,164,.14)" stroke="{C["green"]}" '
        f'stroke-opacity=".55"/>'
        f'<text x="0" y="28" text-anchor="middle" fill="#9bffd9" '
        f'font-size="21" font-weight="900">{_esc(net_s)} net</text></g>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" '
            f'font-family="Inter,system-ui,sans-serif"><defs>{defs}</defs>'
            + "".join(grid) + baseline + "".join(out) + netcall + "</svg>")


# ---- grouped bars ------------------------------------------------------
def grouped_bars(payload: dict, *, w: int = 1010, h: int = 460) -> str:
    groups = payload.get("groups", [])
    series = payload.get("series", [])
    unit = payload.get("unit", "")
    if not groups or not series:
        return f'<svg viewBox="0 0 {w} {h}"></svg>'
    allv = [v for s in series for v in s["values"] if v is not None]
    lo = min(0, min(allv)); hi = max(allv)
    tks = _ticks(lo, hi * 1.06, 5)
    ylo, yhi = tks[0], tks[-1]
    ml, mr, mt, mb = 64, 16, 24, 52
    gn, sn = len(groups), len(series)
    gw = (w - ml - mr) / gn
    bw = gw * 0.62 / sn
    cols = [C[a] for a in ["cyan", "violet", "gold", "green"]]
    gbdefs = "".join(
        f'<linearGradient id="gb{i}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{c}" stop-opacity="1"/>'
        f'<stop offset="1" stop-color="{c}" stop-opacity=".58"/></linearGradient>'
        for i, c in enumerate(cols))

    def Y(v): return mt + (h - mt - mb) * (1 - (v - ylo) / (yhi - ylo))

    grid = []
    for t in tks:
        gy = Y(t)
        grid.append(
            f'<line x1="{ml}" y1="{gy:.1f}" x2="{w-mr}" y2="{gy:.1f}" '
            f'stroke="rgba(255,255,255,.06)"/>'
            f'<text x="{ml-12}" y="{gy+5:.1f}" text-anchor="end" '
            f'fill="#7f97ad" font-size="13">{_esc(_fmt(t,unit))}</text>')
    bars = []
    base = Y(0)
    for gi, g in enumerate(groups):
        gx = ml + gi * gw + gw * 0.19
        est = str(g).rstrip().endswith("E")
        for si, s in enumerate(series):
            v = s["values"][gi]
            if v is None:
                continue
            x = gx + si * bw
            y = Y(v)
            ci = si % len(cols)
            col = cols[ci]
            bw2 = bw * 0.86
            by = min(y, base)
            bh = max(3, abs(base - y))
            extra = (' opacity=".50" stroke="#ffffff" stroke-opacity=".5" '
                     'stroke-dasharray="5 4"') if est else ""
            bars.append(
                f'<rect x="{x:.1f}" y="{by:.1f}" width="{bw2:.1f}" '
                f'height="{bh:.1f}" rx="6" fill="url(#gb{ci})"{extra} '
                f'filter="drop-shadow(0 7px 16px {col}45)"/>'
                f'<rect x="{x:.1f}" y="{by:.1f}" width="{bw2:.1f}" height="3.5" '
                f'rx="2" fill="#ffffff" opacity=".30"/>'
                f'<text x="{x+bw2/2:.1f}" y="{by-12:.1f}" text-anchor="middle" '
                f'fill="#cfe0f0" font-size="14" font-weight="800">'
                f'{_esc(_fmt(v,unit))}</text>')
        bars.append(
            f'<text x="{ml+gi*gw+gw/2:.1f}" y="{h-mb+24:.1f}" '
            f'text-anchor="middle" fill="{"#7f97ad" if est else "#9fb6cb"}" '
            f'font-size="14" font-weight="{700 if est else 600}">'
            f'{_esc(g)}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" '
            f'font-family="Inter,system-ui,sans-serif"><defs>{gbdefs}</defs>'
            + "".join(grid) + "".join(bars) + "</svg>")


def series_legend(payload: dict, *, locale: str = "en") -> str:
    cols = [C[a] for a in ["cyan", "violet", "gold", "green"]]
    out = []
    for i, s in enumerate(payload.get("series", [])):
        nm = s.get("name", "")
        if isinstance(nm, dict):
            nm = nm.get(locale) or nm.get("en") or ""
        out.append(f'<div class="lg"><i style="background:{cols[i%4]}"></i>'
                   f'{_esc(nm)}</div>')
    return '<div class="legend">' + "".join(out) + "</div>"


def dispersion_strip(d: dict, *, locale: str = "en",
                     w: int = 1010, h: int = 210) -> str:
    lo, hi = float(d["min"]), float(d["max"])
    mean, cur = float(d["mean"]), float(d["current"])
    unit = d.get("unit", "$")
    ml, mr = 80, 80
    y = h * 0.50
    span = (hi - lo) or 1

    def X(v):
        return ml + (w - ml - mr) * (max(lo, min(hi, v)) - lo) / span

    def tick(v, lab, color):
        x = X(v)
        return (
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" '
            f'y2="{y+18:.1f}" stroke="{color}" stroke-width="3"/>'
            f'<text x="{x:.1f}" y="{y+50:.1f}" text-anchor="middle" '
            f'fill="#eaf5ff" font-size="23" font-weight="900">'
            f'{_esc(_fmt(v,unit))}</text>'
            f'<text x="{x:.1f}" y="{y+74:.1f}" text-anchor="middle" '
            f'fill="#90a8bd" font-size="13" font-weight="800" '
            f'letter-spacing="1">{_esc(lab)}</text>')

    lab = ({"min": "低", "mean": "均值", "max": "高", "cur": "现价"}
           if locale == "zh" else
           {"min": "LOW", "mean": "MEAN", "max": "HIGH", "cur": "NOW"})
    cx = X(cur)
    return f'''<svg viewBox="0 0 {w} {h}" width="100%"
  font-family="Inter,system-ui,sans-serif">
 <defs><linearGradient id="dsp" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{C['red']}"/><stop offset=".5"
  stop-color="{C['gold']}"/><stop offset="1" stop-color="{C['green']}"/>
 </linearGradient></defs>
 <rect x="{ml}" y="{y-7:.1f}" width="{w-ml-mr}" height="14" rx="7"
  fill="url(#dsp)" opacity=".85"/>
 {tick(lo,lab['min'],C['red'])}
 {tick(mean,lab['mean'],C['gold'])}
 {tick(hi,lab['max'],C['green'])}
 <line x1="{cx:.1f}" y1="{y-46:.1f}" x2="{cx:.1f}" y2="{y+14:.1f}"
  stroke="#eaf9ff" stroke-width="3"/>
 <circle cx="{cx:.1f}" cy="{y:.1f}" r="11" fill="#eaf9ff"
  stroke="{C['cyan']}" stroke-width="4"/>
 <g transform="translate({cx:.1f},{y-46:.1f})">
  <rect x="-66" y="-44" width="132" height="44" rx="12"
   fill="rgba(70,230,255,.16)" stroke="{C['cyan']}" stroke-opacity=".6"/>
  <text x="0" y="-15" text-anchor="middle" fill="#cdf6ff"
   font-size="20" font-weight="900">{_esc(_fmt(cur,unit))}</text>
 </g>
 <text x="{cx:.1f}" y="{y-58:.1f}" text-anchor="middle" fill="{C['cyan']}"
  font-size="12" font-weight="900" letter-spacing="1.5">{_esc(lab['cur'])}</text>
</svg>'''


# ---- score donut (gauge) ----------------------------------------------
def score_donut(payload: dict, *, locale: str = "en", w: int = 320) -> str:
    score = payload.get("score", 0)
    out_of = payload.get("out_of", 5)
    frac = max(0.0, min(1.0, score / out_of if out_of else 0))
    cx = cy = w / 2
    r = w * 0.40
    a0 = -90
    a1 = a0 + frac * 360
    ar0, ar1 = math.radians(a0), math.radians(a1)
    large = 1 if (a1 - a0) > 180 else 0
    x0, y0 = cx + r * math.cos(ar0), cy + r * math.sin(ar0)
    x1, y1 = cx + r * math.cos(ar1), cy + r * math.sin(ar1)
    cap = payload.get("caption", {})
    cap = _esc(cap.get(locale, cap.get("en", "")) if isinstance(cap, dict) else cap)
    ticks = ""
    try:
        steps = int(out_of)
    except Exception:
        steps = 5
    for k in range(steps + 1):
        ta = math.radians(-90 + 360 * k / max(1, steps))
        r1, r2 = r + 16, r + 24
        on = (k / max(1, steps)) <= frac + 1e-6
        tc = C["cyan"] if on else "rgba(255,255,255,.18)"
        ticks += (f'<line x1="{cx+r1*math.cos(ta):.1f}" y1="{cy+r1*math.sin(ta):.1f}" '
                  f'x2="{cx+r2*math.cos(ta):.1f}" y2="{cy+r2*math.sin(ta):.1f}" '
                  f'stroke="{tc}" stroke-width="3" stroke-linecap="round"/>')
    return f'''<svg viewBox="0 0 {w} {w}" width="{w}"
  font-family="Inter,system-ui,sans-serif">
 <defs>
  <linearGradient id="sd_g" x1="0" y1="0" x2="1" y2="1">
   <stop offset="0" stop-color="{C['cyan']}"/>
   <stop offset=".55" stop-color="{C['blue']}"/>
   <stop offset="1" stop-color="{C['violet']}"/>
  </linearGradient>
  <filter id="sd_glow" x="-40%" y="-40%" width="180%" height="180%">
   <feDropShadow dx="0" dy="0" stdDeviation="7"
     flood-color="{C['cyan']}" flood-opacity=".7"/>
  </filter>
 </defs>
 {ticks}
 <circle cx="{cx}" cy="{cy}" r="{r}" fill="none"
   stroke="rgba(255,255,255,.08)" stroke-width="22"/>
 <path d="M {x0:.2f} {y0:.2f} A {r:.2f} {r:.2f} 0 {large} 1 {x1:.2f} {y1:.2f}"
   fill="none" stroke="url(#sd_g)" stroke-width="22" stroke-linecap="round"
   filter="url(#sd_glow)"/>
 <circle cx="{x1:.2f}" cy="{y1:.2f}" r="9" fill="#eaf9ff"/>
 <text x="{cx}" y="{cy-2}" text-anchor="middle" fill="#eaf5ff"
   font-size="66" font-weight="900" letter-spacing="-2">{_esc(score)}<tspan
   font-size="28" fill="#90a8bd" font-weight="800">/{_esc(out_of)}</tspan></text>
 <text x="{cx}" y="{cy+38}" text-anchor="middle" fill="#90a8bd"
   font-size="14" font-weight="800" letter-spacing="1">{cap}</text>
</svg>'''


# ---- hero signature ----------------------------------------------------
def signature(kind: str, core: str, sub: str) -> str:
    core, sub = _esc(core), _esc(sub)
    if kind == "price_arc":
        pts = [(70, 360), (170, 300), (270, 330), (370, 220),
               (470, 250), (560, 120), (640, 150)]
        path = _smooth_path([(x, y) for x, y in pts])
        dots = "".join(
            f'<circle cx="{x}" cy="{y}" r="6" fill="{C["cyan"]}"/>'
            for x, y in pts[::2])
        return f'''<svg viewBox="0 0 700 460" width="100%"
  font-family="Inter,system-ui,sans-serif">
 <defs><linearGradient id="ha" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{C['cyan']}" stop-opacity=".35"/>
  <stop offset="1" stop-color="{C['cyan']}" stop-opacity="0"/></linearGradient></defs>
 <path d="{path} L 640 420 L 70 420 Z" fill="url(#ha)"/>
 <path d="{path}" fill="none" stroke="{C['cyan']}" stroke-width="4"
  stroke-linecap="round" filter="drop-shadow(0 8px 20px {C['cyan']}66)"/>
 {dots}
 <text x="350" y="232" text-anchor="middle" fill="#f4f9ff"
  font-size="48" font-weight="900" letter-spacing="-2">{core}</text>
 <text x="350" y="266" text-anchor="middle" fill="{C['cyan']}"
  font-size="15" font-weight="800" letter-spacing="3">{sub}</text>
</svg>'''
    # default: orbit / constellation
    ring_specs = [(180, C["cyan"], .28, ""),
                  (138, C["violet"], .42, 'stroke-dasharray="5 7"'),
                  (96, C["green"], .22, "")]
    rings = "".join(
        f'<circle cx="350" cy="230" r="{rr}" fill="none" '
        f'stroke="{c}" stroke-width="2" stroke-opacity="{op}" {dash}/>'
        for rr, c, op, dash in ring_specs)
    dots = "".join(
        f'<circle cx="{350+rr*math.cos(math.radians(a)):.1f}" '
        f'cy="{230+rr*math.sin(math.radians(a)):.1f}" r="9" fill="{c}" '
        f'filter="drop-shadow(0 0 12px {c})"/>'
        for rr, a, c in [(180, -38, C["cyan"]), (138, 130, C["violet"]),
                         (96, 250, C["green"]), (180, 210, C["gold"])])
    return f'''<svg viewBox="0 0 700 460" width="100%"
  font-family="Inter,system-ui,sans-serif">
 {rings}{dots}
 <circle cx="350" cy="230" r="78" fill="#0a1a2b"
  stroke="{C['cyan']}" stroke-opacity=".4" stroke-width="1.5"/>
 <text x="350" y="226" text-anchor="middle" fill="#f4f9ff"
  font-size="34" font-weight="900" letter-spacing="-1">{core}</text>
 <text x="350" y="256" text-anchor="middle" fill="{C['cyan']}"
  font-size="12" font-weight="800" letter-spacing="3">{sub}</text>
</svg>'''
