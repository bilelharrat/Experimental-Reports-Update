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
        cells.append(
            f'<div class="metric {tone}">'
            f'<div class="ml">{_e(_t(m["label"], loc))}</div>'
            f'<div class="mv">{_e(m["value"])}</div>'
            f'<div class="mn">{_e(_t(m["note"], loc))}</div></div>')
    return f'<div class="quad">{"".join(cells)}</div>'


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
    return f'''
<div class="split hero">
  <div class="panel" style="display:flex;align-items:center;justify-content:center;padding:34px">
    <div style="width:100%">{sig}</div>
  </div>
  <div class="panel" style="display:flex;flex-direction:column;justify-content:center;gap:4px">
    <div class="ml" style="font-size:14px;font-weight:900;letter-spacing:.16em;
      text-transform:uppercase;color:var(--cyan)">{_e(page.get("_posture_label",""))}</div>
    <div class="grad glow" style="font-size:64px;font-weight:900;
      letter-spacing:-.04em;margin-top:8px;line-height:1;width:fit-content">
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
            f'{charts.area_chart(v, accent=v.get("accent","cyan"))}</div>')


def why_it_moves(page: dict, loc: str) -> str:
    v = page["viz"]
    bullets = "".join(
        f"<li>{_t(b, loc)}</li>" for b in v.get("bullets", []))
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
    justify-content:center">
    <h3>{"为什么是这个板块" if loc=="zh" else "What actually moves the stock"}</h3>
    <ul class="list">{bullets}</ul>
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
            f'{charts.grouped_bars(v)}{charts.series_legend(v)}</div>'
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
    cards = []
    for c in v.get("cards", []):
        cards.append(
            f'<div class="mx-card"><div class="mh">'
            f'<b>{_e(_t(c["title"], loc))}</b>'
            f'<span>{_e(_t(c["tag"], loc))}</span></div>'
            f'<p>{_e(_t(c["detail"], loc))}</p>'
            f'<div class="mx-bar"><i style="width:{c.get("weight",50)}%"></i></div></div>')
    return f'''
<div class="split hero" style="grid-template-columns:.82fr 1.18fr">
  <div class="panel"><div class="pyramid">{"".join(reversed(pyr))}</div></div>
  <div class="matrix" style="grid-template-columns:1fr 1fr;margin-top:0">
    {"".join(cards)}
  </div>
</div>
{_callout(page, loc)}'''


def supply_chain(page: dict, loc: str) -> str:
    v = page["viz"]
    cards = []
    for c in v.get("cards", []):
        cards.append(
            f'<div class="mx-card"><div class="mh">'
            f'<b>{_e(_t(c["title"], loc))}</b>'
            f'<span>{_e(_t(c["tag"], loc))}</span></div>'
            f'<p>{_e(_t(c["detail"], loc))}</p>'
            f'<div class="mx-bar"><i style="width:{c.get("weight",50)}%"></i></div></div>')
    return (f'<div class="matrix" style="grid-template-columns:1fr 1fr 1fr">'
            f'{"".join(cards)}</div>')


def competitive_field(page: dict, loc: str) -> str:
    v = page["viz"]
    sc = v.get("score", {})
    cards = []
    for c in v.get("cards", []):
        cards.append(
            f'<div class="mx-card"><div class="mh">'
            f'<b>{_e(_t(c["title"], loc))}</b>'
            f'<span>{_e(_t(c["tag"], loc))}</span></div>'
            f'<p>{_e(_t(c["detail"], loc))}</p>'
            f'<div class="mx-bar"><i style="width:{c.get("weight",50)}%"></i></div></div>')
    return f'''
<div class="split hero" style="grid-template-columns:1.2fr .8fr">
  <div class="matrix" style="grid-template-columns:1fr 1fr;margin-top:0">
    {"".join(cards)}
  </div>
  <div class="panel" style="display:flex;flex-direction:column;
    align-items:center;justify-content:center">
    <div class="ct" style="align-self:flex-start;font-size:13px;font-weight:900;
      letter-spacing:.12em;text-transform:uppercase;color:#90b4cf;margin-bottom:10px">
      {"替代评分" if loc=="zh" else "DISPLACEMENT SCORE"}</div>
    {charts.score_donut(sc, locale=loc, w=360)}
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
        nodes.append(
            f'<div class="tnode"><div class="td">{_e(n["date"])}</div>'
            f'<div class="tmid"><div class="tt">{_e(_t(n["label"], loc))}</div>'
            f'<div><span class="timp {imp}">{imp_lbl}</span></div>'
            f'<div class="tnote">{_e(_t(n["note"], loc))}</div></div>'
            f'<div class="tbig">{i+1:02d}</div></div>')
    return f'<div class="timeline">{"".join(nodes)}</div>'


def sentiment(page: dict, loc: str) -> str:
    v = page["viz"]
    bars = v.get("bars", {})
    return f'''
{_quad(v.get("quad", []), loc)}
<div class="chart"><div class="ct">
  {"卖方评级分布" if loc=="zh" else "SELL-SIDE RATING DISTRIBUTION"}</div>
  {charts.grouped_bars(bars, h=420)}
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
            f"<dt>{_e(r[0])}</dt><dd>{_e(r[1])}</dd>" for r in s.get("rows", []))
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
        gates.append(
            f'<div class="gate"><div class="gn">{i}</div>'
            f'<b>{_e(_t(g["title"], loc))}</b>'
            f'<p>{_e(_t(g["body"], loc))}</p></div>')
    return f'<div class="gates">{"".join(gates)}</div>'


def sources(page: dict, loc: str) -> str:
    v = page["viz"]
    hdr = (("数据项", "来源", "时点") if loc == "zh"
           else ("FIGURE", "SOURCE", "AS OF"))
    rows = [f'<div class="sr"><span>{hdr[0]}</span><span>{hdr[1]}</span>'
            f'<span>{hdr[2]}</span></div>']
    for r in v.get("rows", []):
        rows.append(
            f'<div class="sr"><b>{_e(r["label"])}</b>'
            f'<span class="u">{_e(r["url"])}</span>'
            f'<span class="d">{_e(r["date"])}</span></div>')
    return f'<div class="srctab">{"".join(rows)}</div>'


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
