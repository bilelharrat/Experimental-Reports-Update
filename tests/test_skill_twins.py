"""Every editorial memo prompt has a Chinese twin under skills/memo/zh/
that is stamped with the digest of the English file it mirrors and keeps
the same section/pass ids, headings and yaml fences. An English edit
without a re-stamp (or a twin that drifted structurally) fails here."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skills_sync.py"
_spec = importlib.util.spec_from_file_location("skills_sync", _SCRIPT)
skills_sync = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(skills_sync)


def test_twinned_files_cover_every_editorial_prompt():
    files = skills_sync.twinned_files()
    assert "voice_contract.md" in files
    assert "structures/late_v2.md" in files
    assert any(f.startswith("types/") for f in files)
    assert "structures/late.md" not in files  # frozen v1 is not twinned


def test_chinese_twins_are_in_sync():
    problems = skills_sync.check_twins()
    assert problems == [], "\n".join(problems)
