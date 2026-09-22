"""The memo pipeline's switches default ON, from one place.

A fresh checkout — or a server whose .env did not carry the owner's lines —
used to build the old v1 memo, because each switch defaulted off at every
call site. These pin the defaults, the off switch, and that no call site
reads a switch with its own default again.
"""
from __future__ import annotations

import re
from pathlib import Path

from server import memo_flags, memo_structure


def test_every_switch_defaults_on_with_a_clean_env(monkeypatch):
    for name in memo_flags.DEFAULTS:
        monkeypatch.delenv(name, raising=False)
    assert all(memo_flags.enabled(name) for name in memo_flags.DEFAULTS)


def test_a_clean_env_writes_the_v2_compact_memo(monkeypatch):
    """The review that prompted this found 46 memos with no scorecard, no
    citations and no charts — v1, which is what an unset flag used to build.
    """
    for name in memo_flags.DEFAULTS:
        monkeypatch.delenv(name, raising=False)
    structure = memo_structure.active_structure("late", "compact")
    assert structure.stage == "late_compact"
    assert structure.scorecard_weights()


def test_zero_still_turns_a_switch_off(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "0")
    assert not memo_flags.enabled("BSH_MEMO_STRUCTURE_V2")
    assert memo_structure.active_structure("late", "compact") is memo_structure.LATE


def test_no_call_site_carries_its_own_default():
    """The default used to be written at fourteen call sites. One place."""
    server = Path(memo_flags.__file__).parent
    names = "|".join(re.escape(n) for n in memo_flags.DEFAULTS)
    pattern = re.compile(rf'(?:environ\.get|getenv|_env_flag)\(\s*"({names})"')
    offenders = [
        f"{path.name}: {match.group(1)}"
        for path in server.glob("*.py")
        if path.name != "memo_flags.py"
        for match in pattern.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
