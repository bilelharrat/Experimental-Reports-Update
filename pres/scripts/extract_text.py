#!/usr/bin/env python3
"""
OCR + layout extraction for a single slide image.

Calls the local `claude` CLI with the OCR overlay prompt and the image
attached via @-path. Parses the returned JSON (defensively — Claude
occasionally adds code fences even when told not to).

Usage:
    python extract_text.py /path/to/image.png
    python extract_text.py /path/to/image.png --out extracted.json

As a module:
    from extract_text import extract_text
    data = extract_text(Path("slide.png"))
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Default location of the OCR prompt (sibling `prompts/` dir).
DEFAULT_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "ocr_overlay.txt"

# Default timeout per image. OCR with full layout extraction can be slow.
DEFAULT_TIMEOUT_SEC = 600


class ClaudeCLIError(RuntimeError):
    """Raised when the claude CLI fails or returns unparseable output."""


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    text = text.strip()
    fence = re.match(r"^```(?:json|JSON)?\s*\n(.*)\n```\s*$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _extract_json_object(text: str) -> str:
    """
    If the model wrapped the JSON in prose, find the first balanced
    JSON object and return it. Falls back to the input unchanged.
    """
    text = _strip_code_fences(text)
    # Fast path: already pure JSON.
    if text.startswith("{"):
        return text

    # Slow path: find the first '{' and walk balanced braces, ignoring
    # braces inside strings.
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text


def _run_claude(prompt: str, timeout: int) -> str:
    """
    Invoke the claude CLI in print mode and return stdout as text.
    The image is referenced inline in the prompt via @-path.

    `--dangerously-skip-permissions` is required because in non-interactive
    print mode the CLI cannot prompt the user to approve a Read on the
    referenced image file, so without this flag the model just replies
    "I need permission to read this file."
    """
    try:
        proc = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ClaudeCLIError(
            "`claude` CLI not found on PATH. Install Claude Code "
            "(https://docs.claude.com/en/docs/claude-code) and ensure "
            "`claude` is on your PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCLIError(
            f"claude CLI timed out after {timeout}s during OCR extraction."
        ) from exc

    if proc.returncode != 0:
        raise ClaudeCLIError(
            f"claude CLI returned code {proc.returncode}.\n"
            f"stderr:\n{proc.stderr.strip()}"
        )
    return proc.stdout


def _validate_ocr_schema(data: dict, image_path: Path) -> None:
    """Light schema validation. Raises ClaudeCLIError on missing required fields."""
    required_top = ("image_width", "image_height", "elements")
    missing = [k for k in required_top if k not in data]
    if missing:
        raise ClaudeCLIError(
            f"OCR JSON for {image_path.name} is missing required fields: {missing}"
        )
    if not isinstance(data["elements"], list):
        raise ClaudeCLIError(
            f"OCR JSON for {image_path.name} has non-list 'elements'."
        )

    # Per-element sanity check. Don't reject — just ensure at minimum
    # an id and some text we can later translate.
    for idx, el in enumerate(data["elements"]):
        if "id" not in el:
            el["id"] = f"text_{idx + 1:03d}"
        if "text_logical" not in el and "text_visible" in el:
            el["text_logical"] = el["text_visible"]


def extract_text(
    image_path: Path,
    prompt_path: Path = DEFAULT_PROMPT_PATH,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> dict:
    """
    Run OCR + layout extraction on one image. Returns parsed JSON dict.

    Raises ClaudeCLIError on any failure.
    """
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not prompt_path.is_file():
        raise FileNotFoundError(f"OCR prompt not found: {prompt_path}")

    prompt_text = prompt_path.read_text(encoding="utf-8")

    # Embed the image with @-syntax. Absolute path makes it robust to
    # whatever cwd `claude` resolves to.
    full_prompt = f"{prompt_text}\n\nIMAGE TO ANALYZE: @{image_path}\n"

    raw = _run_claude(full_prompt, timeout=timeout)
    cleaned = _extract_json_object(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Save raw output next to the image for debugging.
        debug_path = image_path.with_suffix(image_path.suffix + ".ocr_raw.txt")
        try:
            debug_path.write_text(raw, encoding="utf-8")
        except OSError:
            pass
        raise ClaudeCLIError(
            f"Failed to parse OCR JSON for {image_path.name}: {exc}. "
            f"Raw output saved to {debug_path}."
        ) from exc

    _validate_ocr_schema(data, image_path)
    return data


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Extract slide text + layout via Claude CLI.")
    parser.add_argument("image", type=Path, help="Path to the image to analyze.")
    parser.add_argument("--out", type=Path, default=None, help="Where to write JSON. Default: stdout.")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT_PATH, help="Override OCR prompt path.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC, help="Claude CLI timeout in seconds.")
    args = parser.parse_args()

    try:
        data = extract_text(args.image, prompt_path=args.prompt, timeout=args.timeout)
    except (ClaudeCLIError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
