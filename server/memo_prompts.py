"""Loader for the editorial memo prompts under the repo-root skills/memo/.

The files are the source of truth for the text the memo agents run: the
voice contract, the structure-v2 addendum, the risk-card contracts, the
Phase 2 pass focus texts (passes.md), the stage structure profiles
(structures/) and the company-type lenses (types/). Chinese twins live
under skills/memo/zh/ for the founder's team to edit; the English files
are what the agents read (see skills/memo/README.md for the sync flow).

`load_prompt` returns the file text byte-for-byte (minus an optional YAML
front matter block) so the Python constants that used to hold these
literals — and the prompt-cache byte-identity they guard — are unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

MEMO_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills" / "memo"

_PASS_HEADER_RE = re.compile(r"^## pass: ([a-z0-9_]+)\s*$")


def strip_front_matter(text: str) -> str:
    """Drop a leading `---` YAML block (used by twins for the sync stamp)."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end < 0:
        return text
    return text[end + len("\n---\n") :]


def load_prompt(relpath: str) -> str:
    """The prompt text of skills/memo/<relpath>, front matter removed."""
    return strip_front_matter(
        (MEMO_SKILLS_DIR / relpath).read_text(encoding="utf-8")
    )


def parse_passes(text: str) -> list[dict[str, str]]:
    """Parse passes.md: `## pass: <id>` + a yaml fence (label, artifact) +
    the focus prose, in file order. Focus whitespace is normalized to
    single spaces (the prose is hand-wrapped)."""
    passes: list[dict[str, str]] = []
    current: dict[str, Any] | None = None
    in_fence = False
    for line in strip_front_matter(text).splitlines():
        header = _PASS_HEADER_RE.match(line)
        if header:
            current = {"pass_id": header.group(1), "focus_lines": []}
            passes.append(current)
            continue
        if current is None:
            continue
        if line.strip() == "```yaml" and "label" not in current:
            in_fence = True
            continue
        if in_fence:
            if line.strip() == "```":
                in_fence = False
                continue
            key, _, value = line.partition(":")
            current[key.strip()] = value.strip()
            continue
        current["focus_lines"].append(line)
    out: list[dict[str, str]] = []
    for item in passes:
        if "label" not in item or "artifact" not in item:
            raise ValueError(f"passes.md: pass {item['pass_id']} lacks label/artifact")
        focus = " ".join(" ".join(item["focus_lines"]).split())
        if not focus:
            raise ValueError(f"passes.md: pass {item['pass_id']} has no focus text")
        out.append(
            {
                "pass_id": item["pass_id"],
                "label": item["label"],
                "artifact_filename": item["artifact"],
                "focus": focus,
            }
        )
    return out


def load_passes(spec_factory: Callable[..., Any]) -> list[Any]:
    """The Phase 2 passes as `spec_factory(pass_id=, label=,
    artifact_filename=, focus=)` objects, in dispatch order."""
    text = (MEMO_SKILLS_DIR / "passes.md").read_text(encoding="utf-8")
    return [spec_factory(**fields) for fields in parse_passes(text)]
