#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "Pillow>=10.0.0",
#     "reportlab>=4.0.0",
#     "numpy>=1.24",
#     "opencv-python-headless>=4.8",
# ]
# ///
"""
Render a 2-up bilingual "translator notes" PDF from images + augmented
overlay JSONs. Letter landscape, one page per image:

    [ original  |  faded original + Chinese overlay ]

This script is idempotent — it reads `<stem>_overlay.json` files that
were already produced by extract_text + translate, and rebuilds the PDF
without making any LLM calls. Re-run any time you tweak the layout.

Usage:
    uv run scripts/render_pdf.py /path/to/slides_dir
    uv run scripts/render_pdf.py /path/to/slides_dir --out custom.pdf
    uv run scripts/render_pdf.py /path/to/slides_dir --fade 0.7

Layout decisions in this version (from feedback on the first pass):

- No solid white pad behind each translation. The pad ate the layout
  and made any white/light-colored text invisible.
- Chinese text is always drawn in a single dark color, regardless of
  the original `text_color`. Most source slides have white-on-dark
  titles; inheriting that color on a faded-to-white panel made the
  Chinese disappear. Readability beats color fidelity here.
- A subtle cream "highlight" rect (≈8% opacity) sits behind each
  translation to keep it legible on visually busy faded backgrounds,
  without dominating the panel.
- Font registration walks every subface in PingFang.ttc / Noto CJK TTC
  rather than guessing index 0, and the picked font is printed at
  startup so it's obvious if we silently fell back to STSong-Light.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import platform
import sys
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

PAGE_WIDTH, PAGE_HEIGHT = landscape(letter)  # (792, 612)
MARGIN = 18
GUTTER = 12
PANEL_WIDTH = (PAGE_WIDTH - 2 * MARGIN - GUTTER) / 2
PANEL_HEIGHT = PAGE_HEIGHT - 2 * MARGIN
LEFT_PANEL_X = MARGIN
RIGHT_PANEL_X = MARGIN + PANEL_WIDTH + GUTTER
PANEL_Y = MARGIN

# Chinese text colors. We pick one or the other based on the local
# brightness of the faded image at each render_box, so text always has
# contrast without needing a backing rectangle.
ZH_DARK_COLOR = HexColor("#0F1A2E")    # near-black navy, used on light backgrounds
ZH_LIGHT_COLOR = HexColor("#FAF7EE")   # warm cream, used on dark backgrounds

# Halo (drawn behind the main text) — opposite-luminance of the text
# color, with low alpha. Provides edge contrast on patchy backgrounds.
ZH_HALO_LIGHT = Color(1.0, 1.0, 1.0, alpha=0.75)
ZH_HALO_DARK = Color(0.0, 0.0, 0.0, alpha=0.55)

# Cream highlight (legacy — only drawn when --highlight is passed).
ZH_HIGHLIGHT_COLOR = Color(1.0, 0.972, 0.862, alpha=0.55)

# Threshold: mean luminance below this counts as "dark area, use light text".
DARK_BG_LUMINANCE_THRESHOLD = 0.55

PRIMARY_FONT_NAME = "BatchTranslateCJK"
FALLBACK_FONT_NAME = "STSong-Light"  # built into reportlab


# ---------------------------------------------------------------------------
# Font registration
# ---------------------------------------------------------------------------

def _ttc_candidates() -> list[tuple[str, list[int]]]:
    """
    Return [(path, candidate_subface_indexes)] by platform. We try a range
    of indexes because TTC subfont ordering varies across OS versions.
    """
    sysname = platform.system()
    if sysname == "Darwin":
        # PingFang.ttc on modern macOS contains PingFang HK / TC / SC in
        # multiple weights. We don't know which index is which version-to-
        # version, so we walk all of them. PingFang SC tends to be 4-6.
        return [
            ("/System/Library/Fonts/PingFang.ttc", list(range(0, 14))),
            ("/System/Library/Fonts/STHeiti Medium.ttc", list(range(0, 4))),
            ("/System/Library/Fonts/STHeiti Light.ttc", list(range(0, 4))),
            ("/System/Library/Fonts/Hiragino Sans GB.ttc", list(range(0, 4))),
            ("/Library/Fonts/Arial Unicode.ttf", [0]),
            ("/System/Library/Fonts/Supplemental/Songti.ttc", list(range(0, 8))),
        ]
    if sysname == "Linux":
        return [
            ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", [2, 0, 1, 3]),
            ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", [2, 0, 1, 3]),
            ("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", [2, 0, 1, 3]),
            ("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc", [2, 0, 1, 3]),
            ("/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc", [0]),
        ]
    if sysname == "Windows":
        return [
            ("C:/Windows/Fonts/msyh.ttc", [0, 1]),
            ("C:/Windows/Fonts/msyh.ttf", [0]),
            ("C:/Windows/Fonts/simhei.ttf", [0]),
            ("C:/Windows/Fonts/simsun.ttc", [0, 1]),
        ]
    return []


def _font_can_render_chinese(font_name: str) -> bool:
    """
    Sanity check: ask the registered font whether it has glyphs for a
    handful of Simplified Chinese characters. If `stringWidth` returns 0
    or the font can't measure the chars, this font is unusable.
    """
    try:
        face = pdfmetrics.getFont(font_name).face
    except Exception:
        return False
    sample = "中文测试营收"  # mix of common SC characters
    for ch in sample:
        cp = ord(ch)
        # Most TTF fonts expose `charWidths` mapping codepoints to widths.
        widths = getattr(face, "charWidths", None)
        if widths is None:
            # CID fonts route through different machinery; assume ok.
            return True
        w = widths.get(cp, 0)
        if w == 0:
            return False
    return True


def register_fonts(verbose: bool = False) -> str:
    """
    Register CJK fonts and return the name to use for Chinese text.

    Strategy:
        1. Always register the CIDFont fallback (built into reportlab).
        2. Walk every (path, index) candidate; for the first one whose
           registration succeeds AND can actually render Chinese,
           promote it to primary.
        3. Otherwise return the CIDFont fallback.
    """
    # CID fallback first — guarantees we always have *something*.
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(FALLBACK_FONT_NAME))
    except Exception:
        pass

    for path, indexes in _ttc_candidates():
        if not Path(path).is_file():
            continue
        for idx in indexes:
            try:
                pdfmetrics.registerFont(TTFont(PRIMARY_FONT_NAME, path, subfontIndex=idx))
            except Exception as exc:
                if verbose:
                    print(f"  font: {path}#{idx} -> register failed ({exc})", file=sys.stderr)
                continue
            if not _font_can_render_chinese(PRIMARY_FONT_NAME):
                if verbose:
                    print(f"  font: {path}#{idx} -> registered but no CJK glyphs", file=sys.stderr)
                continue
            if verbose:
                print(f"  font: {path}#{idx} -> using as {PRIMARY_FONT_NAME}", file=sys.stderr)
            return PRIMARY_FONT_NAME

    if verbose:
        print(f"  font: no system CJK font found, falling back to {FALLBACK_FONT_NAME}", file=sys.stderr)
    return FALLBACK_FONT_NAME


# ---------------------------------------------------------------------------
# Image preparation
# ---------------------------------------------------------------------------

def _crop_to_slide_canvas(
    img: Image.Image, overlay: dict
) -> tuple[Image.Image, dict]:
    """
    Crop the image to `slide_canvas_box` and return (cropped_image,
    adjusted_overlay) where the overlay's positions and image dimensions
    are rewritten to be relative to the crop.

    Why crop: the OCR delivers slide_canvas_box as the rectangle of actual
    slide content, with browser/viewer UI (DocSend toolbar, page counter,
    footer) outside it. By cropping we drop everything outside that rect
    BEFORE rendering, so the right panel shows only the slide proper —
    no toolbar/footer artifacts to inpaint or scar.

    If slide_canvas_box is missing, malformed, or covers the entire image,
    we return the input unchanged.
    """
    canvas = overlay.get("slide_canvas_box")
    if not canvas:
        return img, overlay

    iw, ih = img.size
    overlay_iw = float(overlay.get("image_width") or 0)
    overlay_ih = float(overlay.get("image_height") or 0)
    if overlay_iw <= 0 or overlay_ih <= 0:
        return img, overlay
    sx = iw / overlay_iw
    sy = ih / overlay_ih

    try:
        cx = float(canvas["x"])
        cy = float(canvas["y"])
        cw = float(canvas["width"])
        ch = float(canvas["height"])
    except (KeyError, TypeError, ValueError):
        return img, overlay

    # Clamp to image bounds.
    px0 = max(0, int(round(cx * sx)))
    py0 = max(0, int(round(cy * sy)))
    px1 = min(iw, int(round((cx + cw) * sx)))
    py1 = min(ih, int(round((cy + ch) * sy)))
    if px1 - px0 < 8 or py1 - py0 < 8:
        return img, overlay

    # Trivial case: canvas is essentially the full image — nothing to do.
    if px0 == 0 and py0 == 0 and px1 == iw and py1 == ih:
        return img, overlay

    cropped = img.crop((px0, py0, px1, py1))

    # Build a deep copy of the overlay with positions adjusted to the
    # cropped coord system. Element coordinates are in OCR units
    # (overlay["image_width"]/["image_height"]); after cropping, the new
    # OCR coordinate system has origin at slide_canvas (cx, cy) and
    # dimensions (cw, ch).
    adjusted = json.loads(json.dumps(overlay))
    adjusted["image_width"] = cw
    adjusted["image_height"] = ch
    # The new slide canvas equals the full cropped frame.
    adjusted["slide_canvas_box"] = {"x": 0, "y": 0, "width": cw, "height": ch}

    def _shift(box: dict | None) -> None:
        if not box:
            return
        try:
            box["x"] = box["x"] - cx
            box["y"] = box["y"] - cy
        except (KeyError, TypeError):
            pass

    for el in adjusted.get("elements", []):
        _shift(el.get("render_box"))
        _shift(el.get("tight_glyph_box"))

    # Excluded elements (browser UI) are by definition outside the slide
    # canvas, so they're irrelevant after the crop. Drop them.
    adjusted["excluded_elements"] = []

    return cropped, adjusted


def _fade_image(img: Image.Image, alpha: float) -> Image.Image:
    """
    Return a faded copy of the image: original blended with a white wash
    at `alpha` opacity. alpha=0.85 means the wash is 85% opaque, so the
    underlying slide shows at ~15%. alpha=0 returns the input unchanged.
    """
    if alpha <= 0:
        return img.convert("RGB")
    rgba = img.convert("RGBA")
    wash = Image.new("RGBA", rgba.size, (255, 255, 255, int(255 * alpha)))
    composite = Image.alpha_composite(rgba, wash)
    return composite.convert("RGB")


def _build_rect_mask(img_size: tuple[int, int], overlay: dict, pad: int = 6) -> np.ndarray:
    """
    Build a binary mask of "regions where text might live" — the union
    of every OCR-reported box (with a small pad). Used in both mask
    modes: as the final mask in 'rect' mode, or as a constraint on the
    glyph mask in 'glyph' mode.
    """
    iw, ih = img_size
    overlay_iw = float(overlay.get("image_width") or 0)
    overlay_ih = float(overlay.get("image_height") or 0)
    mask = np.zeros((ih, iw), dtype=np.uint8)
    if overlay_iw <= 0 or overlay_ih <= 0:
        return mask
    sx = iw / overlay_iw
    sy = ih / overlay_ih

    def _stamp(box: dict | None) -> None:
        if not box:
            return
        try:
            x = int(round(box["x"] * sx)) - pad
            y = int(round(box["y"] * sy)) - pad
            w = int(round(box["width"] * sx)) + 2 * pad
            h = int(round(box["height"] * sy)) + 2 * pad
        except (KeyError, TypeError, ValueError):
            return
        x0 = max(0, x); y0 = max(0, y)
        x1 = min(iw, x + w); y1 = min(ih, y + h)
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = 255

    for el in overlay.get("elements", []):
        _stamp(el.get("tight_glyph_box"))
        _stamp(el.get("render_box"))
    for el in overlay.get("excluded_elements", []):
        _stamp(el.get("bounding_box"))
    return mask


def _build_glyph_mask(
    img: Image.Image,
    overlay: dict,
    box_pad: int = 8,
    glyph_dilate: int = 3,
    expand_pct_x: float = 0.25,
    expand_pct_y: float = 0.40,
    expand_min_x: int = 20,
    expand_min_y: int = 14,
) -> np.ndarray:
    """
    Build a mask of just the glyph pixels (not the full rectangles) within
    each OCR-reported text box. The mask is computed PER-BOX with adaptive
    thresholding + polarity detection, which is essential for slides that
    mix dark and light backgrounds across the same deck.

    Per-box pipeline:
        1. Crop the grayscale ROI to box + small pad.
        2. Otsu's method finds the optimal threshold from the local
           histogram, splitting it into two clusters.
        3. Sample the ROI's BORDER pixels to estimate background luminance.
        4. Polarity decision: whichever cluster (above-Otsu or below-Otsu)
           is FARTHER from the background luminance is the text. We mask
           only that cluster.
        5. Sanity check: if the resulting mask covers > 60% of the box,
           something went wrong (e.g., the box has no real text, or the
           histogram isn't bimodal). Drop the mask for that box rather
           than blanket-masking the whole region.
        6. Drop pepper noise (MORPH_OPEN), then dilate slightly for
           antialiased edges.

    This replaces the previous global-threshold approach, which masked
    the dark background AND the light text on dark-bg slides — producing
    the cream/peach blobs in the inpaint-only output.
    """
    iw, ih = img.size
    overlay_iw = float(overlay.get("image_width") or 0)
    overlay_ih = float(overlay.get("image_height") or 0)
    mask = np.zeros((ih, iw), dtype=np.uint8)
    if overlay_iw <= 0 or overlay_ih <= 0:
        return mask
    sx = iw / overlay_iw
    sy = ih / overlay_ih

    bgr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    gray_full = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    def _process_box(box: dict | None) -> None:
        if not box:
            return
        try:
            bx = box["x"] * sx
            by = box["y"] * sy
            bw = box["width"] * sx
            bh = box["height"] * sy
        except (KeyError, TypeError, ValueError):
            return

        # Proportional expansion of the OCR box. Necessary because the
        # OCR box positions are systematically slightly off — typically
        # shifted right (clipping a leading letter) and starting below
        # the actual top of the text (clipping ascenders). Constant pad
        # alone can't catch a 60-pixel x-shift on a wide title; a 25%
        # expansion of a 400px wide title gives 100px on each side, which
        # comfortably covers the error. Smaller boxes get smaller absolute
        # expansion, which is appropriate.
        ex_x = max(int(bw * expand_pct_x), expand_min_x, box_pad)
        ex_y = max(int(bh * expand_pct_y), expand_min_y, box_pad)

        x0 = max(0, int(round(bx)) - ex_x)
        y0 = max(0, int(round(by)) - ex_y)
        x1 = min(iw, int(round(bx + bw)) + ex_x)
        y1 = min(ih, int(round(by + bh)) + ex_y)
        if x1 - x0 < 6 or y1 - y0 < 6:
            return

        roi = gray_full[y0:y1, x0:x1]

        # ----- Source 1: Otsu thresholding on the local histogram -----
        # Catches the glyph CORES (pixels far from background luminance).
        otsu_thresh, otsu_above = cv2.threshold(
            roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        otsu_below = cv2.bitwise_not(otsu_above)

        # Estimate background luminance from the box border.
        border_w = max(1, min(box_pad, 4))
        if roi.shape[0] > 2 * border_w and roi.shape[1] > 2 * border_w:
            border = np.concatenate([
                roi[:border_w, :].ravel(),
                roi[-border_w:, :].ravel(),
                roi[:, :border_w].ravel(),
                roi[:, -border_w:].ravel(),
            ])
            bg_lum = float(np.mean(border))
        else:
            bg_lum = float(np.mean(roi))

        # Polarity: whichever side of Otsu is FARTHER from bg = text.
        above_lum = float(np.mean(roi[otsu_above > 0])) if (otsu_above > 0).any() else 0
        below_lum = float(np.mean(roi[otsu_below > 0])) if (otsu_below > 0).any() else 0
        if abs(above_lum - bg_lum) > abs(below_lum - bg_lum):
            otsu_glyph = otsu_above
        else:
            otsu_glyph = otsu_below

        # Sanity check: drop boxes where Otsu produced a useless split.
        otsu_pct = float((otsu_glyph > 0).sum()) / otsu_glyph.size
        if otsu_pct > 0.60 or otsu_pct < 0.001:
            return

        # ----- Source 2: Sobel gradient magnitude -----
        # Catches the ANTIALIASED FRINGE around glyph edges. These fringe
        # pixels have intermediate luminance between text and bg, so Otsu
        # misses them — but they're exactly what produces the visible
        # "ghost" outline after inpainting because they retain text-color
        # tint. High-gradient pixels are edges, by definition.
        sobel_x = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
        gradient = np.sqrt(sobel_x * sobel_x + sobel_y * sobel_y)
        # Normalize to 0-255 and threshold. The threshold is relative to
        # the local max so it adapts to box contrast.
        gmax = float(gradient.max())
        if gmax > 1e-3:
            edge_mask = ((gradient / gmax) > 0.18).astype(np.uint8) * 255
        else:
            edge_mask = np.zeros_like(otsu_glyph)

        # Union: glyph cores + AA fringe.
        glyph = cv2.bitwise_or(otsu_glyph, edge_mask)

        # Cleanup: kill pepper noise.
        glyph = cv2.morphologyEx(glyph, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        # Morphological close to bridge tiny gaps within glyph strokes.
        glyph = cv2.morphologyEx(glyph, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        # Dilate for any remaining edge slop.
        if glyph_dilate > 0:
            ksize = glyph_dilate * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
            glyph = cv2.dilate(glyph, kernel, iterations=1)

        # Final sanity check after edge expansion.
        if (glyph > 0).sum() > glyph.size * 0.8:
            # Edge detection went haywire (very busy box) — fall back to
            # otsu-only mask which had passed the earlier sanity check.
            glyph = otsu_glyph
            if glyph_dilate > 0:
                glyph = cv2.dilate(
                    glyph,
                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (glyph_dilate * 2 + 1,) * 2),
                    iterations=1,
                )

        # Stamp into the global mask.
        mask[y0:y1, x0:x1] = cv2.bitwise_or(mask[y0:y1, x0:x1], glyph)

    for el in overlay.get("elements", []):
        # Use render_box (the larger of the two boxes — per the OCR prompt
        # it's "the layout region intended for translated text rendering"
        # and includes the full extent of the original text). The smaller
        # tight_glyph_box can be too tight on the left edge and clip the
        # leading letter of titles like "Anduril Industries" (visible as
        # an "And" remnant after inpainting). render_box gives Otsu more
        # background context to work with too, improving the polarity
        # decision and AA-edge capture.
        box = el.get("render_box") or el.get("tight_glyph_box")
        _process_box(box)
    for el in overlay.get("excluded_elements", []):
        _process_box(el.get("bounding_box"))

    return mask


def _remove_text(
    img: Image.Image,
    overlay: dict,
    pad: int = 6,
    dilate_px: int = 4,
    inpaint_radius: int = 3,
    algo: str = "telea",
    mask_mode: str = "glyph",
) -> Image.Image:
    """
    Inpaint over the original English text, leaving the slide's visual
    context (photos, charts, layout) intact.

    Two mask modes:
        - 'glyph' (default): mask only the glyph pixels detected via
          thresholding inside each OCR box. Produces thin
          character-shaped holes that TELEA fills naturally.
        - 'rect': mask the full OCR rectangles. Faster, but produces
          blurry patches when the background isn't uniform.

    Defaults are tuned for the 'glyph' mode: small inpaint radius (3),
    TELEA algorithm (fast and best for thin gaps).
    """
    iw, ih = img.size
    overlay_iw = float(overlay.get("image_width") or 0)
    overlay_ih = float(overlay.get("image_height") or 0)
    if overlay_iw <= 0 or overlay_ih <= 0:
        return img.convert("RGB")

    if mask_mode == "glyph":
        mask = _build_glyph_mask(
            img, overlay, box_pad=pad, glyph_dilate=max(1, dilate_px // 2)
        )
    else:
        mask = _build_rect_mask((iw, ih), overlay, pad=pad)
        if dilate_px > 0:
            ksize = max(1, dilate_px * 2 + 1)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
            mask = cv2.dilate(mask, kernel, iterations=1)

    if not mask.any():
        return img.convert("RGB")

    rgb = np.asarray(img.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    # Algorithm choice:
    # - INPAINT_TELEA (Fast Marching, default): excellent for thin
    #   glyph-shaped holes; fills small gaps very cleanly with surrounding
    #   pixel propagation. This is what we want for glyph masking.
    # - INPAINT_NS (Navier-Stokes): slower; better on large rect masks
    #   where TELEA leaves streaks. Use with mask_mode='rect'.
    flag = cv2.INPAINT_NS if algo == "ns" else cv2.INPAINT_TELEA
    cleaned_bgr = cv2.inpaint(bgr, mask, inpaintRadius=inpaint_radius, flags=flag)

    cleaned_rgb = cv2.cvtColor(cleaned_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(cleaned_rgb)


def _structural_image(img_path: Path, edge_intensity: float = 0.5) -> Image.Image:
    """
    Render a "blueprint" version of the slide: structural edges visible
    on a near-white background, with all color and texture suppressed.

    Pipeline:
        1. Convert to grayscale.
        2. Run a Sobel-style edge filter (PIL.FIND_EDGES is a 3x3 Sobel).
        3. Threshold + invert so edges become DARK lines on a LIGHT canvas.
        4. Blend with white at `edge_intensity` so we get visible-but-muted
           structure rather than harsh black lines.

    This is the OpenCV-style processing we hinted at, done with stock PIL
    so we don't pull in opencv-python for one operation.
    """
    img = Image.open(img_path).convert("L")
    edges = img.filter(ImageFilter.FIND_EDGES)
    # Slight blur before thresholding helps smooth jaggy raster edges.
    edges = edges.filter(ImageFilter.GaussianBlur(radius=0.6))
    arr = np.asarray(edges, dtype=np.uint8)
    # Threshold: any edge response > 18 counts as a structural line.
    mask = arr > 18
    # Build the output: pure white where there's no edge; edge intensity
    # mapped to luminance where there is.
    out = np.full_like(arr, 255, dtype=np.uint8)
    edge_strength = (arr.astype(np.float32) / 255.0) * edge_intensity
    edge_lum = (255.0 * (1.0 - edge_strength)).clip(0, 255).astype(np.uint8)
    out = np.where(mask, edge_lum, out)
    grey = Image.fromarray(out, mode="L")
    return grey.convert("RGB")


def _local_luminance(
    img: Image.Image,
    bx: float,
    by: float,
    bw: float,
    bh: float,
    overlay_iw: float,
    overlay_ih: float,
) -> float:
    """
    Return the mean luminance (0..1) of `img` over the given OCR-coord
    region. Used to pick a high-contrast text color per element.
    """
    iw, ih = img.size
    if overlay_iw <= 0 or overlay_ih <= 0:
        return 1.0
    sx = iw / overlay_iw
    sy = ih / overlay_ih
    x0 = max(0, int(bx * sx))
    y0 = max(0, int(by * sy))
    x1 = min(iw, int((bx + bw) * sx))
    y1 = min(ih, int((by + bh) * sy))
    if x1 <= x0 or y1 <= y0:
        return 1.0
    region = img.crop((x0, y0, x1, y1)).convert("L")
    arr = np.asarray(region, dtype=np.float32)
    return float(arr.mean()) / 255.0


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _alignment_to_reportlab(value: str) -> int:
    return {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}.get(value, TA_LEFT)


def _draw_image_into_panel(
    canvas: Canvas,
    pil_img: Image.Image,
    panel_x: float,
    panel_y: float,
    panel_w: float,
    panel_h: float,
) -> tuple[float, float, float, float]:
    """
    Draw `pil_img` scaled to fit the panel, centered. Returns
    (image_x, image_y_top, draw_w, draw_h) — the drawn image's top-left
    in PDF coords and its rendered dimensions in points.

    NOTE: we deliberately return draw_w/draw_h instead of a single scale.
    Overlay coordinate scaling needs to map from the OCR's claimed image
    dimensions (overlay["image_width"]/["image_height"]) to the rendered
    panel dimensions, NOT from the PIL-loaded file's pixel dimensions.
    Those two can disagree — the model sometimes reports smaller dims
    than the actual file — and using the wrong basis bunches every
    element in the upper-left corner of the panel.
    """
    iw, ih = pil_img.size
    scale = min(panel_w / iw, panel_h / ih)
    draw_w = iw * scale
    draw_h = ih * scale

    image_x = panel_x + (panel_w - draw_w) / 2
    panel_top = panel_y + panel_h
    image_y_top = panel_top - (panel_h - draw_h) / 2

    image_y_bottom = image_y_top - draw_h
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=85, optimize=True)
    buf.seek(0)
    canvas.drawImage(
        ImageReader(buf),
        image_x,
        image_y_bottom,
        width=draw_w,
        height=draw_h,
        mask="auto",
    )
    return image_x, image_y_top, draw_w, draw_h


def _build_paragraph(
    zh: str, font_name: str, font_pt: float, alignment: int, color
) -> Paragraph:
    style = ParagraphStyle(
        "zh",
        fontName=font_name,
        fontSize=font_pt,
        leading=font_pt * 1.18,
        textColor=color,
        alignment=alignment,
        wordWrap="CJK",  # Chinese can break between any two chars.
    )
    safe = html.escape(zh).replace("\n", "<br/>")
    return Paragraph(safe, style)


def _draw_para_with_halo(
    canvas: Canvas,
    zh: str,
    font_name: str,
    font_pt: float,
    alignment: int,
    text_color,
    halo_color,
    rl_x: float,
    draw_y: float,
    rl_w: float,
) -> None:
    """
    Draw the paragraph twice: first a halo (offset slightly in 4 directions)
    to give the text a soft outline that improves contrast against any
    background, then the main text on top.

    Cheap and effective vs. full text-stroke rendering, which Paragraph
    doesn't expose. The 4-direction halo costs 4 extra para draws per
    element, but each element is small so total overhead is minimal.
    """
    halo_para = _build_paragraph(zh, font_name, font_pt, alignment, halo_color)
    # We only need wrap once — same width and font produces the same layout.
    halo_para.wrap(rl_w, 100000)

    offset = max(font_pt * 0.07, 0.6)
    for dx, dy in ((-offset, 0), (offset, 0), (0, -offset), (0, offset)):
        # Re-instantiate because Paragraph caches state from drawOn.
        p = _build_paragraph(zh, font_name, font_pt, alignment, halo_color)
        p.wrap(rl_w, 100000)
        p.drawOn(canvas, rl_x + dx, draw_y + dy)

    main_para = _build_paragraph(zh, font_name, font_pt, alignment, text_color)
    main_para.wrap(rl_w, 100000)
    main_para.drawOn(canvas, rl_x, draw_y)


def _draw_zh_overlay(
    canvas: Canvas,
    overlay: dict,
    image_x: float,
    image_y_top: float,
    draw_w: float,
    draw_h: float,
    cjk_font_name: str,
    show_highlight: bool,
    backdrop_for_sampling: Image.Image | None = None,
    debug: bool = False,
) -> int:
    """
    Render every translated element on top of the faded image. Returns
    the count of elements drawn.

    Coordinate normalization: render_box values are in the OCR's coordinate
    system (image_width / image_height as reported by the model). We scale
    those to the rendered image's dimensions in points, which may differ
    from the PIL-loaded file's pixel dimensions if the model reported
    different numbers.

    We do NOT use reportlab's Frame here. Frame.addFromList silently
    drops paragraphs that don't fit and returns without raising — earlier
    renders looked "successful" while producing no visible text. Instead
    we measure with Paragraph.wrap, shrink the font until it fits (or hit
    a floor), and always drawOn the result. Overflow is acceptable,
    invisibility is not.
    """
    overlay_iw = float(overlay.get("image_width") or 0)
    overlay_ih = float(overlay.get("image_height") or 0)
    if overlay_iw <= 0 or overlay_ih <= 0:
        # Fall back: assume render_boxes are already in PDF-points-ish
        # space. Effectively scale=1.0; the result will look bad but
        # won't crash.
        if debug:
            print(
                f"  WARN: overlay missing/invalid image_width/image_height "
                f"(got {overlay.get('image_width')!r} x {overlay.get('image_height')!r}); "
                f"falling back to 1:1 scaling",
                file=sys.stderr,
            )
        scale_x = scale_y = 1.0
    else:
        scale_x = draw_w / overlay_iw
        scale_y = draw_h / overlay_ih

    if debug:
        print(
            f"  overlay coord space: {overlay_iw:.0f} x {overlay_ih:.0f} "
            f"-> drawn {draw_w:.1f} x {draw_h:.1f} (scale_x={scale_x:.3f}, scale_y={scale_y:.3f})",
            file=sys.stderr,
        )

    drawn = 0
    for el in overlay.get("elements", []):
        zh = (el.get("zh_text") or "").strip()
        if not zh:
            continue

        box = el.get("render_box") or el.get("tight_glyph_box")
        if not box:
            continue

        try:
            bx = float(box["x"])
            by = float(box["y"])
            bw = float(box["width"])
            bh = float(box["height"])
        except (KeyError, TypeError, ValueError):
            continue

        # Convert overlay-coord box -> PDF pts (PDF origin = bottom-left).
        rl_x = image_x + bx * scale_x
        rl_top = image_y_top - by * scale_y
        rl_w = max(bw * scale_x, 4.0)
        rl_h = max(bh * scale_y, 6.0)
        rl_y_bottom = rl_top - rl_h

        if debug:
            print(
                f"    {el.get('id','?')}: src=({bx:.0f},{by:.0f},{bw:.0f}x{bh:.0f}) "
                f"-> pdf=({rl_x:.1f},{rl_y_bottom:.1f},{rl_w:.1f}x{rl_h:.1f}) "
                f"text={zh[:30]!r}",
                file=sys.stderr,
            )
            # Outline the rect we're about to draw into so we can see
            # whether positions look right.
            canvas.saveState()
            canvas.setStrokeColorRGB(1.0, 0.0, 0.0)
            canvas.setLineWidth(0.4)
            canvas.rect(rl_x, rl_y_bottom, rl_w, rl_h, stroke=1, fill=0)
            canvas.restoreState()

        # Pick text color & halo for this element by sampling the local
        # luminance of the backdrop image at this region. Light area ->
        # dark text + light halo. Dark area -> light text + dark halo.
        if backdrop_for_sampling is not None:
            lum = _local_luminance(
                backdrop_for_sampling, bx, by, bw, bh, overlay_iw, overlay_ih
            )
        else:
            lum = 1.0  # assume light backdrop
        if lum < DARK_BG_LUMINANCE_THRESHOLD:
            text_color, halo_color = ZH_LIGHT_COLOR, ZH_HALO_DARK
        else:
            text_color, halo_color = ZH_DARK_COLOR, ZH_HALO_LIGHT

        # Initial font size: scale the OCR-estimated px size into points,
        # using the y-axis scale (font sizes track vertical typography).
        font_px = el.get("font_size_estimate_px") or 14
        try:
            font_pt = max(float(font_px) * scale_y, 5.5)
        except (TypeError, ValueError):
            font_pt = 10.0

        alignment = _alignment_to_reportlab(el.get("alignment", "left"))

        # Measure with one paragraph; shrink font until it fits the box.
        para = _build_paragraph(zh, cjk_font_name, font_pt, alignment, text_color)
        try:
            _, para_h = para.wrap(rl_w, 100000)
        except Exception:
            para_h = rl_h * 2

        shrink_attempts = 0
        while para_h > rl_h and font_pt > 5.5 and shrink_attempts < 8:
            font_pt *= 0.85
            para = _build_paragraph(zh, cjk_font_name, font_pt, alignment, text_color)
            try:
                _, para_h = para.wrap(rl_w, 100000)
            except Exception:
                para_h = rl_h * 2
                break
            shrink_attempts += 1

        # Optional cream rectangle (off by default; --highlight re-enables).
        if show_highlight:
            highlight_h = min(rl_h, max(para_h, font_pt * 1.2))
            canvas.saveState()
            canvas.setFillColor(ZH_HIGHLIGHT_COLOR)
            canvas.rect(
                rl_x + 1,
                rl_top - highlight_h - 1,
                rl_w - 2,
                highlight_h,
                fill=1,
                stroke=0,
            )
            canvas.restoreState()

        # Top-aligned within the render_box. Overflow is allowed.
        draw_y = rl_top - para_h
        try:
            _draw_para_with_halo(
                canvas, zh, cjk_font_name, font_pt, alignment,
                text_color, halo_color, rl_x, draw_y, rl_w,
            )
            drawn += 1
            continue
        except Exception:
            pass

        # Last-resort fallback: stamp the raw text with drawString.
        canvas.saveState()
        try:
            canvas.setFont(cjk_font_name, max(font_pt, 6.0))
        except Exception:
            canvas.setFont(FALLBACK_FONT_NAME, max(font_pt, 6.0))
        canvas.setFillColor(text_color)
        canvas.drawString(rl_x + 1, rl_y_bottom + 2, zh[:120])
        canvas.restoreState()
        drawn += 1
    return drawn


def _draw_page_header(canvas: Canvas, image_path: Path, page_num: int, total: int) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#666666"))
    canvas.drawString(MARGIN, PAGE_HEIGHT - MARGIN + 4, image_path.name)
    canvas.drawCentredString(
        PAGE_WIDTH / 2,
        PAGE_HEIGHT - MARGIN + 4,
        f"{page_num} / {total}",
    )
    canvas.drawRightString(
        PAGE_WIDTH - MARGIN,
        PAGE_HEIGHT - MARGIN + 4,
        "Original  |  Simplified Chinese overlay",
    )
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Top-level rendering
# ---------------------------------------------------------------------------

def render_pdf(
    pairs: list[tuple[Path, Path]],
    out_path: Path,
    fade_alpha: float = 0.0,
    show_highlight: bool = False,
    inpaint_text: bool = True,
    aggressive_inpaint: bool = False,
    inpaint_algo: str = "telea",
    mask_mode: str = "glyph",
    draw_chinese: bool = True,
    crop_to_slide: bool = True,
    verbose: bool = True,
    debug: bool = False,
) -> None:
    """
    pairs: list of (image_path, overlay_json_path).
    out_path: where to write the PDF.
    fade_alpha: opacity of the white wash on the right panel (0..1).
    show_highlight: draw a subtle cream highlight rect behind each translation.
    """
    if verbose:
        print(f"Registering CJK fonts...", file=sys.stderr)
    cjk_font = register_fonts(verbose=verbose)
    if verbose:
        print(f"  -> using font: {cjk_font}", file=sys.stderr)

    canvas = Canvas(str(out_path), pagesize=landscape(letter))
    canvas.setTitle(f"Slide translations: {out_path.stem}")

    total = len(pairs)
    for idx, (image_path, overlay_path) in enumerate(pairs, 1):
        try:
            overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARN: skipping {image_path.name}: {exc}", file=sys.stderr)
            continue

        original_full = Image.open(image_path).convert("RGB")

        # Crop both panels to the slide_canvas_box so we never render the
        # browser/viewer chrome (DocSend toolbar, page counter, footer).
        # This eliminates the need to inpaint excluded_elements and removes
        # the horizontal "scars" those left at the top/bottom of the right
        # panel.
        if crop_to_slide:
            display_img, panel_overlay = _crop_to_slide_canvas(original_full, overlay)
        else:
            display_img, panel_overlay = original_full, overlay

        # Build the right-panel backdrop: optionally inpaint over the original
        # English text (using the adjusted box positions as a mask), then
        # optionally apply a light white wash on top.
        if inpaint_text:
            if aggressive_inpaint:
                cleaned = _remove_text(
                    display_img, panel_overlay,
                    pad=14, dilate_px=14, inpaint_radius=8,
                    algo=inpaint_algo, mask_mode=mask_mode,
                )
            else:
                cleaned = _remove_text(
                    display_img, panel_overlay,
                    algo=inpaint_algo, mask_mode=mask_mode,
                )
        else:
            cleaned = display_img
        backdrop = _fade_image(cleaned, alpha=fade_alpha)

        _draw_page_header(canvas, image_path, idx, total)

        _draw_image_into_panel(
            canvas, display_img, LEFT_PANEL_X, PANEL_Y, PANEL_WIDTH, PANEL_HEIGHT
        )

        image_x, image_y_top, draw_w, draw_h = _draw_image_into_panel(
            canvas, backdrop, RIGHT_PANEL_X, PANEL_Y, PANEL_WIDTH, PANEL_HEIGHT
        )
        if debug:
            print(
                f"\n[{idx}/{total}] {image_path.name}  pil={original_full.size}"
                f" -> display={display_img.size}, "
                f"overlay_dims=({panel_overlay.get('image_width')!r}x{panel_overlay.get('image_height')!r}), "
                f"drawn_pt=({draw_w:.1f}x{draw_h:.1f}), "
                f"inpaint={inpaint_text}, crop={crop_to_slide}, fade={fade_alpha}",
                file=sys.stderr,
            )
        if draw_chinese:
            n_drawn = _draw_zh_overlay(
                canvas, panel_overlay, image_x, image_y_top, draw_w, draw_h,
                cjk_font, show_highlight,
                backdrop_for_sampling=backdrop,
                debug=debug,
            )
        else:
            n_drawn = 0
            if verbose:
                print(
                    "  (--no-overlay: skipping Chinese rendering)",
                    file=sys.stderr,
                )
        if verbose:
            print(
                f"  [{idx}/{total}] {image_path.name}: {n_drawn} translations drawn",
                file=sys.stderr,
            )

        canvas.showPage()

    canvas.save()


def discover_pairs(directory: Path) -> list[tuple[Path, Path]]:
    """Find images with sidecar `<stem>_overlay.json` in `directory`."""
    pairs: list[tuple[Path, Path]] = []
    for child in sorted(directory.iterdir()):
        if not child.is_file() or child.suffix.lower() not in IMAGE_EXTS:
            continue
        overlay = directory / f"{child.stem}_overlay.json"
        if overlay.is_file():
            pairs.append((child, overlay))
    return pairs


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Re-render the bilingual PDF from existing image + overlay JSON pairs."
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing slide images and *_overlay.json files.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output PDF path. Default: <dir>/<dir_name>_translations.pdf",
    )
    parser.add_argument(
        "--fade",
        type=float,
        default=0.0,
        help="Right-panel white-wash opacity (0..1). 0 (default) = no fade — "
             "the right panel shows the original visuals at full strength after "
             "text inpainting. Increase to mute the backdrop and make the "
             "Chinese pop more (try 0.2 for a light wash).",
    )
    parser.add_argument(
        "--no-inpaint",
        action="store_true",
        help="Skip OpenCV text inpainting. With this flag the right panel shows "
             "the original image (with English text still visible), faded by "
             "--fade. Use if inpainting introduces artifacts on a particular deck "
             "or if you want the legacy faded-overlay look.",
    )
    parser.add_argument(
        "--aggressive-inpaint",
        action="store_true",
        help="Use much larger pad/dilation/radius for text removal (pad=14, "
             "dilate=14, radius=8). Use this when you see English text bleeding "
             "through behind the Chinese on multi-line paragraphs. Trade-off: "
             "slightly more smudging of photo content adjacent to text.",
    )
    parser.add_argument(
        "--no-crop",
        action="store_true",
        help="Don't crop panels to slide_canvas_box. By default both panels "
             "show only the slide content (browser/viewer UI removed). Pass "
             "this if you want the original screenshots, toolbars and all.",
    )
    parser.add_argument(
        "--inpaint-algo",
        choices=("telea", "ns"),
        default="telea",
        help="cv2 inpainting algorithm. With glyph mask mode (default), "
             "'telea' (Fast Marching) is ideal — it fills thin "
             "character-shaped holes cleanly from surrounding pixels. "
             "Switch to 'ns' (Navier-Stokes) only if using --mask-mode rect "
             "and the backgrounds are photographic.",
    )
    parser.add_argument(
        "--mask-mode",
        choices=("glyph", "rect"),
        default="glyph",
        help="How to build the inpainting mask. 'glyph' (default) thresholds "
             "to find the actual glyph pixels inside each OCR box and masks "
             "only those — produces thin character-shaped holes that "
             "INPAINT_TELEA fills naturally with no smearing. 'rect' masks "
             "the full OCR rectangle — faster but produces blurry patches "
             "on photographic backgrounds.",
    )
    parser.add_argument(
        "--no-overlay",
        action="store_true",
        help="Skip the Chinese text drawing on the right panel. Use to "
             "evaluate text removal quality in isolation — without the "
             "Chinese covering up the inpainted regions you can see "
             "directly how clean the cleanup is.",
    )
    parser.add_argument(
        "--highlight",
        action="store_true",
        help="Paint a cream rectangle behind each translation. Off by default; "
             "the adaptive-color text plus halo usually handles contrast. Enable "
             "for extra visual separation between text blocks.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-page progress output.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Draw red outlines around every render_box and print the OCR coord -> "
             "PDF coord transform per element. Use this when overlay positions look "
             "wrong; the outlines reveal exactly where the renderer thinks each box is.",
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"ERROR: not a directory: {args.directory}", file=sys.stderr)
        return 1
    if not (0.0 <= args.fade <= 1.0):
        print(f"ERROR: --fade must be in [0, 1] (got {args.fade})", file=sys.stderr)
        return 2

    pairs = discover_pairs(args.directory)
    if not pairs:
        print(
            f"ERROR: no image+overlay pairs found in {args.directory}. "
            f"Run scripts/batch_translate.py first to generate *_overlay.json files.",
            file=sys.stderr,
        )
        return 1

    out_path = args.out or args.directory / f"{args.directory.name}_translations.pdf"
    render_pdf(
        pairs,
        out_path,
        fade_alpha=args.fade,
        show_highlight=args.highlight,
        inpaint_text=not args.no_inpaint,
        aggressive_inpaint=args.aggressive_inpaint,
        inpaint_algo=args.inpaint_algo,
        mask_mode=args.mask_mode,
        draw_chinese=not args.no_overlay,
        crop_to_slide=not args.no_crop,
        verbose=not args.quiet,
        debug=args.debug,
    )
    print(f"Wrote {out_path} ({len(pairs)} page(s))")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
