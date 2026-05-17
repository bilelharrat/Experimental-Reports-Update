"""Page-body renderers — one per page_type.

Each function returns the inner HTML for <main class="body">. The page
chrome (kicker, headline, dek, footer) is added by render.py. Pure
functions of (page, locale); no data fetching, no LLM.
"""
from __future__ import annotations

import html
from typing import Any

from . import charts


def _t(d: Any, loc: str) -> str:
    if isinstance(d, dict):
        return str(d.get(loc) or d.get("en") or "")
    return str(d or "")


def _e(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _quad(items: list[dict], loc: str) -> str:
    cells = []
    for m in items:
        tone = m.get("tone", "")
        val = _t(m["value"], loc)
        # numeric values stay big; word values get a smaller, tidy size
        small = "" if (len(val) <= 6 or any(c.isdigit() for c in val)) else " mv-sm"
        cells.append(
            f'<div class="metric {tone}">'
            f'<div class="ml">{_e(_t(m["label"], loc))}</div>'
            f'<div class="mv{small}">{_e(val)}</div>'
            f'<div class="mn">{_e(_t(m["note"], loc))}</div></div>')
    return f'<div class="quad">{"".join(cells)}</div>'


def _mx_card(c: dict, loc: str) -> str:
    w = int(c.get("weight", 50))
    lvl = "hi" if w >= 78 else "md" if w >= 58 else "lo"
    return (
        f'<div class="mx-card mx-{lvl}"><div class="mh">'
        f'<b>{_e(_t(c["title"], loc))}</b>'
        f'<span>{_e(_t(c["tag"], loc))}</span></div>'
        f'<p>{_e(_t(c["detail"], loc))}</p>'
        f'<div class="mx-foot"><div class="mx-bar"><i style="width:{w}%"></i></div>'
        f'<span class="mx-w">{w}</span></div></div>')


def _callout(page: dict, loc: str, danger: bool = False) -> str:
    c = page.get("callout")
    if not c:
        return ""
    cls = "callout danger" if danger else "callout"
    return f'<div class="{cls}">{_t(c, loc)}</div>'


def cover_verdict(page: dict, loc: str) -> str:
    v = page["viz"]
    sub = v.get(f"sub_{loc}") or v.get("sub_en", "")
    sig = charts.signature(v.get("signature", "orbit"), v.get("core", ""), sub)
    tags = "".join(f"<span>{_e(_t(t, loc))}</span>" for t in v.get("tags", []))
    thesis = "".join(f"<li>{_t(b, loc)}</li>" for b in v.get("thesis", []))
    hs = v.get("hero_stats", [])
    hs_html = ""
    if hs:
        cells = "".join(
            f'<div style="flex:1;text-align:center;padding:22px 14px;'
            f'border-radius:14px;background:rgba(255,255,255,.045);'
            f'border:1px solid rgba(255,255,255,.09)">'
            f'<div style="font-size:13px;font-weight:850;letter-spacing:.06em;'
            f'text-transform:uppercase;color:#8fa6bb">{_e(_t(s["k"], loc))}</div>'
            f'<div class="grad" style="font-size:38px;font-weight:900;'
            f'margin-top:12px;letter-spacing:-.03em">{_e(_t(s["v"], loc))}</div>'
            f'</div>' for s in hs)
        hs_html = ('<div style="display:flex;gap:16px;margin-top:30px">'
                   + cells + '</div>')
    return f'''
<div class="split hero">
  <div class="panel" style="display:flex;flex-direction:column;
    justify-content:center;gap:12px;padding:40px">
    <div style="max-height:300px;display:flex;align-items:center">{sig}</div>
    {hs_html}
  </div>
  <div class="panel" style="display:flex;flex-direction:column;justify-content:center;gap:4px">
    <div class="ml" style="font-size:14px;font-weight:900;letter-spacing:.16em;
      text-transform:uppercase;color:var(--cyan)">{_e(page.get("_posture_label",""))}</div>
    <div class="grad" style="font-size:46px;font-weight:850;
      letter-spacing:-.03em;margin-top:6px;line-height:1;width:fit-content">
      {_e(page.get("_posture",""))}</div>
    <div class="tags">{tags}</div>
    <div style="height:1px;background:rgba(255,255,255,.10);margin:26px 0 4px"></div>
    <ul class="list">{thesis}</ul>
  </div>
</div>
{_quad(v.get("quad", []), loc)}'''


def the_tape(page: dict, loc: str) -> str:
    v = page["viz"]
    return (f'<div class="chart"><div class="ct">'
            f'{"价格走势 · 美元" if loc=="zh" else "PRICE PATH · USD"}</div>'
            f'{charts.area_chart(v, accent=v.get("accent","cyan"), locale=loc)}</div>')


def why_it_moves(page: dict, loc: str) -> str:
    v = page["viz"]
    sl = [s for s in v.get("slices", []) if s.get("value")]
    cols = [charts.C.get(s.get("accent", "cyan"), charts.C["cyan"]) for s in sl]
    bullets = "".join(
        f'<li style="--bd:{cols[i % len(cols)] if cols else charts.C["cyan"]}">'
        f'{_t(b, loc)}</li>'
        for i, b in enumerate(v.get("bullets", [])))
    return f'''
<div class="split c2" style="grid-template-columns:.92fr 1.08fr;align-items:stretch">
  <div class="chart" style="margin-top:26px;display:flex;flex-direction:column;
    align-items:center;justify-content:center">
    <div class="ct" style="align-self:flex-start">
      {"营收结构" if loc=="zh" else "REVENUE MIX"}</div>
    {charts.donut(v, locale=loc, w=460)}
    <div style="width:100%;margin-top:28px">{charts.donut_legend(v, locale=loc)}</div>
  </div>
  <div class="panel" style="margin-top:26px;display:flex;flex-direction:column;
    justify-content:flex-start;gap:6px">
    <h3>{"为什么是这个板块" if loc=="zh" else "What actually moves the stock"}</h3>
    <div class="sub">{"按对股价的影响排序" if loc=="zh" else "ranked by impact on the stock"}</div>
    <ul class="list tied">{bullets}</ul>
  </div>
</div>'''


def revenue_bridge(page: dict, loc: str) -> str:
    v = page["viz"]
    return (f'<div class="chart"><div class="ct">'
            f'{"营收桥 · 十亿美元" if loc=="zh" else "REVENUE BRIDGE · $B"}</div>'
            f'{charts.waterfall(v)}</div>')


def unit_economics(page: dict, loc: str) -> str:
    v = page["viz"]
    return (f'<div class="chart"><div class="ct">'
            f'{"利润率轨迹" if loc=="zh" else "MARGIN TRAJECTORY"}</div>'
            f'{charts.grouped_bars(v)}{charts.series_legend(v, locale=loc)}</div>'
            f'{_callout(page, loc)}')


def moat_integration(page: dict, loc: str) -> str:
    v = page["viz"]
    pyr_n = len(v.get("pyramid", []))
    widths = [92, 76, 60, 46, 38]
    pyr = []
    for i, s in enumerate(v.get("pyramid", [])):
        w = widths[i] if i < len(widths) else 34
        pyr.append(
            f'<div class="pyr" style="width:{w}%">'
            f'<b>{_e(_t(s["label"], loc))}</b>'
            f'<span>{_e(_t(s["strength"], loc))}</span></div>')
    cards = "".join(
        _mx_card(c, loc)
        for c in sorted(v.get("cards", []),
                        key=lambda c: c.get("weight", 50), reverse=True))
    return f'''
<div class="split hero" style="grid-template-columns:.82fr 1.18fr">
  <div class="panel"><div class="pyramid">{"".join(reversed(pyr))}</div></div>
  <div class="matrix" style="grid-template-columns:1fr 1fr;margin-top:0">
    {cards}
  </div>
</div>
{_callout(page, loc)}'''


def supply_chain(page: dict, loc: str) -> str:
    v = page["viz"]
    cards = "".join(
        _mx_card(c, loc)
        for c in sorted(v.get("cards", []),
                        key=lambda c: c.get("weight", 50), reverse=True))
    return (f'<div class="matrix" style="grid-template-columns:1fr 1fr 1fr">'
            f'{cards}</div>')


def competitive_field(page: dict, loc: str) -> str:
    v = page["viz"]
    sc = v.get("score", {})
    cards = "".join(
        _mx_card(c, loc)
        for c in sorted(v.get("cards", []),
                        key=lambda c: c.get("weight", 50), reverse=True))
    lo_lbl, hi_lbl = (("共存", "替代") if loc == "zh" else ("coexist", "displace"))
    return f'''
<div class="split hero" style="grid-template-columns:1.2fr .8fr">
  <div class="matrix" style="grid-template-columns:1fr 1fr;margin-top:0">
    {cards}
  </div>
  <div class="panel" style="display:flex;flex-direction:column;
    align-items:center;justify-content:center">
    <div class="ct" style="align-self:flex-start;font-size:13px;font-weight:900;
      letter-spacing:.12em;text-transform:uppercase;color:#90b4cf;margin-bottom:10px">
      {"替代评分" if loc=="zh" else "DISPLACEMENT SCORE"}</div>
    {charts.score_donut(sc, locale=loc, w=360)}
    <div style="display:flex;justify-content:space-between;width:78%;
      margin-top:18px;font-size:13px;font-weight:800;color:#8fa6bb;
      text-transform:uppercase;letter-spacing:.08em">
      <span>{lo_lbl}</span><span>{hi_lbl}</span></div>
  </div>
</div>
{_callout(page, loc)}'''


def catalysts(page: dict, loc: str) -> str:
    v = page["viz"]
    nodes = []
    for i, n in enumerate(v.get("nodes", [])):
        imp = n.get("impact", "medium")
        imp_lbl = {"high": ("高" if loc == "zh" else "HIGH"),
                   "medium": ("中" if loc == "zh" else "MEDIUM"),
                   "low": ("低" if loc == "zh" else "LOW")}[imp]
        watch = n.get("watch")
        watch_html = (
            f'<div class="twatch"><span>{"关注" if loc=="zh" else "WATCH"}</span>'
            f'{_e(_t(watch, loc))}</div>') if watch else ""
        nodes.append(
            f'<div class="tlr">'
            f'<div class="tlw"><div class="tld">{_e(n["date"])}</div>'
            f'<span class="timp {imp}">{imp_lbl}</span></div>'
            f'<div class="tlb"><div class="tlt">{_e(_t(n["label"], loc))}</div>'
            f'<div class="tln">{_e(_t(n["note"], loc))}</div>'
            f'{watch_html}</div></div>')
    return f'<div class="tline">{"".join(nodes)}</div>'


def sentiment(page: dict, loc: str) -> str:
    v = page["viz"]
    bars = v.get("bars", {})
    disp = v.get("dispersion")
    disp_html = ""
    if disp:
        disp_html = (
            f'<div class="disp"><div class="dct">'
            f'{"分析师目标价区间" if loc=="zh" else "ANALYST TARGET-PRICE DISPERSION"}'
            f'</div>{charts.dispersion_strip(disp, locale=loc)}</div>')
    return f'''
{_quad(v.get("quad", []), loc)}
{disp_html}
<div class="chart"><div class="ct">
  {"卖方评级分布" if loc=="zh" else "SELL-SIDE RATING DISTRIBUTION"}</div>
  {charts.grouped_bars(bars, h=300)}
</div>'''


def scenario_math(page: dict, loc: str) -> str:
    v = page["viz"]
    out = []
    names = {"bear": ("空头" if loc == "zh" else "Bear"),
             "base": ("基准" if loc == "zh" else "Base"),
             "bull": ("多头" if loc == "zh" else "Bull")}
    for key in ("bear", "base", "bull"):
        s = v.get(key, {})
        rows = "".join(
            f"<dt>{_e(_t(r[0], loc))}</dt><dd>{_e(_t(r[1], loc))}</dd>"
            for r in s.get("rows", []))
        cap = "回报倍数 (MoIC)" if loc == "zh" else "MoIC vs entry"
        out.append(
            f'<div class="scard {key}"><h3>{names[key]}</h3>'
            f'<div class="moic">{_e(s.get("moic",""))}</div>'
            f'<div class="scap">{cap}</div>'
            f'<div class="sbar"><i style="height:{s.get("fill",40)}%"></i></div>'
            f'<dl>{rows}</dl></div>')
    return f'<div class="scen">{"".join(out)}</div>{_callout(page, loc)}'


def risk_gates(page: dict, loc: str) -> str:
    v = page["viz"]
    gates = []
    for i, g in enumerate(v.get("gates", []), 1):
        st = g.get("status") or {}
        lvl = st.get("level", "")
        pill = (f'<span class="gst {lvl}">{_e(_t(st.get("label",""), loc))}</span>'
                if st else "")
        metric = g.get("metric")
        msub = (f'<div class="gmet">{_e(_t(metric, loc))}</div>'
                if metric else "")
        gates.append(
            f'<div class="grow"><div class="gnum">{i}</div>'
            f'<div class="gmain"><div class="ghead">'
            f'<b>{_e(_t(g["title"], loc))}</b>{pill}</div>'
            f'<p>{_e(_t(g["body"], loc))}</p></div>'
            f'{msub}</div>')
    return f'<div class="glist">{"".join(gates)}</div>'


def sources(page: dict, loc: str) -> str:
    v = page["viz"]
    data = v.get("rows", [])
    counts: dict[str, int] = {}
    for r in data:
        t = _t(r.get("type", ""), loc) or ("数据" if loc == "zh" else "data")
        counts[t] = counts.get(t, 0) + 1
    mx = max(counts.values()) if counts else 1
    prov = "".join(
        f'<div class="spv"><div class="spk">{_e(k)}</div>'
        f'<div class="spn">{c}</div>'
        f'<div class="spbar"><i style="width:{int(c/mx*100)}%"></i></div></div>'
        for k, c in sorted(counts.items(), key=lambda kv: -kv[1])[:4])
    prov_html = f'<div class="srcprov">{prov}</div>' if prov else ""
    hdr = (("数据项", "来源", "类型", "时点") if loc == "zh"
           else ("FIGURE", "SOURCE", "TYPE", "AS OF"))
    rows = [f'<div class="sr sh"><span>{hdr[0]}</span><span>{hdr[1]}</span>'
            f'<span>{hdr[2]}</span><span>{hdr[3]}</span></div>']
    for r in data:
        typ = _t(r.get("type", ""), loc) or ("数据" if loc == "zh" else "data")
        rows.append(
            f'<div class="sr"><b>{_e(_t(r["label"], loc))}</b>'
            f'<span class="u"><span class="src-pill">{_e(r["url"])}</span></span>'
            f'<span class="src-type">{_e(typ)}</span>'
            f'<span class="d">{_e(r["date"])}</span></div>')
    return f'{prov_html}<div class="srctab">{"".join(rows)}</div>'


RENDERERS = {
    "cover_verdict": cover_verdict,
    "the_tape": the_tape,
    "why_it_moves": why_it_moves,
    "revenue_bridge": revenue_bridge,
    "unit_economics": unit_economics,
    "moat_integration": moat_integration,
    "supply_chain": supply_chain,
    "competitive_field": competitive_field,
    "catalysts": catalysts,
    "sentiment": sentiment,
    "scenario_math": scenario_math,
    "risk_gates": risk_gates,
    "sources": sources,
}


def render_body(page: dict, loc: str) -> str:
    fn = RENDERERS.get(page["page_type"])
    if not fn:
        return f'<div class="callout danger">Unknown page: {_e(page["page_type"])}</div>'
    return fn(page, loc)
