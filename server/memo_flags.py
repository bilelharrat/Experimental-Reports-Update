"""The memo pipeline's on/off switches, and their defaults, in one place.

These eight flags together are the pipeline the owner tests every day: the
v2 structure (scorecard, pinned facts, clickable citations, charts, the
compact and full profiles), parallel English sections, the speculative spine
and early sections, the Chinese chase, and the pin-check repair. Each used to
default OFF, with the default repeated at every call site (fourteen of them),
so a fresh checkout — or a server whose .env did not carry the owner's
lines — silently built the old v1 memo: five sections, no scorecard, no
citations, and a Compact/Full choice that did nothing. A 2026-09-22 review
of 46 memos written that way reported exactly those gaps.

They now default ON, and every site reads its default from here. An
explicit ``=0`` in the environment still turns any of them off.
"""
from __future__ import annotations

import os

DEFAULTS: dict[str, bool] = {
    # The v2 structure family: profiles with a scorecard, pins, citations,
    # charts; honours the Compact / Full choice. Needs parallel English.
    "BSH_MEMO_STRUCTURE_V2": True,
    # One worker per section instead of one monolithic English call. The v2
    # structure has no monolithic twin.
    "BSH_MEMO_ENGLISH_PARALLEL": True,
    # Write the analysis artifacts on a side agent while sections are written.
    "BSH_MEMO_ARTIFACTS_ASYNC": True,
    # Start the spine as soon as the passes that feed its pins are in.
    "BSH_MEMO_SPINE_SPECULATIVE": True,
    # Start sections that only need the pins before the full wave.
    "BSH_MEMO_SECTION_EARLY_START": True,
    # Translate each finished section while the others are still written.
    "BSH_MEMO_ZH_CHASING": True,
    # The compact bilingual unit format for the Chinese stage.
    "BSH_MEMO_ZH_COMPACT": True,
    # Feed pin-echo findings to the surgical repair.
    "BSH_MEMO_PIN_CHECK_REPAIR": True,
}

_TRUE = {"1", "true", "yes", "on"}


def enabled(name: str) -> bool:
    """Whether the switch ``name`` is on: the environment if it says, else
    the default above. Unknown names are a programming error."""
    default = DEFAULTS[name]
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE
