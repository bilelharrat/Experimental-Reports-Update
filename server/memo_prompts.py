"""Loader for the editorial memo prompts under the repo-root skills/memo/.

The files are the source of truth for the text the memo agents run: the
voice contract, the structure-v2 addendum, the risk-card contracts, the
Phase 2 pass focus texts and the rules every pass shares (passes.md), the
stage structure profiles (structures/), the company-type lenses (types/),
the Chinese style guide and glossary (zh_style.md) and the jurisdiction
research overlays (jurisdictions/). Chinese twins live
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
# The run-wide block of passes.md: everything under this heading up to the
# next `## ` heading reaches every Phase 2 pass (the notes above it are for
# maintainers and never reach an agent).
_PASS_RULES_HEADING = "## Rules for every pass"
_JURISDICTION_CODE_RE = re.compile(r"^[a-z]{2,8}$")


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


def parse_pass_rules(text: str) -> str:
    """The body of the `## Rules for every pass` block of passes.md (the
    heading itself dropped, surrounding blank lines trimmed), or "" when
    the file has no such block. The block ends at the next `## ` heading."""
    body: list[str] = []
    inside = False
    for line in strip_front_matter(text).splitlines():
        if line.strip() == _PASS_RULES_HEADING:
            inside = True
            continue
        if inside:
            if line.startswith("## "):
                break
            body.append(line)
    return "\n".join(body).strip("\n")


def load_pass_rules() -> str:
    """The run-wide rules every Phase 2 pass shares (passes.md), "" if the
    block is absent. Read at call time, so an edit lands on the next run."""
    return parse_pass_rules(
        (MEMO_SKILLS_DIR / "passes.md").read_text(encoding="utf-8")
    )


def load_jurisdiction(code: str | None) -> str:
    """The research overlay for one jurisdiction —
    skills/memo/jurisdictions/<code>.md, front matter removed — or "" when
    the code is empty, malformed or has no file (a run with no detected
    jurisdiction gets nothing, so its prompts stay byte-identical)."""
    key = str(code or "").strip().lower()
    if not _JURISDICTION_CODE_RE.match(key):
        return ""
    path = MEMO_SKILLS_DIR / "jurisdictions" / f"{key}.md"
    if not path.is_file():
        return ""
    return load_prompt(f"jurisdictions/{key}.md")
