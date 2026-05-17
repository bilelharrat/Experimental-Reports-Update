"""Deterministic visual linter — high error detection, zero LLM.

Two layers:

1. **Model checks** (pure Python, fast): bilingual parity, chart-math
   reconciliation, headline length budgets, and *chart truthfulness*
   (every value in brief.json must appear, correctly formatted, in the
   rendered HTML — catches a renderer drifting from its data).

2. **Rendered-DOM audit** (headless Chrome): an in-page script measures
   the live DOM and reports content bleeding off the fixed A4 canvas,
   clipped/overflowing text, collapsed (tofu) text, exact page
   geometry, the U+FFFD replacement char, and large vertical voids.

Findings have severity ``error`` (gate-blocking) or ``warn``. Writes
``<run>/eval/lint.json`` and prints a table. Exit code 1 if any error.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import charts, render, tokens
from .rasterize import _find_chrome

TOL = 0.5  # $B reconciliation tolerance


# ---- model-level checks ------------------------------------------------
def _walk_parity(node: Any, path: str, out: list[dict]) -> None:
    """Any dict carrying an 'en' must carry a non-empty 'zh'."""
    if isinstance(node, dict):
        if "en" in node and set(node) <= {"en", "zh"}:
            if not str(node.get("zh") or "").strip():
                out.append({"severity": "error", "code": "bilingual_parity",
                            "msg": f"missing/empty zh at {path}"})
            return
        for k, v in node.items():
            _walk_parity(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_parity(v, f"{path}[{i}]", out)


def _model_checks(brief: dict) -> list[dict]:
    f: list[dict] = []
    req = ("kicker", "headline", "dek", "footer", "viz")
    for i, p in enumerate(brief.get("pages", []), 1):
        tag = f"p{i:02d}/{p.get('page_type','?')}"
        for k in req:
            if k not in p:
                f.append({"severity": "error", "code": "missing_field",
                          "page": i, "msg": f"{tag}: missing '{k}'"})
        _walk_parity({k: p.get(k) for k in ("kicker", "headline", "dek", "footer")},
                     tag, f)
        for it in f:
            it.setdefault("page", i)
        hl = p.get("headline", {})
        if len(str(hl.get("en", ""))) > 96:
            f.append({"severity": "warn", "code": "headline_long",
                      "page": i, "msg": f"{tag}: EN headline >96 chars (wrap risk)"})
        if len(str(hl.get("zh", ""))) > 46:
            f.append({"severity": "warn", "code": "headline_long",
                      "page": i, "msg": f"{tag}: ZH headline >46 chars (wrap risk)"})
        v = p.get("viz", {})
        kind = v.get("kind")
        if kind == "waterfall":
            s = v.get("start", {}).get("value", 0)
            e = v.get("end", {}).get("value", 0)
            cum = s + sum(st.get("value", 0) for st in v.get("steps", []))
            if abs(cum - e) > TOL:
                f.append({"severity": "error", "code": "waterfall_reconcile",
                          "page": i,
                          "msg": f"{tag}: start+steps={cum:.2f} ≠ end={e:.2f}"})
        if kind == "donut":
            sl = [x for x in v.get("slices", []) if x.get("value")]
            if not sl or sum(x["value"] for x in sl) <= 0:
                f.append({"severity": "error", "code": "donut_empty",
                          "page": i, "msg": f"{tag}: donut has no positive slices"})
        if kind == "scenario_set":
            for key in ("bear", "base", "bull"):
                fl = v.get(key, {}).get("fill")
                if fl is None or not (0 <= fl <= 100):
                    f.append({"severity": "warn", "code": "scenario_fill",
                              "page": i, "msg": f"{tag}: {key}.fill out of [0,100]"})
    return f


def _truthfulness(brief: dict) -> list[dict]:
    """Every JSON number must appear, correctly formatted, in the HTML."""
    f: list[dict] = []
    for loc in ("en", "zh"):
        docs = render.build_page_docs(brief, loc)
        for i, (p, html) in enumerate(zip(brief["pages"], docs), 1):
            tag = f"p{i:02d}/{p.get('page_type','?')}[{loc}]"
            v = p.get("viz", {})
            expect: list[str] = []
            if v.get("kind") == "donut":
                u = v.get("unit", "$B")
                tot = sum(s["value"] for s in v["slices"] if s.get("value"))
                expect.append(charts._fmt(tot, u))
                expect += [charts._fmt(s["value"], u)
                           for s in v["slices"] if s.get("value")]
            elif v.get("kind") == "waterfall":
                u = v.get("unit", "$")
                expect += [charts._fmt(v["start"]["value"], u),
                           charts._fmt(v["end"]["value"], u)]
            elif v.get("kind") == "hero":
                expect += [m["value"] for m in v.get("quad", [])]
            for s in expect:
                if s and s not in html:
                    f.append({"severity": "error", "code": "chart_untruthful",
                              "page": i,
                              "msg": f"{tag}: rendered HTML missing value '{s}'"})
    return f


# ---- rendered-DOM audit (headless Chrome) ------------------------------
_AUDIT_JS = r"""
(function(){
 try{
  var pg=document.querySelector('.page');
  var pr=pg.getBoundingClientRect();
  var EXP_W=%d, EXP_H=%d, F=[];
  if(Math.abs(pg.offsetWidth-EXP_W)>1||Math.abs(pg.offsetHeight-EXP_H)>1)
    F.push({severity:'error',code:'geometry',
      msg:'page '+pg.offsetWidth+'x'+pg.offsetHeight+' != '+EXP_W+'x'+EXP_H});
  var skip=/(page-mark|page-aura|page-grid|accent-bar|tbig)/;
  var els=pg.querySelectorAll('*');
  for(var i=0;i<els.length;i++){
    var e=els[i];
    if(e.closest('svg'))continue;
    if(skip.test(e.className||''))continue;
    var cs=getComputedStyle(e), r=e.getBoundingClientRect();
    if(cs.position==='absolute'&&skip.test(e.className||''))continue;
    if(r.width<0.5&&r.height<0.5)continue;
    // bleed off the fixed canvas
    if(r.right>pr.right+1.5||r.bottom>pr.bottom+1.5||
       r.left<pr.left-1.5||r.top<pr.top-1.5){
      F.push({severity:'error',code:'bleed',
        msg:(e.className||e.tagName)+' off-canvas '+
        Math.round(Math.max(r.right-pr.right,r.bottom-pr.bottom,
        pr.left-r.left,pr.top-r.top))+'px'});
    }
    // clipped text — only on text leaves (containers overflow for
    // decorative reasons; a genuinely clipped string clips its own leaf)
    if(e.children.length===0&&cs.overflow!=='visible'&&
       (e.scrollWidth-e.clientWidth>2||e.scrollHeight-e.clientHeight>2)&&
       (e.textContent||'').trim()){
      F.push({severity:'error',code:'clip',
        msg:(e.className||e.tagName)+' text clipped '+
        Math.max(e.scrollWidth-e.clientWidth,e.scrollHeight-e.clientHeight)+'px'});
    }
    // collapsed text (tofu / zero box with content)
    var t=(e.childNodes.length===1&&e.firstChild.nodeType===3)?
      (e.textContent||'').trim():'';
    if(t&&(r.width<4||r.height<7))
      F.push({severity:'error',code:'collapsed',
        msg:(e.className||e.tagName)+' text box '+
        Math.round(r.width)+'x'+Math.round(r.height)});
  }
  // vertical void
  var body=pg.querySelector('main.body'),ft=pg.querySelector('footer.foot');
  if(body&&ft){
    var kids=body.children, lb=kids.length?
      kids[kids.length-1].getBoundingClientRect().bottom:body.getBoundingClientRect().top;
    var gap=ft.getBoundingClientRect().top-lb;
    if(gap>300)F.push({severity:'warn',code:'void',
      msg:'vertical void '+Math.round(gap)+'px between body and footer'});
  }
  if((document.body.innerText||'').indexOf('�')>=0)
    F.push({severity:'error',code:'fffd',msg:'U+FFFD replacement char present'});
  document.title='AUDIT::'+JSON.stringify(F)+'::END';
 }catch(err){document.title='AUDIT::[{"severity":"error","code":"audit_crash","msg":"'+err+'"}]::END';}
})();
"""


def _dom_audit(brief: dict, chrome: str, scratch: Path) -> list[dict]:
    f: list[dict] = []
    js = _AUDIT_JS % (tokens.PAGE_W, tokens.PAGE_H)
    for loc in ("en", "zh"):
        docs = render.build_page_docs(brief, loc)
        for i, doc in enumerate(docs, 1):
            inj = doc.replace("</body>", f"<script>{js}</script></body>")
            fp = scratch / f"{loc}-p{i:02d}.html"
            fp.write_text(inj, encoding="utf-8")
            try:
                r = subprocess.run(
                    [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                     f"--window-size={tokens.PAGE_W},{tokens.PAGE_H}",
                     "--virtual-time-budget=4000", "--dump-dom", f"file://{fp}"],
                    capture_output=True, text=True, timeout=60)
                m = re.search(r"AUDIT::(.*?)::END", r.stdout, re.S)
                items = json.loads(m.group(1)) if m else [
                    {"severity": "error", "code": "audit_missing",
                     "msg": "no audit payload (page failed to run)"}]
            except Exception as exc:  # noqa: BLE001
                items = [{"severity": "error", "code": "audit_error",
                          "msg": f"{type(exc).__name__}: {exc}"}]
            for it in items:
                it["page"] = i
                it["locale"] = loc
                f.append(it)
    return f


# ---- driver ------------------------------------------------------------
def lint_run(run: Path) -> int:
    run = Path(run).resolve()
    brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
    findings = _model_checks(brief) + _truthfulness(brief)
    chrome = _find_chrome()
    if chrome:
        scratch = run / ".lint"
        scratch.mkdir(exist_ok=True)
        findings += _dom_audit(brief, chrome, scratch)
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)
    else:
        findings.append({"severity": "warn", "code": "no_chrome",
                         "msg": "Chrome not found — DOM audit skipped"})

    errs = [x for x in findings if x["severity"] == "error"]
    warns = [x for x in findings if x["severity"] == "warn"]
    out = {"run": str(run), "summary": {"errors": len(errs), "warns": len(warns)},
           "findings": findings}
    evd = run / "eval"
    evd.mkdir(exist_ok=True)
    (evd / "lint.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[lint] {run.parent.name}/{run.name} — "
          f"{len(errs)} errors, {len(warns)} warns")
    for x in errs[:40]:
        loc = f" [{x.get('locale')}]" if x.get("locale") else ""
        print(f"  ✗ p{x.get('page','?'):>2}{loc} {x['code']}: {x['msg']}")
    for x in warns[:20]:
        loc = f" [{x.get('locale')}]" if x.get("locale") else ""
        print(f"  ⚠ p{x.get('page','?'):>2}{loc} {x['code']}: {x['msg']}")
    print(f"[lint] → {evd/'lint.json'}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(lint_run(Path(sys.argv[1])))
