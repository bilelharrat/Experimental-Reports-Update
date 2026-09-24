"""Server-rendered PNG charts for memo ``chart`` blocks.

The structure-v2 profiles ask sections to emit ``chart`` blocks (bar /
grouped_bar / hbar / line / pie) for their fixed chart slots; this module
turns one validated block into PNG bytes for the DOCX renderer, once per
document language.

What the image carries, and what it leaves to the document:

- The reading ("Bars below 1.0x lose money") is printed ONCE, in the
  caption under the image — never drawn inside it as well.
- Series labels, x categories, the unit and reference-line labels may be
  bilingual ``{"en", "zh"}``; each language gets its own render (the
  locale and the resolved labels are part of the cache key). Plain strings
  serve both languages as before.
- Text uses the memo's body face where the host has it — Arial, with a CJK
  face behind it for Chinese labels (Hiragino Sans GB / Arial Unicode MS /
  Noto Sans CJK SC), falling back to matplotlib's DejaVu Sans. Nothing is
  bundled; the stack is filtered to installed fonts so no render logs a
  missing-font warning.
- Optional ``reference_lines`` ``[{"y": 1.0, "label": "Breakeven"}]`` draw a
  dashed rule (vertical on ``hbar``); a point with ``"estimate": true``
  draws lighter and hatched (bars) or with a dashed segment into it
  (lines). A period written "2027E" / "2027F" is an estimate too.
- A line chart whose x values are all dates (``2026``, ``2026-03``,
  ``2026-03-31``, ``2026-Q2``, ``Q2 2026``, ``FY2026``, ``2027E``) plots
  them on a true time axis, so a missing period shows as a gap.
- X labels rotate only when their measured widths overflow their slots.

matplotlib is imported lazily and forced onto the Agg backend so the
server never touches a display; rendering is deterministic for a given
block, locale and host.
"""
from __future__ import annotations

import io
import json
import re
from functools import lru_cache
from typing import Any

# Palette mirrors memo_docx_renderer's document colors.
_NAVY = "#1B2A4A"
_TIFFANY = "#0ABAB5"
_GOLD = "#C9A227"
_GREY = "#8A8F98"
_RULE = "#A33A2B"
_SERIES_COLORS = (_NAVY, _TIFFANY, _GOLD, _GREY)

# The memo's body face first, CJK faces a Mac or Linux host has behind it,
# matplotlib's bundled face last.
FONT_STACK = (
    "Arial",
    "Hiragino Sans GB",
    "Arial Unicode MS",
    "Noto Sans CJK SC",
    "DejaVu Sans",
)

MAX_REFERENCE_LINES = 3


def chart_png(block: dict, locale: str = "en") -> bytes:
    """Render one memo ``chart`` block to PNG bytes for ``locale`` (cached:
    the same block, language and labels render once per process)."""
    spec = chart_spec(block, locale)
    return _render_cached(json.dumps(spec, sort_keys=True, ensure_ascii=False))


def chart_spec(block: dict, locale: str = "en") -> dict:
    """The resolved, JSON-able drawing spec for ``block`` in ``locale`` —
    every label already in that language."""
    locale = "zh" if locale == "zh" else "en"
    series = []
    for one in block.get("series") or []:
        if not isinstance(one, dict):
            continue
        points = []
        for point in one.get("points") or []:
            if not isinstance(point, dict):
                continue
            points.append(
                {
                    "x": _text(point.get("x"), locale),
                    "y": float(point.get("y")),
                    "estimate": _flag(point.get("estimate"))
                    or _estimate_marker(_text(point.get("x"), "en")),
                }
            )
        series.append({"label": _text(one.get("label"), locale), "points": points})
    lines = []
    rules = block.get("reference_lines")
    for item in (rules if isinstance(rules, list) else [])[:MAX_REFERENCE_LINES]:
        if not isinstance(item, dict):
            continue
        value = item.get("y")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        lines.append({"y": float(value), "label": _text(item.get("label"), locale)})
    return {
        "locale": locale,
        "chart_type": str(block.get("chart_type") or "bar").strip().lower(),
        "unit": _text(block.get("unit"), locale),
        "series": series,
        "reference_lines": lines,
    }


def _flag(value: Any) -> bool:
    """``true`` (or a model's "true" / "yes" / 1) — anything else is False."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "yes", "1", "y"}


def _text(value: Any, locale: str) -> str:
    """A label in ``locale``: a bilingual value's half (English when the
    Chinese half is blank), a plain value as written."""
    if isinstance(value, dict):
        chosen = value.get(locale)
        if chosen is None or not str(chosen).strip():
            chosen = value.get("en")
        return str(chosen or "").strip()
    if value is None:
        return ""
    return str(value).strip()


# ---- dates on the x axis -------------------------------------------------------

_YEAR_DATE_RE = re.compile(
    r"^(?:FY\s?)?(\d{4})(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?)?\s*([EF])?$",
    re.IGNORECASE,
)
_QUARTER_FIRST_RE = re.compile(r"^Q([1-4])\s*[-']?\s*(\d{4})\s*([EF])?$", re.IGNORECASE)
_QUARTER_LAST_RE = re.compile(r"^(\d{4})\s*[-/ ]?\s*Q([1-4])\s*([EF])?$", re.IGNORECASE)


def _estimate_marker(label: str) -> bool:
    """"2027E" / "FY2027F" / "2027-Q3E" — a period the writer marked as an
    estimate or forecast."""
    text = str(label or "").strip()
    return bool(
        (
            _YEAR_DATE_RE.match(text)
            or _QUARTER_LAST_RE.match(text)
            or _QUARTER_FIRST_RE.match(text)
        )
        and text[-1:].upper() in {"E", "F"}
    )


def _date_position(label: str) -> float | None:
    """A dated label as a decimal year (2026-07 -> 2026.5), else None."""
    text = str(label or "").strip()
    match = _YEAR_DATE_RE.match(text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2) or 1)
        day = int(match.group(3) or 1)
        if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2200):
            return None
        return year + (month - 1) / 12 + (day - 1) / 365
    match = _QUARTER_LAST_RE.match(text)
    if match:
        return int(match.group(1)) + (int(match.group(2)) - 1) / 4
    match = _QUARTER_FIRST_RE.match(text)
    if match:
        return int(match.group(2)) + (int(match.group(1)) - 1) / 4
    return None


def time_positions(labels: list[str]) -> list[float] | None:
    """Positions on a true time axis when EVERY label is a date and they
    run forward in time; None otherwise (the axis stays categorical)."""
    if len(labels) < 2:
        return None
    positions = [_date_position(label) for label in labels]
    if any(position is None for position in positions):
        return None
    if any(later <= earlier for earlier, later in zip(positions, positions[1:])):
        return None
    return positions  # type: ignore[return-value]


# ---- rendering ----------------------------------------------------------------


@lru_cache(maxsize=128)
def _render_cached(key: str) -> bytes:
    return _render(json.loads(key))


def _format_value(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if float(value).is_integer():
        return f"{int(value)}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


@lru_cache(maxsize=1)
def installed_font_stack() -> tuple[str, ...]:
    """FONT_STACK filtered to the faces this host has."""
    from matplotlib import font_manager

    installed = {entry.name for entry in font_manager.fontManager.ttflist}
    stack = tuple(name for name in FONT_STACK if name in installed)
    return stack or ("DejaVu Sans",)


def _tint(color: str, alpha: float) -> tuple[float, float, float, float]:
    from matplotlib.colors import to_rgba

    red, green, blue, _ = to_rgba(color)
    return (red, green, blue, alpha)


def _render(spec: dict) -> bytes:
    import logging

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # A CJK face without a "normal" weight (Hiragino Sans GB ships W3/W6)
    # makes font_manager warn on every new text size; the substitute it
    # picks is the right one.
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

    rc = {
        "font.family": list(installed_font_stack()),
        "axes.unicode_minus": False,
        "hatch.linewidth": 0.6,
    }
    with matplotlib.rc_context(rc):
        fig, ax = plt.subplots(figsize=(6.6, 3.3), dpi=160)
        try:
            _draw(fig, ax, spec)
            buffer = io.BytesIO()
            fig.savefig(buffer, format="png")
            return buffer.getvalue()
        finally:
            plt.close(fig)


def _draw(fig: Any, ax: Any, spec: dict) -> None:
    chart_type = spec["chart_type"]
    series = spec["series"]
    unit = spec["unit"]
    if chart_type == "pie":
        _draw_pie(ax, series[0]["points"])
        fig.tight_layout()
        return
    if chart_type == "hbar":
        _draw_hbar(ax, series[0]["points"], unit)
    elif chart_type == "line":
        _draw_lines(ax, series)
    else:  # bar / grouped_bar
        _draw_bars(ax, series)
    rules = _draw_reference_lines(
        ax, spec.get("reference_lines") or [], vertical=chart_type == "hbar"
    )
    # The legend names the series when there are several, and every
    # labelled rule — placed where it covers the least data.
    handles, labels = ax.get_legend_handles_labels()
    if len(series) <= 1:
        keep = [(h, lbl) for h, lbl in zip(handles, labels) if h in rules]
        handles, labels = [h for h, _ in keep], [lbl for _, lbl in keep]
    if handles:
        ax.legend(handles, labels, frameon=False, fontsize=8.5, loc="best")
    if unit and chart_type != "hbar":
        ax.set_ylabel(unit, fontsize=9, color="#333333")
    ax.tick_params(labelsize=9, colors="#333333")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#BBBBBB")
    ax.grid(axis="x" if chart_type == "hbar" else "y", linewidth=0.6, alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()
    if chart_type != "hbar" and x_labels_overflow(fig, ax):
        for label in ax.get_xticklabels():
            label.set_rotation(30)
            label.set_horizontalalignment("right")
        fig.tight_layout()


def _draw_pie(ax: Any, points: list[dict]) -> None:
    values = [max(point["y"], 0.0) for point in points]
    labels = [point["x"] for point in points]
    colors = [_SERIES_COLORS[i % len(_SERIES_COLORS)] for i in range(len(points))]
    _wedges, _texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.0f%%",
        startangle=90,
        counterclock=False,
        textprops={"fontsize": 9, "color": "#333333"},
        wedgeprops={"linewidth": 1, "edgecolor": "white"},
    )
    for autotext in autotexts:
        autotext.set_color("white")
    ax.axis("equal")


def _style_estimate_bars(bars: Any, points: list[dict], color: str) -> None:
    for bar, point in zip(bars, points):
        if point.get("estimate"):
            bar.set_facecolor(_tint(color, 0.35))
            bar.set_edgecolor(color)
            bar.set_hatch("///")
            bar.set_linewidth(0.8)


def _draw_hbar(ax: Any, points: list[dict], unit: str) -> None:
    labels = [point["x"] for point in points]
    values = [point["y"] for point in points]
    positions = list(range(len(points)))
    bars = ax.barh(positions, values, height=0.55, color=_NAVY)
    _style_estimate_bars(bars, points, _NAVY)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()  # first point on top
    ax.bar_label(
        bars, fmt=lambda v: _format_value(v), fontsize=8, padding=3, color="#333333"
    )
    ax.margins(x=0.12)
    if unit:
        ax.set_xlabel(unit, fontsize=9, color="#333333")


def _draw_bars(ax: Any, series: list[dict]) -> None:
    categories = [point["x"] for point in series[0]["points"]]
    positions = range(len(categories))
    width = 0.72 / max(len(series), 1)
    total_bars = sum(len(one["points"]) for one in series)
    for index, one in enumerate(series):
        color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
        offset = (index - (len(series) - 1) / 2) * width
        bars = ax.bar(
            [pos + offset for pos in positions],
            [point["y"] for point in one["points"]],
            width=width if len(series) > 1 else 0.55,
            color=color,
            label=one["label"],
        )
        _style_estimate_bars(bars, one["points"], color)
        if total_bars <= 12:
            ax.bar_label(
                bars,
                fmt=lambda v: _format_value(v),
                fontsize=8,
                padding=2,
                color="#333333",
            )
    ax.set_xticks(list(positions))
    ax.set_xticklabels(categories)
    ax.margins(y=0.16)


def _draw_lines(ax: Any, series: list[dict]) -> None:
    labels = [point["x"] for point in series[0]["points"]]
    positions = time_positions(labels) or list(range(len(labels)))
    for index, one in enumerate(series):
        color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
        ys = [point["y"] for point in one["points"]]
        estimates = [bool(point.get("estimate")) for point in one["points"]]
        # A solid path through the reported points, a dashed segment into
        # every estimated one.
        for start in range(len(ys) - 1):
            ax.plot(
                positions[start : start + 2],
                ys[start : start + 2],
                linewidth=2,
                color=color,
                linestyle="--" if estimates[start + 1] else "-",
                label=one["label"] if start == 0 else None,
            )
        for x, y, estimate in zip(positions, ys, estimates):
            ax.plot(
                [x],
                [y],
                marker="o",
                markersize=4.5,
                color=color,
                markerfacecolor="white" if estimate else color,
                markeredgewidth=1.2,
                linestyle="none",
            )
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.margins(x=0.04, y=0.12)


def _draw_reference_lines(ax: Any, lines: list[dict], *, vertical: bool) -> list:
    """Dashed rules at the given values (vertical on a horizontal-bar
    chart); a labelled rule joins the legend. Returns the drawn rules."""
    drawn = []
    for line in lines:
        value = line["y"]
        label = line.get("label") or None
        draw = ax.axvline if vertical else ax.axhline
        drawn.append(
            draw(value, color=_RULE, linestyle="--", linewidth=1.1, zorder=3, label=label)
        )
    if lines and not vertical:
        # Keep every rule inside the plot.
        low, high = ax.get_ylim()
        values = [line["y"] for line in lines]
        top = max(values)
        ax.set_ylim(min(low, min(values)), max(high, top + abs(top) * 0.08))
    return [rule for rule, line in zip(drawn, lines) if line.get("label")]


def x_labels_overflow(fig: Any, ax: Any) -> bool:
    """True when two neighbouring x tick labels overlap or one runs past
    the figure edge, measured on the drawn canvas."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = [
        label.get_window_extent(renderer)
        for label in ax.get_xticklabels()
        if label.get_visible() and label.get_text()
    ]
    if not boxes:
        return False
    boxes.sort(key=lambda box: box.x0)
    gap = 4.0  # pixels between neighbours
    for left, right in zip(boxes, boxes[1:]):
        if left.x1 + gap > right.x0:
            return True
    return boxes[0].x0 < 0 or boxes[-1].x1 > fig.bbox.width
