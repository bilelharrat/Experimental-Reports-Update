"""Generate one text-free art PNG via `codex exec '$imagegen …'`.

Content-addressed cache (hash of the prompt) so re-runs and prompt
tweaks only pay for what changed.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data" / "report_visuals" / "_cache"


def _key(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:16]


def generate(prompt: str, out: Path, *, timeout: int = 600) -> tuple[bool, str]:
    """Write a PNG to `out`. Returns (ok, note). Uses the cache when the
    exact prompt was generated before."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{_key(prompt)}.png"
    if cached.exists() and cached.stat().st_size > 0:
        shutil.copyfile(cached, out)
        return True, "cache"

    codex = shutil.which("codex")
    if not codex:
        return False, "codex CLI not on PATH"
    instruction = (
        f"$imagegen {prompt} "
        f"Save it as {cached}"
    )
    try:
        proc = subprocess.run(
            [codex, "exec", instruction],
            capture_output=True, text=True, timeout=timeout, cwd=str(REPO),
        )
    except subprocess.TimeoutExpired:
        return False, f"codex timed out after {timeout}s"
    if not cached.exists() or cached.stat().st_size == 0:
        tail = (proc.stderr or proc.stdout or "")[-400:]
        return False, f"no image produced (exit {proc.returncode}): {tail}"
    shutil.copyfile(cached, out)
    return True, "generated"
