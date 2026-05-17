"""LLM vision critique — routed through the `claude` CLI (house rule:
no direct SDK). Feeds the rendered page PNGs + brief.json to Claude with
a strict rubric and parses a scored, actionable JSON verdict.

Writes ``<run>/eval/critique.json`` and a human ``critique.md``. The
Phase-5 gate is computed in Python from the parsed scores — the model's
own pass/fail boolean is never trusted.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DIMS = ["info_density", "hierarchy", "chart_truthfulness", "polish",
        "bilingual_parity", "punch", "whitespace_discipline"]

# Phase-5 exit bar
GATE_MEAN = 4.3
GATE_MIN_PAGE = 4.0

_PROMPT = """You are a ruthless senior information-design critic reviewing a \
bilingual (English + 简体中文) visual stock brief. Inspiration: dense, \
high-contrast WeChat investing infographics — every page must land one \
punchy idea with magazine-grade polish and zero dead space.

Use the Read tool to open EVERY image listed below (they are PNGs in the \
run directory). Also Read `brief.json` for ground-truth numbers.

English pages: {en}
Chinese sample pages: {zh}

Score each ENGLISH page 1-5 (5 = world-class) on these dimensions:
{dims}
- chart_truthfulness: chart magnitudes/labels must match brief.json exactly.
- whitespace_discipline: penalize large empty voids inside cards/panels.
- bilingual_parity: judged from the Chinese samples vs their EN twins \
(layout/quality must match; no clipped or tofu CJK).

Return ONLY a JSON object between the markers, no prose outside them:
<CRITIQUE>
{{"pages":[{{"n":1,"page_type":"...","scores":{{<dim>:int,...}},
"overall":number,"issues":["specific visible defect"],
"fixes":["concrete actionable change"]}}, ...],
"bilingual_notes":["..."],"top_fixes":["ranked highest-impact changes"]}}
</CRITIQUE>
Be specific and visual ("the donut legend wraps", "headline collides with \
accent bar"). Vague praise is useless."""


def _gather(run: Path) -> tuple[list[str], list[str]]:
    en = sorted((run / "pages" / "en").glob("page-*.png"))
    zh = sorted((run / "pages" / "zh").glob("page-*.png"))
    en_rel = [f"pages/en/{p.name}" for p in en]
    # sample: cover + a mid chart page + scenario-ish page
    idx = sorted({0, len(zh) // 3, max(0, len(zh) - 2)}) if zh else []
    zh_rel = [f"pages/zh/{zh[i].name}" for i in idx]
    return en_rel, zh_rel


def _aggregate(parsed: dict) -> dict:
    pages = parsed.get("pages", [])
    dim_means = {}
    for d in DIMS:
        vals = [pg["scores"].get(d) for pg in pages
                if isinstance(pg.get("scores"), dict) and pg["scores"].get(d) is not None]
        dim_means[d] = round(sum(vals) / len(vals), 2) if vals else None
    overalls = [pg.get("overall") for pg in pages if pg.get("overall") is not None]
    valid = [m for m in dim_means.values() if m is not None]
    mean = round(sum(valid) / len(valid), 2) if valid else 0.0
    min_pg = min(overalls) if overalls else 0.0
    gate = mean >= GATE_MEAN and min_pg >= GATE_MIN_PAGE
    return {"dimension_means": dim_means, "mean": mean,
            "min_page_overall": min_pg,
            "gate_pass": gate,
            "gate_thresholds": {"mean>=": GATE_MEAN, "min_page>=": GATE_MIN_PAGE}}


def critique_run(run: Path, timeout: int = 900) -> int:
    run = Path(run).resolve()
    claude = shutil.which("claude")
    if not claude:
        print("[critique] `claude` CLI not on PATH — skipping")
        return 0
    en, zh = _gather(run)
    if not en:
        print("[critique] no rendered PNGs — run render+rasterize first")
        return 1
    prompt = _PROMPT.format(
        en="\n".join(en), zh="\n".join(zh) or "(none)",
        dims="\n".join(f"- {d}" for d in DIMS))
    print(f"[critique] {run.parent.name}/{run.name} — "
          f"{len(en)} EN + {len(zh)} ZH pages → claude (this costs tokens)…")
    try:
        proc = subprocess.run(
            [claude, "-p", prompt, "--output-format", "json",
             "--no-session-persistence", "--add-dir", str(run)],
            capture_output=True, text=True, timeout=timeout, cwd=str(run))
    except subprocess.TimeoutExpired:
        print(f"[critique] timed out after {timeout}s")
        return 1
    if proc.returncode != 0:
        print(f"[critique] claude exited {proc.returncode}: "
              f"{(proc.stderr or '')[:400]}")
        return 1
    try:
        result = (json.loads(proc.stdout or "{}").get("result") or "").strip()
        cost = json.loads(proc.stdout or "{}").get("total_cost_usd")
    except json.JSONDecodeError:
        result, cost = proc.stdout or "", None
    m = re.search(r"<CRITIQUE>(.*?)</CRITIQUE>", result, re.S)
    raw = m.group(1).strip() if m else result
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        print("[critique] could not parse model JSON; raw saved")
        (run / "eval").mkdir(exist_ok=True)
        (run / "eval" / "critique.raw.txt").write_text(result, encoding="utf-8")
        return 1

    agg = _aggregate(parsed)
    parsed["_aggregate"] = agg
    parsed["_cost_usd"] = cost
    evd = run / "eval"
    evd.mkdir(exist_ok=True)
    (evd / "critique.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# Vision critique — {run.parent.name}/{run.name}", "",
             f"**Gate:** {'PASS ✅' if agg['gate_pass'] else 'FAIL ❌'}  ·  "
             f"mean {agg['mean']} (≥{GATE_MEAN})  ·  "
             f"weakest page {agg['min_page_overall']} (≥{GATE_MIN_PAGE})  ·  "
             f"cost ${cost}", "",
             "## Dimension means",
             *[f"- **{k}**: {v}" for k, v in agg["dimension_means"].items()],
             "", "## Top fixes",
             *[f"{i}. {x}" for i, x in enumerate(parsed.get("top_fixes", []), 1)],
             "", "## Per page"]
    for pg in parsed.get("pages", []):
        lines.append(f"### p{pg.get('n')} · {pg.get('page_type','')} "
                      f"(overall {pg.get('overall')})")
        for it in pg.get("issues", []):
            lines.append(f"- ✗ {it}")
        for fx in pg.get("fixes", []):
            lines.append(f"- → {fx}")
    if parsed.get("bilingual_notes"):
        lines += ["", "## Bilingual",
                  *[f"- {x}" for x in parsed["bilingual_notes"]]]
    (evd / "critique.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"[critique] gate={'PASS' if agg['gate_pass'] else 'FAIL'} "
          f"mean={agg['mean']} weakest={agg['min_page_overall']} "
          f"cost=${cost}")
    print(f"[critique] → {evd/'critique.md'}")
    return 0 if agg["gate_pass"] else 2


if __name__ == "__main__":
    sys.exit(critique_run(Path(sys.argv[1])))
