"""One-off cleanup: remove Zainar-specific template bleed from memo editor states.

Earlier revisions of ``memo_editor_store._fallback_thesis_cards`` /
``_fallback_risk_cards`` hardcoded Zainar's positioning claims (sub-meter
location, GPS-alternative, carrier adoption) as the default card text, so
every company's editor state was seeded with another company's assets.

This script rewrites ONLY exact matches of those template strings in each
``data/memo_editor/<company>/state.yaml`` with the neutral replacements the
store now generates. Card ids, ranks, user edits, and version history are
left untouched. ``zainar-inc`` is skipped — the text genuinely describes
Zainar there.

Run:  uv run python scripts/fix_memo_editor_template_bleed.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EDITOR_ROOT = ROOT / "data" / "memo_editor"
COMPANIES_YAML = ROOT / "data" / "companies.yaml"
SKIP_COMPANIES = {"zainar-inc"}

OLD_THESIS_TITLE = "Existing networks can become a software positioning layer."
OLD_DIFFERENTIATOR = (
    "The platform claims sub-meter location using existing network infrastructure."
)
OLD_BENEFIT = "The core benefit is GPS-alternative location where GPS fails."
OLD_METRICS_TITLE = "Launch-scale metrics create a late-stage underwriting frame."
OLD_RISK_TITLE = "Standards or carrier adoption could compress moat durability."
OLD_RISK_BULLET = (
    "Patent and standards diligence should test whether the claimed moat "
    "survives platform adoption."
)

NEW_BENEFIT = (
    "The core customer benefit has not been independently verified; "
    "source it before export."
)
NEW_METRICS_TITLE = "Disclosed metrics frame the underwriting baseline."
NEW_RISK_TITLE = "Competitive or platform shifts could compress moat durability."
NEW_RISK_BULLET = (
    "Patent, standards, and competitive diligence should test whether the "
    "claimed moat survives platform-level adoption by larger players."
)
FALLBACK_DIFFERENTIATOR = (
    "Differentiation claims are not yet documented; treat this thesis as "
    "pending diligence."
)


def _company_records() -> dict[str, dict]:
    try:
        data = yaml.safe_load(COMPANIES_YAML.read_text(encoding="utf-8"))
    except Exception:
        return {}
    records = data.get("companies") if isinstance(data, dict) else data
    if not isinstance(records, list):
        return {}
    return {
        str(item.get("id")): item
        for item in records
        if isinstance(item, dict) and item.get("id")
    }


def _replace_in_state(state: dict, company: dict) -> list[str]:
    company_label = (
        str(company.get("name") or "").strip()
        or str(state.get("company_name") or "").strip()
        or "The company"
    )
    description = " ".join(str(company.get("description") or "").split()).strip()
    replacements = {
        OLD_THESIS_TITLE: (
            f"{company_label} claims a differentiated technology position."
        ),
        OLD_DIFFERENTIATOR: description or FALLBACK_DIFFERENTIATOR,
        OLD_BENEFIT: NEW_BENEFIT,
        OLD_METRICS_TITLE: NEW_METRICS_TITLE,
        OLD_RISK_TITLE: NEW_RISK_TITLE,
        OLD_RISK_BULLET: NEW_RISK_BULLET,
    }
    changes: list[str] = []

    def rewrite(value: str) -> str | None:
        # Exact matches and embedded occurrences (e.g. "Discuss: <old title>")
        # both get replaced; ids/slugs are never strings equal to or
        # containing the full old sentences, so they stay stable.
        out = value
        for old, new in replacements.items():
            if old in out:
                out = out.replace(old, new)
        return out if out != value else None

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str):
                    replaced = rewrite(value)
                    if replaced is not None:
                        node[key] = replaced
                        changes.append(f"{path}.{key}: {value[:60]!r}")
                else:
                    walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                if isinstance(value, str):
                    replaced = rewrite(value)
                    if replaced is not None:
                        node[index] = replaced
                        changes.append(f"{path}[{index}]: {value[:60]!r}")
                else:
                    walk(value, f"{path}[{index}]")

    walk(state, "state")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = _company_records()
    total = 0
    for state_path in sorted(EDITOR_ROOT.glob("*/state.yaml")):
        company_id = state_path.parent.name
        if company_id in SKIP_COMPANIES:
            print(f"skip {company_id} (template text is genuinely this company's)")
            continue
        try:
            state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR reading {state_path}: {exc}")
            continue
        if not isinstance(state, dict):
            continue
        changes = _replace_in_state(state, records.get(company_id) or {})
        if not changes:
            print(f"clean {company_id}")
            continue
        total += len(changes)
        print(f"fix   {company_id}: {len(changes)} replacement(s)")
        for change in changes:
            print(f"      - {change}")
        if not args.dry_run:
            with state_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(state, f, sort_keys=False, allow_unicode=True)
    print(f"{'DRY RUN — ' if args.dry_run else ''}{total} replacement(s) total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
