#!/usr/bin/env python3
"""Keep the Chinese twins of the memo prompts in step with the English.

The agents read the English files under skills/memo/; the founder's team
edits the Chinese twins under skills/memo/zh/ (same relative paths). Each
twin's front matter carries `en_sha256`, the digest of the English file it
mirrors, so an English edit that was not ported to the twin (or a twin
that was never refreshed) fails `--check`. After porting a change, run
`--stamp` to record the new digest.

    uv run python scripts/skills_sync.py --check
    uv run python scripts/skills_sync.py --stamp

`check_twins()` is also what tests/test_skill_twins.py runs.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills" / "memo"
ZH = SKILLS / "zh"

# English files that have (or must have) a Chinese twin. The frozen late
# v1 profile and components.yaml are technical and are not twinned.
TWINNED = [
    "voice_contract.md",
    "structure_addendum.md",
    "risk_card_v2.md",
    "risk_card_compact.md",
    "passes.md",
    "structures/late_v2.md",
    "structures/late_compact.md",
    "structures/growth.md",
    "structures/early.md",
    # The Buffett-method memo skill (claude_runner loads the English file).
    "buffett.md",
    # The Chinese style guide and glossary every Chinese-writing prompt
    # carries (claude_runner._memo_zh_style loads the English file).
    "zh_style.md",
    # Jurisdiction overlays for the Phase 2 passes (memo_prompts.
    # load_jurisdiction; injected into the passes' shared context).
    "jurisdictions/cn.md",
]

_STAMP_RE = re.compile(r"^---\nen_sha256: ([0-9a-f]{64})\n---\n", re.S)
_SECTION_RE = re.compile(r"^## section: ([a-z0-9_]+)\s*$", re.M)
_PASS_RE = re.compile(r"^## pass: ([a-z0-9_]+)\s*$", re.M)
_HEADING_RE = re.compile(r"^(#{1,3}) ", re.M)


def twinned_files() -> list[str]:
    files = list(TWINNED)
    files.extend(
        f"types/{p.name}" for p in sorted((SKILLS / "types").glob("*.md"))
    )
    return files


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_stamp(twin: Path) -> tuple[str | None, str]:
    """(stamped digest or None, twin body without the stamp block)."""
    text = twin.read_text(encoding="utf-8")
    match = _STAMP_RE.match(text)
    if match is None:
        return None, text
    return match.group(1), text[match.end() :]


def _structure_ids(text: str, pattern: re.Pattern[str]) -> list[str]:
    return pattern.findall(text)


def check_twins() -> list[str]:
    problems: list[str] = []
    for rel in twinned_files():
        en_path = SKILLS / rel
        zh_path = ZH / rel
        if not en_path.exists():
            problems.append(f"{rel}: English file missing")
            continue
        if not zh_path.exists():
            problems.append(f"{rel}: Chinese twin missing (skills/memo/zh/{rel})")
            continue
        stamp, body = read_stamp(zh_path)
        if stamp is None:
            problems.append(f"{rel}: twin has no en_sha256 stamp — run --stamp after syncing")
        elif stamp != digest(en_path):
            problems.append(
                f"{rel}: English file changed since the twin was stamped — port "
                "the change into the twin (or the twin's edit into English), "
                "then run --stamp"
            )
        en_text = en_path.read_text(encoding="utf-8")
        for label, pattern in (("section", _SECTION_RE), ("pass", _PASS_RE)):
            en_ids = _structure_ids(en_text, pattern)
            zh_ids = _structure_ids(body, pattern)
            if en_ids != zh_ids:
                problems.append(
                    f"{rel}: `## {label}:` ids differ — en {en_ids} vs zh {zh_ids}"
                )
        en_fences = en_text.count("```")
        zh_fences = body.count("```")
        if en_fences != zh_fences:
            problems.append(
                f"{rel}: code-fence count differs (en {en_fences}, zh {zh_fences}) — "
                "yaml fences are copied verbatim"
            )
        en_headings = len(_HEADING_RE.findall(en_text))
        zh_headings = len(_HEADING_RE.findall(body))
        if en_headings != zh_headings:
            problems.append(
                f"{rel}: heading count differs (en {en_headings}, zh {zh_headings})"
            )
    return problems


def stamp_twins() -> int:
    stamped = 0
    for rel in twinned_files():
        en_path = SKILLS / rel
        zh_path = ZH / rel
        if not en_path.exists() or not zh_path.exists():
            continue
        _old, body = read_stamp(zh_path)
        zh_path.write_text(
            f"---\nen_sha256: {digest(en_path)}\n---\n{body}", encoding="utf-8"
        )
        stamped += 1
    return stamped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="verify twins are stamped and structurally aligned")
    group.add_argument("--stamp", action="store_true", help="re-stamp every twin with its English digest")
    args = parser.parse_args(argv)
    if args.stamp:
        print(f"stamped {stamp_twins()} twins")
        return 0
    problems = check_twins()
    for problem in problems:
        print(f"- {problem}")
    if problems:
        print(f"{len(problems)} problem(s)")
        return 1
    print(f"all {len(twinned_files())} twins in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
