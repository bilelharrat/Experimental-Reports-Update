"""Build a great, text-free art prompt per page.

Prompt = STYLE_CAPSULE (fixed house style)
       + SUBJECT       (a concrete metaphor derived from the page theme)
       + COMPOSITION    (engineered negative space for the coded overlay)
       + NEGATIVES      (fixed — keeps text/logos/UI out of the raster)
"""
from __future__ import annotations

# One verbatim block on every image → the deck looks art-directed.
STYLE_CAPSULE = (
    "Cinematic abstract 3D render, institutional-finance editorial art. "
    "Deep ink-navy background (#04070f), single cool key light, soft "
    "volumetric haze, electric-cyan rim light with a restrained violet "
    "accent bloom, deep falloff to near-black. Filmic low-saturation "
    "grade, fine grain, premium and quiet. No symbology."
)

NEGATIVES = (
    "Absolutely no text, letters, numbers, words, logos, watermark, UI, "
    "charts, graphs, axes, diagrams, human figures, faces, brand "
    "likeness, clutter, busy background, oversaturation, or lens-flare "
    "kitsch."
)

# Composition presets. The coded overlay puts the title + dek in the
# LOWER-LEFT, so the art must fill the frame and dominate the upper /
# right while that lower-left band fades to a clean dark gradient.
_COMPOSITION = (
    "Portrait 1024x1536. The subject is large and fills the upper two-"
    "thirds and right side of the frame, bleeding off the top and right "
    "edges with depth and presence. The lower-left third dissolves into "
    "a smooth, detail-free near-black gradient reserved for overlaid "
    "text. No empty dead center; the art carries the page."
)
_HERO_COMPOSITION = (
    "Portrait 1024x1536, cinematic hero. The subject is bold and sweeps "
    "across the upper half and right side, bleeding off the top and "
    "right edges, with strong presence. The lower-left half fades to a "
    "smooth detail-free near-black gradient reserved for a large "
    "overlaid title and stat band. No empty dead center."
)

# Concrete metaphor bank keyed by the page's SECTION name (the kicker,
# e.g. "03 · Valuation discipline" → "valuation discipline"). The
# section name is unambiguous; the headline is not (it borrows words
# like "price" across topics), so it is only a fallback. Distinct
# subjects per section ⇒ distinct prompts ⇒ no cache collisions.
_BANK = [
    (("verdict",),
     "a single precision balance form suspended in a dark void, one "
     "polished cyan-lit fulcrum in sharp focus, the rest dissolving to "
     "bokeh — poised equilibrium, cold and exact"),
    (("investment read", "thesis", "underwrite"),
     "two opposing translucent luminous masses held in taut balance, "
     "one cyan and resolved, one violet and unresolved, a tense gap "
     "of dark space between them"),
    (("valuation",),
     "two translucent layered time-planes drifting out of alignment, a "
     "thin cyan parallax seam between them, depth fading to black"),
    (("growth quality", "growth", "bridge"),
     "converging luminous tributaries of uneven width merging into one "
     "broader cyan channel cut through dark glass strata"),
    (("moat",),
     "stacked translucent glass strata in cross-section, only the "
     "deepest core seam glowing cyan, the upper layers dim commodity-grey"),
    (("product adoption", "adoption", "product"),
     "an ascending series of receding luminous thresholds, the near "
     "ones solid cyan, the far ones faint — staged progression into haze"),
    (("competitive", "replacement"),
     "a sparse constellation of cool nodes with one dominant violet "
     "anchor, thin tension filaments across vast dark negative space"),
    (("exit math", "exit", "scenario"),
     "a single light trail forking into three divergent paths of "
     "unequal brightness receding into deep darkness"),
    (("ic gates", "gates", "gate"),
     "a row of narrow vertical threshold portals, only some lit cyan "
     "from within, the unlit ones swallowed in deep shadow"),
]

_FALLBACK = (
    "an abstract field of layered cool light planes with a single "
    "cyan focal ridge dissolving into dark depth"
)


def _section(page: dict) -> str:
    # strip a leading "NN · " / "NN -" ordinal from the kicker
    import re
    k = (page.get("kicker") or "").lower()
    return re.sub(r"^\s*\d+\s*[·\-.]\s*", "", k).strip()


def _subject(page: dict) -> str:
    sec = _section(page)
    for keys, subj in _BANK:
        if any(k in sec for k in keys):
            return subj
    # headline fallback only if the section name matched nothing
    head = (page.get("headline") or "").lower()
    for keys, subj in _BANK:
        if any(k in head for k in keys):
            return subj
    return _FALLBACK


def art_prompt(page: dict, hero: bool = False) -> str:
    comp = _HERO_COMPOSITION if hero else _COMPOSITION
    return (
        f"{STYLE_CAPSULE} SUBJECT: {_subject(page)}. "
        f"COMPOSITION: {comp} {NEGATIVES}"
    )
