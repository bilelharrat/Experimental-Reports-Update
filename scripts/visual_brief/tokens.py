"""Design system for the Visual Stock Brief.

Single source of truth for page geometry, palette, type scale and the
global stylesheet. No data, no LLM — pure deterministic styling so the
render layer is golden-testable.
"""
from __future__ import annotations

# ---- page geometry -----------------------------------------------------
# Denser-than-A4 portrait so content fills the canvas (≈4:5).
# Rasterized at 3x → ~3720x4440.
PAGE_W = 1240
PAGE_H = 1480
PAGE_PAD = 76

# ---- palette -----------------------------------------------------------
PALETTE = {
    "bg": "#04070f",
    "ink": "#f4f9ff",
    "muted": "#9fb4cc",
    "faint": "#6c8099",
    "cyan": "#46e6ff",
    "blue": "#5a8bff",
    "violet": "#b878ff",
    "green": "#37f0a4",
    "gold": "#ffcb5c",
    "red": "#ff6f80",
}

ACCENTS = ["cyan", "blue", "violet", "green", "gold", "red"]


def hex_of(name: str) -> str:
    return PALETTE.get(name, name)


# ---- global stylesheet -------------------------------------------------
GLOBAL_CSS = f"""
:root {{
  --page-w:{PAGE_W}px; --page-h:{PAGE_H}px; --pad:{PAGE_PAD}px; --pad-x:30px;
  --bg:{PALETTE['bg']}; --ink:{PALETTE['ink']}; --muted:{PALETTE['muted']};
  --faint:{PALETTE['faint']}; --cyan:{PALETTE['cyan']}; --blue:{PALETTE['blue']};
  --violet:{PALETTE['violet']}; --green:{PALETTE['green']}; --gold:{PALETTE['gold']};
  --red:{PALETTE['red']};
  --panel:linear-gradient(180deg,rgba(255,255,255,.072),rgba(255,255,255,.028));
  --panel-strong:linear-gradient(180deg,rgba(255,255,255,.105),rgba(255,255,255,.04));
  --stroke:rgba(126,205,255,.20);
  --stroke-soft:rgba(255,255,255,.10);
  --radius:24px;
  --shadow:0 30px 80px rgba(0,0,0,.55);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:#02040a;color:var(--ink);
  font-family:"Inter","SF Pro Display",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;}}
html[lang="zh"] body{{
  font-family:"PingFang SC","Hiragino Sans GB","Noto Sans SC","Microsoft YaHei","Inter",sans-serif;
}}
/* full-bleed: every page spans the window edge-to-edge, no centered
   fixed-width column. Rasterized output stays exact because the Chrome
   window is forced to PAGE_W and the @page box is fixed (see print). */
.deck{{display:flex;flex-direction:column;align-items:stretch;gap:0;padding:0;}}

.page{{
  position:relative;overflow:hidden;
  display:flex;flex-direction:column;
  width:100%;min-height:var(--page-h);
  padding:var(--pad) var(--pad-x);
  background:
    radial-gradient(840px 620px at 88% 8%, rgba(70,230,255,.16), transparent 56%),
    radial-gradient(680px 560px at 4% 104%, rgba(55,240,164,.10), transparent 60%),
    radial-gradient(560px 520px at 100% 100%, rgba(184,120,255,.10), transparent 58%),
    linear-gradient(160deg,#0a1730 0%,#06101f 56%,#03101a 100%);
  border:0;border-bottom:1px solid rgba(96,190,255,.18);
  border-radius:0;
}}
.page::before{{content:"";position:absolute;inset:0;border:0;pointer-events:none;}}
.page-grid{{position:absolute;inset:0;pointer-events:none;opacity:.55;
  background-image:linear-gradient(rgba(255,255,255,.022) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.022) 1px,transparent 1px);
  background-size:54px 54px;
  -webkit-mask-image:linear-gradient(to bottom,transparent,#000 12%,#000 86%,transparent);}}
.page-aura{{position:absolute;width:420px;height:420px;border-radius:50%;right:-130px;top:120px;
  background:radial-gradient(circle at 60% 35%,rgba(255,255,255,.55),rgba(120,230,255,.16) 20%,
    rgba(90,139,255,.06) 42%,transparent 66%);filter:blur(4px);opacity:.40;pointer-events:none;}}

.row{{position:relative;z-index:2;display:flex;justify-content:space-between;align-items:center;
  border-bottom:1px solid rgba(126,210,255,.16);padding-bottom:16px;}}
.kicker{{display:flex;align-items:center;gap:12px;font-size:14px;font-weight:800;
  letter-spacing:.20em;text-transform:uppercase;color:#bfe6ff;}}
html[lang="zh"] .kicker{{letter-spacing:.10em;}}
.kicker .dot{{width:10px;height:10px;border-radius:50%;background:var(--cyan);
  box-shadow:0 0 18px var(--cyan);}}
.pnum{{font-size:14px;font-weight:800;color:#d6e8ff;background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:6px 13px;}}

h1.head{{position:relative;z-index:2;margin:38px 0 14px;font-size:60px;line-height:1.02;
  letter-spacing:-.035em;font-weight:850;max-width:1010px;}}
html[lang="zh"] h1.head{{font-size:54px;line-height:1.16;letter-spacing:-.005em;font-weight:800;}}
.dek{{position:relative;z-index:2;margin:0;color:#cddcec;font-size:21px;line-height:1.5;
  max-width:980px;font-weight:450;}}
html[lang="zh"] .dek{{font-size:20px;line-height:1.66;}}
.accent-bar{{position:relative;z-index:2;width:96px;height:5px;border-radius:999px;margin:24px 0 0;
  background:linear-gradient(90deg,var(--cyan),var(--violet));box-shadow:0 0 22px rgba(70,230,255,.5);}}

main.body{{position:relative;z-index:2;margin-top:34px;flex:1 1 auto;
  display:flex;flex-direction:column;justify-content:center;min-height:0;}}
main.body > *:first-child{{margin-top:0;}}
footer.foot{{position:relative;z-index:2;margin-top:auto;padding-top:18px;
  display:flex;justify-content:space-between;gap:16px;align-items:flex-end;
  color:#6f879f;font-size:12.5px;letter-spacing:.02em;
  border-top:1px solid rgba(255,255,255,.08);}}
footer.foot .src{{display:flex;flex-wrap:wrap;gap:6px 14px;max-width:760px;}}
footer.foot .src span{{color:#7f97ad;}}
footer.foot .src b{{color:#a9c2d8;font-weight:700;}}

.card{{background:var(--panel);border:1px solid var(--stroke-soft);
  border-radius:20px;box-shadow:inset 0 1px 0 rgba(255,255,255,.06);}}

/* metric quad */
.quad{{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-top:32px;}}
.metric{{padding:28px 24px;border-radius:18px;min-height:210px;display:flex;
  flex-direction:column;background:var(--panel-strong);
  border:1px solid var(--stroke-soft);box-shadow:inset 0 1px 0 rgba(255,255,255,.07);}}
.metric .ml{{font-size:13px;font-weight:900;letter-spacing:.13em;text-transform:uppercase;
  color:#90b4cf;}}
html[lang="zh"] .metric .ml{{letter-spacing:.04em;}}
.metric .mv{{font-size:46px;font-weight:900;letter-spacing:-.04em;margin-top:auto;
  line-height:1;}}
.metric .mn{{font-size:14.5px;color:#a7bbcf;line-height:1.36;margin-top:14px;}}
.metric.good{{border-color:rgba(55,240,164,.34);background:linear-gradient(180deg,rgba(55,240,164,.12),rgba(255,255,255,.03));}}
.metric.good .mv{{color:#9bffd9;}}
.metric.warn{{border-color:rgba(255,203,92,.36);background:linear-gradient(180deg,rgba(255,203,92,.11),rgba(255,255,255,.03));}}
.metric.warn .mv{{color:#ffe1a4;}}
.metric.bad{{border-color:rgba(255,111,128,.40);background:linear-gradient(180deg,rgba(255,111,128,.12),rgba(255,255,255,.03));}}
.metric.bad .mv{{color:#ffb3bc;}}

.tags{{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px;}}
.tags span{{font-size:13px;font-weight:750;color:#dff6ff;background:rgba(70,230,255,.12);
  border:1px solid rgba(70,230,255,.26);border-radius:999px;padding:8px 14px;}}

.callout{{display:flex;gap:18px;align-items:center;margin-top:24px;padding:22px 26px;
  border-radius:16px;font-size:17px;line-height:1.5;color:#f4f9ff;font-weight:550;
  border:1px solid rgba(255,203,92,.55);border-left:5px solid var(--gold);
  background:linear-gradient(90deg,rgba(255,203,92,.20),rgba(255,203,92,.05));}}
.callout.danger{{border-color:rgba(255,111,128,.55);border-left-color:var(--red);
  background:linear-gradient(90deg,rgba(255,111,128,.22),rgba(255,111,128,.05));}}
.callout b{{color:var(--gold);white-space:nowrap;font-weight:900;}}
.callout.danger b{{color:#ffb9c1;}}
.callout.danger b{{color:#ffb3bc;}}

.split{{display:grid;gap:24px;margin-top:30px;flex:1 1 auto;min-height:0;}}
.split.c2{{grid-template-columns:1fr 1fr;}}
.split.hero{{grid-template-columns:1.04fr .96fr;align-items:stretch;}}
.panel{{padding:30px;border-radius:20px;background:var(--panel);
  border:1px solid var(--stroke-soft);}}
.panel h3{{font-size:18px;font-weight:800;letter-spacing:.02em;color:#dff6ff;margin-bottom:6px;}}
.panel .sub{{font-size:13.5px;color:#90a7bd;margin-bottom:16px;}}

.list{{margin:16px 0 0;padding:0;list-style:none;}}
.list li{{position:relative;padding:18px 0 18px 28px;font-size:18.5px;line-height:1.5;
  color:#d4e2f0;border-top:1px solid rgba(255,255,255,.07);}}
.list li:first-child{{border-top:0;}}
.list li::before{{content:"";position:absolute;left:0;top:27px;width:10px;height:10px;
  border-radius:50%;background:var(--cyan);box-shadow:0 0 12px var(--cyan);}}
html[lang="zh"] .list li{{line-height:1.62;}}
.list li b{{color:#eaf5ff;}}

.evrow{{padding:16px 0;border-top:1px solid rgba(255,255,255,.08);}}
.evrow:first-of-type{{border-top:0;}}
.evrow b{{display:block;font-size:24px;letter-spacing:-.03em;}}
.evrow span{{display:block;color:#b3c5d5;font-size:14.5px;line-height:1.4;margin-top:6px;}}
.evrow.g b{{color:#9bffd9;}} .evrow.w b{{color:#ffe1a4;}} .evrow.r b{{color:#ffb3bc;}}

/* pyramid */
.pyramid{{display:flex;flex-direction:column;justify-content:center;gap:12px;height:100%;}}
.pyr{{margin:0 auto;border-radius:14px;padding:16px 18px;text-align:center;
  background:var(--panel-strong);border:1px solid var(--stroke-soft);}}
.pyr b{{display:block;font-size:21px;letter-spacing:-.02em;}}
.pyr span{{display:block;font-size:12px;font-weight:800;letter-spacing:.10em;text-transform:uppercase;
  color:#9fb6cb;margin-top:6px;}}

/* matrix */
.matrix{{display:grid;gap:18px;margin-top:28px;flex:1 1 auto;
  align-content:stretch;}}
.mx-card{{padding:30px;border-radius:16px;background:var(--panel);
  border:1px solid var(--stroke-soft);display:flex;flex-direction:column;
  justify-content:space-between;min-height:172px;}}
.mx-card .mh{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}}
.mx-card .mh b{{font-size:20px;letter-spacing:-.02em;}}
.mx-card .mh span{{font-size:11.5px;font-weight:850;text-transform:uppercase;letter-spacing:.08em;
  color:#cdeaff;border:1px solid rgba(126,210,255,.26);border-radius:999px;padding:6px 12px;
  white-space:nowrap;}}
.mx-card p{{flex:1 1 auto;display:flex;align-items:center;font-size:17px;
  line-height:1.5;color:#c4d5e6;margin:18px 0;font-weight:450;}}
html[lang="zh"] .mx-card p{{font-size:16.5px;line-height:1.7;}}
.mx-foot{{display:flex;align-items:center;gap:16px;}}
.mx-bar{{flex:1 1 auto;height:10px;border-radius:999px;
  background:rgba(255,255,255,.09);overflow:hidden;}}
.mx-bar i{{display:block;height:100%;border-radius:999px;}}
.mx-w{{font-size:17px;font-weight:900;color:#dfeeff;min-width:38px;text-align:right;
  letter-spacing:-.02em;}}
.mx-hi .mx-bar i{{background:linear-gradient(90deg,#ff8a96,var(--red));}}
.mx-md .mx-bar i{{background:linear-gradient(90deg,#ffd98a,var(--gold));}}
.mx-lo .mx-bar i{{background:linear-gradient(90deg,var(--cyan),var(--green));}}
.mx-hi .mh span{{color:#ffb9c1;border-color:rgba(255,111,128,.42);
  background:rgba(255,111,128,.10);}}
.mx-md .mh span{{color:#ffe1a4;border-color:rgba(255,203,92,.42);
  background:rgba(255,203,92,.10);}}
.mx-lo .mh span{{color:#9bffd9;border-color:rgba(55,240,164,.36);
  background:rgba(55,240,164,.09);}}
.mx-hi .mx-w{{color:#ffb9c1;}} .mx-md .mx-w{{color:#ffe1a4;}}
.mx-lo .mx-w{{color:#9bffd9;}}

/* timeline */
.timeline{{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-top:40px;
  position:relative;flex:1 1 auto;align-items:stretch;}}
.timeline::before{{content:"";position:absolute;left:8%;right:8%;top:58px;height:2px;
  background:linear-gradient(90deg,var(--cyan),var(--violet),var(--gold),var(--red));opacity:.5;}}
.tnode{{position:relative;overflow:hidden;padding:36px 30px;border-radius:18px;
  background:var(--panel);border:1px solid var(--stroke-soft);
  display:flex;flex-direction:column;}}
.tnode::before{{content:"";position:absolute;top:46px;right:30px;width:16px;height:16px;
  border-radius:50%;background:var(--cyan);box-shadow:0 0 20px var(--cyan);}}
.tnode .tbig{{position:absolute;right:18px;bottom:-30px;font-size:150px;font-weight:900;
  letter-spacing:-.06em;color:rgba(255,255,255,.045);line-height:1;pointer-events:none;}}
.tnode .td{{font-size:15px;font-weight:900;letter-spacing:.10em;text-transform:uppercase;color:#9ec0d6;}}
.tnode{{justify-content:flex-start;}}
.tnode .tmid{{position:relative;z-index:1;flex:1 1 auto;display:flex;
  flex-direction:column;justify-content:space-between;}}
.tnode .tt{{font-size:31px;font-weight:850;letter-spacing:-.02em;line-height:1.14;}}
.tnode .timp{{display:inline-block;margin-top:22px;font-size:13px;font-weight:800;
  text-transform:uppercase;letter-spacing:.06em;padding:7px 14px;border-radius:999px;}}
.timp.high{{color:#1a0a0d;background:var(--red);
  box-shadow:0 4px 14px rgba(255,111,128,.45);}}
.timp.medium{{color:#ffe1a4;background:transparent;
  border:1.5px solid rgba(255,203,92,.7);}}
.timp.low{{color:#9bffd9;background:rgba(55,240,164,.14);
  border:1.5px solid rgba(55,240,164,.4);}}
.tnode .td{{display:flex;align-items:center;gap:14px;}}
.tnode .tdi{{font-size:13px;font-weight:900;color:#06101f;background:var(--cyan);
  width:30px;height:30px;border-radius:9px;display:flex;align-items:center;
  justify-content:center;letter-spacing:-.02em;
  box-shadow:0 0 14px rgba(70,230,255,.5);}}
.tnode .twatch{{margin-top:20px;font-size:15px;line-height:1.45;color:#a7c6da;
  border-top:1px dashed rgba(255,255,255,.12);padding-top:16px;}}
.tnode .twatch span{{display:inline-block;font-size:11px;font-weight:900;
  letter-spacing:.12em;color:var(--cyan);margin-right:10px;}}
.list.tied li::before{{background:var(--bd);
  box-shadow:0 0 12px var(--bd);}}
.tnode .tnote{{font-size:18.5px;color:#b6c7d8;line-height:1.55;margin-top:24px;}}
html[lang="zh"] .tnode .tnote{{font-size:18px;line-height:1.7;}}

/* scenarios */
.scen{{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin-top:32px;
  align-items:stretch;}}
.scard{{position:relative;padding:32px 28px;border-radius:20px;min-height:520px;
  overflow:hidden;background:var(--panel-strong);border:1px solid var(--stroke-soft);
  display:flex;flex-direction:column;}}
.scard.bear{{border-color:rgba(255,111,128,.34);}}
.scard.base{{border-color:rgba(255,203,92,.36);}}
.scard.bull{{border-color:rgba(55,240,164,.36);}}
.scard h3{{font-size:24px;font-weight:850;letter-spacing:.02em;}}
.scard .moic{{font-size:64px;font-weight:900;letter-spacing:-.05em;margin-top:8px;
  line-height:1;}}
.scard.bear .moic{{color:#ffb3bc;}} .scard.base .moic{{color:#ffe1a4;}}
.scard.bull .moic{{color:#9bffd9;}}
.scard .scap{{font-size:14px;font-weight:700;color:#8fa6bb;margin-top:10px;
  text-transform:uppercase;letter-spacing:.10em;}}
.scard .sbar{{flex:1 1 auto;margin:30px 0;border-radius:16px;
  background:rgba(255,255,255,.045);overflow:hidden;display:flex;
  align-items:flex-end;min-height:90px;}}
.scard .sbar i{{display:block;width:100%;border-radius:16px;}}
.scard.bear .sbar i{{background:linear-gradient(180deg,#ff8a96,#ff6f80);}}
.scard.base .sbar i{{background:linear-gradient(180deg,#ffd98a,#ffcb5c);}}
.scard.bull .sbar i{{background:linear-gradient(180deg,#7df0c0,#37f0a4);}}
.scard dl{{display:grid;grid-template-columns:1fr 1fr;gap:22px 14px;}}
.scard dt{{font-size:12.5px;font-weight:900;text-transform:uppercase;letter-spacing:.07em;color:#90a8bd;}}
.scard dd{{font-size:22px;font-weight:850;color:#eef7ff;margin-top:5px;}}

/* gate grid */
.gates{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:30px;
  flex:1 1 auto;align-items:stretch;}}
.gate{{position:relative;padding:34px 34px 34px 84px;border-radius:18px;
  display:flex;flex-direction:column;justify-content:space-between;
  background:var(--panel);border:1px solid var(--stroke-soft);}}
.gate p{{flex:1 1 auto;display:flex;align-items:center;}}
.gate .gn{{position:absolute;left:22px;top:22px;width:34px;height:34px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;font-weight:900;font-size:16px;
  background:var(--cyan);color:#06101f;}}
.gate .ghead{{display:flex;align-items:center;justify-content:space-between;gap:14px;}}
.gate .ghead b{{font-size:21px;letter-spacing:-.02em;}}
.gate p{{margin-top:12px;font-size:15px;line-height:1.46;color:#b6c7d8;}}
.gate .gst{{font-size:11px;font-weight:900;text-transform:uppercase;
  letter-spacing:.07em;padding:6px 12px;border-radius:999px;white-space:nowrap;}}
.gst.ontrack{{color:#9bffd9;background:rgba(55,240,164,.14);
  border:1px solid rgba(55,240,164,.4);}}
.gst.monitor{{color:#ffe1a4;background:rgba(255,203,92,.13);
  border:1px solid rgba(255,203,92,.42);}}
.gst.notmet{{color:#ffb9c1;background:rgba(255,111,128,.14);
  border:1px solid rgba(255,111,128,.42);}}
.gate .gmetric{{margin-top:16px;font-size:13.5px;font-weight:750;color:#cfe0f0;
  background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.10);
  border-radius:10px;padding:12px 14px;}}

/* source table */
.srctab{{margin-top:30px;border-radius:18px;overflow:hidden;flex:1 1 auto;
  display:flex;flex-direction:column;justify-content:center;
  border:1px solid var(--stroke-soft);background:var(--panel);}}
.srctab .sr{{display:grid;grid-template-columns:1.3fr 1.7fr 150px 130px;gap:22px;
  padding:30px 34px;border-top:1px solid rgba(255,255,255,.07);font-size:16px;
  align-items:center;}}
.srctab .sr.sh{{border-top:0;background:rgba(255,255,255,.04);font-weight:850;
  text-transform:uppercase;letter-spacing:.10em;font-size:12.5px;color:#9fb6cb;}}
.srctab .sr b{{color:#eaf5ff;font-size:17px;font-weight:800;letter-spacing:-.01em;}}
.srctab .sr .u .src-pill{{display:inline-block;color:#9fe6ff;
  background:rgba(70,230,255,.10);border:1px solid rgba(70,230,255,.26);
  border-radius:999px;padding:8px 14px;font-size:13.5px;font-weight:700;
  word-break:break-all;}}
.srctab .sr.sh .src-pill,.srctab .sr.sh .u{{all:unset;}}
.srctab .sr .src-type{{font-size:12px;font-weight:850;text-transform:uppercase;
  letter-spacing:.06em;color:#cdeaff;}}
.srctab .sr .d{{color:#9fb6cb;font-weight:700;}}

/* svg chart frame */
.chart{{margin-top:28px;border-radius:20px;padding:32px 32px 26px;background:var(--panel);
  border:1px solid var(--stroke-soft);display:flex;flex-direction:column;
  flex:1 1 auto;justify-content:center;}}
.chart svg{{display:block;}}
.chart .ct{{font-size:13px;font-weight:900;letter-spacing:.12em;text-transform:uppercase;
  color:#90b4cf;margin-bottom:14px;}}
html[lang="zh"] .chart .ct{{letter-spacing:.04em;}}
.legend{{display:flex;flex-wrap:wrap;gap:10px 18px;margin-top:16px;}}
.legend .lg{{display:flex;align-items:center;gap:8px;font-size:13px;color:#bccddf;font-weight:650;}}
.legend .lg i{{width:13px;height:13px;border-radius:4px;}}

/* ---- dense timeline spine (catalysts) ---- */
.tline{{display:flex;flex-direction:column;flex:1 1 auto;position:relative;
  margin-top:32px;}}
.tline::before{{content:"";position:absolute;left:206px;top:18px;bottom:18px;width:3px;
  border-radius:3px;background:linear-gradient(180deg,var(--cyan),var(--violet),
  var(--gold),var(--red));opacity:.6;}}
.tlr{{display:grid;grid-template-columns:230px 1fr;gap:46px;flex:1 1 auto;
  padding:22px 0;border-top:1px solid rgba(255,255,255,.09);align-items:center;}}
.tlr:first-child{{border-top:0;}}
.tlw{{position:relative;text-align:right;padding-right:40px;}}
.tlw::after{{content:"";position:absolute;right:-10px;top:50%;
  transform:translateY(-50%);width:20px;height:20px;border-radius:50%;
  background:var(--cyan);box-shadow:0 0 0 7px rgba(70,230,255,.12),
  0 0 22px var(--cyan);}}
.tld{{font-size:24px;font-weight:900;letter-spacing:-.02em;color:#eaf5ff;}}
.tlw .timp{{display:inline-block;margin-top:14px;}}
.tlb .tlt{{font-size:32px;font-weight:850;letter-spacing:-.02em;line-height:1.12;}}
html[lang="zh"] .tlb .tlt{{font-size:30px;line-height:1.24;}}
.tlb .tln{{font-size:18.5px;line-height:1.5;color:#bbccde;margin-top:14px;}}
html[lang="zh"] .tlb .tln{{font-size:18px;line-height:1.7;}}
.tlb .twatch{{margin-top:16px;font-size:15px;line-height:1.45;color:#a7c6da;}}
.tlb .twatch span{{display:inline-block;font-size:11px;font-weight:900;
  letter-spacing:.12em;color:var(--cyan);margin-right:10px;}}

/* ---- dense gate rows (risk_gates) ---- */
.glist{{display:flex;flex-direction:column;flex:1 1 auto;gap:16px;margin-top:30px;}}
.grow{{display:grid;grid-template-columns:62px 1.35fr 1fr;gap:30px;
  align-items:center;flex:1 1 auto;padding:24px 30px;border-radius:16px;
  background:var(--panel);border:1px solid var(--stroke-soft);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 14px 38px rgba(0,0,0,.24);}}
.grow .gnum{{width:50px;height:50px;border-radius:14px;background:var(--cyan);
  color:#06101f;font-weight:900;font-size:21px;display:flex;align-items:center;
  justify-content:center;box-shadow:0 0 0 6px rgba(70,230,255,.12),
  0 6px 16px rgba(70,230,255,.4);}}
.grow .ghead{{display:flex;align-items:center;gap:14px;}}
.grow .ghead b{{font-size:22px;letter-spacing:-.02em;}}
.grow p{{margin-top:9px;font-size:16px;line-height:1.45;color:#b6c7d8;}}
.grow .gmet{{font-size:14.5px;font-weight:750;color:#dfeeff;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.10);
  border-radius:12px;padding:16px 18px;line-height:1.4;}}

/* ---- sources provenance summary ---- */
.srcprov{{display:flex;gap:18px;margin-top:30px;}}
.spv{{flex:1;padding:20px 22px;border-radius:14px;background:var(--panel);
  border:1px solid var(--stroke-soft);}}
.spv .spk{{font-size:12.5px;font-weight:900;letter-spacing:.08em;
  text-transform:uppercase;color:#90b4cf;}}
.spv .spn{{font-size:34px;font-weight:900;letter-spacing:-.03em;margin-top:8px;
  color:#eaf5ff;}}
.spv .spbar{{height:8px;border-radius:999px;background:rgba(255,255,255,.09);
  margin-top:14px;overflow:hidden;}}
.spv .spbar i{{display:block;height:100%;border-radius:999px;
  background:linear-gradient(90deg,var(--cyan),var(--green));}}

/* ---- target dispersion strip (sentiment) ---- */
.disp{{margin-top:28px;border-radius:20px;padding:34px 40px 46px;
  background:var(--panel);border:1px solid var(--stroke-soft);}}
.disp .dct{{font-size:13px;font-weight:900;letter-spacing:.12em;
  text-transform:uppercase;color:#90b4cf;margin-bottom:30px;}}

/* ---- pizzazz ---- */
.grad{{background:linear-gradient(102deg,var(--cyan) 0%,#8fd2ff 42%,var(--violet) 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;}}
.glow{{filter:drop-shadow(0 0 26px rgba(70,230,255,.42));}}
.page-mark{{position:absolute;right:-46px;bottom:-58px;z-index:0;
  pointer-events:none;font-size:210px;font-weight:900;letter-spacing:-.07em;
  line-height:1;color:rgba(255,255,255,.012);}}
.row{{position:relative;}}
.row::after{{content:"";position:absolute;left:0;bottom:-1px;width:148px;height:2px;
  border-radius:2px;background:linear-gradient(90deg,var(--cyan),transparent);
  box-shadow:0 0 14px rgba(70,230,255,.5);}}
.kicker .dot{{box-shadow:0 0 0 6px rgba(70,230,255,.10),0 0 18px var(--cyan);}}
.metric{{position:relative;overflow:hidden;}}
.metric::before{{content:"";position:absolute;left:0;right:0;top:0;height:3px;
  background:linear-gradient(90deg,var(--cyan),transparent);opacity:.65;}}
.metric.good::before{{background:linear-gradient(90deg,var(--green),transparent);}}
.metric.warn::before{{background:linear-gradient(90deg,var(--gold),transparent);}}
.metric.bad::before{{background:linear-gradient(90deg,var(--red),transparent);}}
.metric .mv{{text-shadow:0 0 24px rgba(70,230,255,.18);}}
.accent-bar{{background:linear-gradient(90deg,var(--cyan),var(--violet),var(--cyan));
  background-size:200% 100%;}}
.scard{{box-shadow:inset 0 1px 0 rgba(255,255,255,.07),0 24px 60px rgba(0,0,0,.30);}}
.scard .moic{{text-shadow:0 0 30px currentColor;}}
.chart,.panel,.mx-card,.tnode,.gate{{
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 18px 48px rgba(0,0,0,.26);}}
.tnode::after{{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;
  background:linear-gradient(180deg,var(--cyan),transparent);opacity:.5;}}
.gate .gn{{box-shadow:0 0 0 6px rgba(70,230,255,.12),0 6px 16px rgba(70,230,255,.4);}}

@page{{size:{PAGE_W}px {PAGE_H}px;margin:0;}}
@media print{{
  html,body{{background:#02040a;}}
  .deck{{padding:0;gap:0;}}
  .page{{border-radius:0;box-shadow:none;break-after:page;border:0;}}
  .page::before{{display:none;}}
}}
"""
