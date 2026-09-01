"""Card → spine composition for the Memo Studio process flow.

The seed direction (spine → cards) lives in
:func:`memo_editor_store.apply_agent_spine`. This module owns the generate
direction: turning the user's edited card state back into the
``spine.json`` payload Phase 3 consumes. The composed ``shared_facts`` is
the pin sheet — the existing pin-echo gate then mechanically enforces the
user's decisions in the final memo. The package skeleton (including the
complete sources list) is copied unchanged from the investigation spine:
sections cite sources by id and cannot add them.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from . import memo_editor_store

STUDIO_PIN_SHEET_FILENAME = "studio_pin_sheet.md"

_SECTION_NOTE_LIMIT = 400
_SEVERITY_RATING = {"high": "8/10", "medium": "5/10", "low": "3/10"}
_LIKELIHOODS = {"high": "High", "medium": "Medium", "low": "Low"}
_RATING_RE = re.compile(r"^(10|[1-9])\s*(?:/\s*10)?$")


class StudioComposeError(ValueError):
    """The studio state cannot become a valid spine; the user can fix it."""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_rating(card: dict) -> str:
    """Best-effort ``N/10`` from a card: accept "7", 7, "7/10"; fall back
    to the severity mapping; never return an invalid pin."""
    for raw in (card.get("agent_rating"), card.get("rating")):
        match = _RATING_RE.match(_clean(raw))
        if match:
            return f"{match.group(1)}/10"
    return _SEVERITY_RATING.get(_clean(card.get("severity")).lower(), "5/10")


def _normalize_likelihood(card: dict) -> str | None:
    return _LIKELIHOODS.get(_clean(card.get("likelihood")).lower())


def _included_cards(state: dict, section_id: str) -> list[dict]:
    section = (state.get("sections") or {}).get(section_id) or {}
    cards = [
        card
        for card in (section.get("cards") or [])
        if isinstance(card, dict) and card.get("included", True)
    ]
    cards.sort(key=lambda c: int(c.get("rank") or 999))
    return cards


def _selected_conclusion(state: dict) -> dict | None:
    section = (state.get("sections") or {}).get(
        memo_editor_store.SECTION_CONCLUSION
    ) or {}
    selected = section.get("selected_option_id")
    for option in section.get("options") or []:
        if isinstance(option, dict) and option.get("id") == selected:
            return option
    return None


def _card_bullet_lines(card: dict) -> list[str]:
    lines: list[str] = []
    for bullet in card.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        text = _clean(bullet.get("text"))
        if text:
            lines.append(f"- {text}")
        for child in bullet.get("children") or []:
            if isinstance(child, dict) and _clean(child.get("text")):
                lines.append(f"  - {_clean(child.get('text'))}")
    return lines


def _thesis_note(thesis_cards: list[dict]) -> str:
    ordered = "; ".join(
        f"{index}) {_clean(card.get('title'))}"
        for index, card in enumerate(thesis_cards, start=1)
    )
    suffix = (
        " Full card text: logs/english_units/"
        f"{STUDIO_PIN_SHEET_FILENAME}."
    )
    note = f"Pinned theses, in this order: {ordered}."
    if len(note) + len(suffix) > _SECTION_NOTE_LIMIT:
        note = note[: _SECTION_NOTE_LIMIT - len(suffix) - 1].rstrip() + "…"
    return note + suffix


_RISK_NOTE = (
    "Risk order, inclusion, ratings, and likelihoods are user-decided — "
    "mirror shared_facts.risks exactly. Mitigation and framing notes: "
    f"logs/english_units/{STUDIO_PIN_SHEET_FILENAME}."
)


def _pin_sheet(
    *,
    state: dict,
    recommendation: str,
    stance: dict,
    thesis_cards: list[dict],
    risk_cards: list[dict],
) -> str:
    lines: list[str] = [
        "# Memo Studio pin sheet",
        "",
        f"Composed from editor revision {state.get('revision_id') or '?'}. "
        "A human reviewed and ranked these cards; the memo must follow "
        "their order, inclusion, and stance.",
        "",
        "## Recommendation (pinned verbatim)",
        recommendation,
        "",
        f"## Conclusion stance: {_clean(stance.get('label')) or 'selected'}",
    ]
    if _clean(stance.get("rationale")):
        lines.append(f"Rationale: {_clean(stance.get('rationale'))}")
    lines.append("")
    lines.append("## Investment thesis cards (user order)")
    if thesis_cards:
        for index, card in enumerate(thesis_cards, start=1):
            lines.append(f"{index}. **{_clean(card.get('title'))}**")
            lines.extend(_card_bullet_lines(card))
    else:
        lines.append("(none pinned — draft highlights from the analysis)")
    lines.append("")
    lines.append("## Risk cards (user order)")
    for index, card in enumerate(risk_cards, start=1):
        likelihood = _normalize_likelihood(card)
        lines.append(
            f"{index}. **{_clean(card.get('title'))}** — "
            f"{normalize_rating(card)}"
            + (f", likelihood {likelihood}" if likelihood else "")
        )
        lines.extend(_card_bullet_lines(card))
    return "\n".join(lines) + "\n"


def compose_spine(
    state: dict,
    base_spine: dict,
    *,
    provenance: dict | None = None,
) -> tuple[dict, str, list[str]]:
    """Compose the generate-time spine from the studio card state.

    Returns ``(spine, pin_sheet_md, warnings)``. Raises
    :class:`StudioComposeError` for states the user must fix (no
    investigation spine, no conclusion stance, zero included risks).
    ``key_metrics``/``scenarios``/``source_topics`` round-trip verbatim
    from the seeded ``pinned_facts`` (falling back to the base spine) —
    the pin-echo gate checks their numeric tokens downstream.
    """
    if not isinstance(base_spine, dict):
        raise StudioComposeError(
            "no investigation spine found — run Deep Investigate first"
        )
    skeleton = base_spine.get("package_skeleton")
    if (
        not isinstance(skeleton, dict)
        or not isinstance(skeleton.get("sources"), list)
        or not skeleton.get("sources")
    ):
        raise StudioComposeError(
            "the investigation spine has no package skeleton or sources — "
            "re-run Deep Investigate"
        )
    base_facts = base_spine.get("shared_facts")
    base_facts = base_facts if isinstance(base_facts, dict) else {}
    warnings: list[str] = []

    stance = _selected_conclusion(state)
    if stance is None:
        raise StudioComposeError("no conclusion stance is selected")
    recommendation = _clean(stance.get("text"))
    if not recommendation:
        raise StudioComposeError("the selected conclusion option has no text")
    if len(recommendation) > 300:
        recommendation = recommendation[:299].rstrip() + "…"
        warnings.append(
            "the selected conclusion text was truncated to 300 characters "
            "for the recommendation pin"
        )

    risk_cards = _included_cards(state, memo_editor_store.SECTION_RISKS)
    if not risk_cards:
        raise StudioComposeError("no risk cards are included")
    if not 4 <= len(risk_cards) <= 6:
        warnings.append(
            f"{len(risk_cards)} risk cards are included; the memo's risk "
            "register works best with 4-6"
        )
    risks: list[dict] = []
    for card in risk_cards:
        summary = _clean(card.get("title"))
        if len(summary) > 160:
            summary = summary[:159].rstrip() + "…"
            warnings.append(
                f"risk card title truncated to 160 characters: {summary[:60]}…"
            )
        risk: dict[str, Any] = {
            "summary": summary,
            "rating": normalize_rating(card),
        }
        likelihood = _normalize_likelihood(card)
        if likelihood:
            risk["likelihood"] = likelihood
        risks.append(risk)

    thesis_cards = _included_cards(
        state, memo_editor_store.SECTION_INVESTMENT_THESIS
    )
    if not thesis_cards:
        warnings.append(
            "no thesis cards are included; the highlights section falls "
            "back to the analysis artifacts"
        )

    pinned = state.get("pinned_facts")
    pinned = pinned if isinstance(pinned, dict) else {}
    shared_facts: dict[str, Any] = {
        "recommendation_sentence": recommendation,
        "key_metrics": copy.deepcopy(
            pinned.get("key_metrics")
            if isinstance(pinned.get("key_metrics"), list)
            else base_facts.get("key_metrics") or []
        ),
        "scenarios": copy.deepcopy(
            pinned.get("scenarios")
            if isinstance(pinned.get("scenarios"), dict)
            and pinned.get("scenarios")
            else base_facts.get("scenarios") or {}
        ),
        "risks": risks,
        "source_topics": copy.deepcopy(
            pinned.get("source_topics")
            if isinstance(pinned.get("source_topics"), dict)
            and pinned.get("source_topics")
            else base_facts.get("source_topics") or {}
        ),
    }

    section_notes = base_spine.get("section_notes")
    section_notes = (
        copy.deepcopy(section_notes) if isinstance(section_notes, dict) else {}
    )
    if thesis_cards:
        section_notes["investment_highlights"] = _thesis_note(thesis_cards)
    section_notes["investment_risk"] = _RISK_NOTE

    spine = {
        "package_skeleton": copy.deepcopy(skeleton),
        "shared_facts": shared_facts,
        "section_notes": section_notes,
        "studio_provenance": {
            "revision_id": _clean(state.get("revision_id")),
            **{
                key: _clean(value)
                for key, value in (provenance or {}).items()
                if _clean(value)
            },
        },
    }
    pin_sheet = _pin_sheet(
        state=state,
        recommendation=recommendation,
        stance=stance,
        thesis_cards=thesis_cards,
        risk_cards=risk_cards,
    )
    return spine, pin_sheet, warnings
