"""Server-rendered PNG charts for memo ``chart`` blocks.

The structure-v2 profiles ask sections to emit ``chart`` blocks (bar /
grouped_bar / line) for their fixed chart slots; this module turns one
validated block into PNG bytes for the DOCX renderer. Everything inside
the image is English/neutral text only — the Chinese document localizes
the heading and caption around the image, so one deterministic PNG
serves both locales (no CJK fonts required in the chart itself).

matplotlib is imported lazily and forced onto the Agg backend so the
server never touches a display; rendering is deterministic for a given
block, and results are cached so the EN and ZH documents share one
render.
"""
from __future__ import annotations

import io
import json
from functools import lru_cache
from typing import Any

# Palette mirrors memo_docx_renderer's document colors.
_NAVY = "#1B2A4A"
_TIFFANY = "#0ABAB5"
_GOLD = "#C9A227"
_GREY = "#8A8F98"
_SERIES_COLORS = (_NAVY, _TIFFANY, _GOLD, _GREY)


def chart_png(block: dict) -> bytes:
    """Render one memo ``chart`` block to PNG bytes (cached)."""
    spec = {
        "chart_type": str(block.get("chart_type") or "bar"),
        "unit": _en(block.get("unit")),
        "series": [
            {
                "label": str(series.get("label") or ""),
                "points": [
                    {"x": str(point.get("x")), "y": float(point.get("y"))}
                    for point in series.get("points") or []
                ],
            }
            for series in block.get("series") or []
            if isinstance(series, dict)
        ],
    }
    return _render_cached(
        json.dumps(spec, sort_keys=True, ensure_ascii=False)
    )


def _en(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("en") or "").strip()
    return str(value or "").strip()


@lru_cache(maxsize=64)
def _render_cached(key: str) -> bytes:
    return _render(json.loads(key))


def _format_value(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if float(value).is_integer():
        return f"{int(value)}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _render(spec: dict) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chart_type = spec["chart_type"]
    series = spec["series"]
    fig, ax = plt.subplots(figsize=(6.6, 3.3), dpi=160)
    try:
        if chart_type == "line":
            for index, one in enumerate(series):
                xs = [p["x"] for p in one["points"]]
                ys = [p["y"] for p in one["points"]]
                ax.plot(
                    xs,
                    ys,
                    marker="o",
                    markersize=4,
                    linewidth=2,
                    color=_SERIES_COLORS[index % len(_SERIES_COLORS)],
                    label=one["label"],
                )
        else:  # bar / grouped_bar
            categories = [p["x"] for p in series[0]["points"]]
            positions = range(len(categories))
            width = 0.72 / max(len(series), 1)
            total_bars = sum(len(one["points"]) for one in series)
            for index, one in enumerate(series):
                offset = (index - (len(series) - 1) / 2) * width
                bars = ax.bar(
                    [pos + offset for pos in positions],
                    [p["y"] for p in one["points"]],
                    width=width if len(series) > 1 else 0.55,
                    color=_SERIES_COLORS[index % len(_SERIES_COLORS)],
                    label=one["label"],
                )
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

        if len(series) > 1:
            ax.legend(frameon=False, fontsize=8.5, loc="best")
        if spec["unit"]:
            ax.set_ylabel(spec["unit"], fontsize=9, color="#333333")
        ax.tick_params(labelsize=9, colors="#333333")
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color("#BBBBBB")
        ax.grid(axis="y", linewidth=0.6, alpha=0.3)
        ax.set_axisbelow(True)
        labels = [str(label.get_text()) for label in ax.get_xticklabels()]
        if any(len(label) > 9 for label in labels):
            plt.setp(ax.get_xticklabels(), rotation=18, ha="right")
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png")
        return buffer.getvalue()
    finally:
        plt.close(fig)
