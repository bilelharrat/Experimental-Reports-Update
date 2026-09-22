/**
 * Fitting a rendered Word page (docx-preview) to the viewer's width, the way
 * Preview's "Zoom to Fit" does: the page keeps its own layout — tables,
 * columns, page breaks — and only its scale changes, so a memo reads the same
 * at any window size, just larger when there is room.
 */

const PX_PER_UNIT = { pt: 96 / 72, in: 96, cm: 96 / 2.54, mm: 96 / 25.4, px: 1 };

/** A page's own width in CSS px, read from docx-preview's inline style. */
export function docxPageWidth(section, fallback = 816) {
  const match = String(section?.style?.width || "")
    .trim()
    .match(/^([\d.]+)(pt|in|cm|mm|px)$/);
  if (match) {
    const px = Number(match[1]) * PX_PER_UNIT[match[2]];
    if (Number.isFinite(px) && px > 0) return px;
  }
  return fallback;
}

/**
 * The zoom that fits a page `pageWidth` wide into `available` px. A narrow
 * window shrinks the page rather than scroll it sideways; a very wide one
 * stops at `max`, past which a memo's type gets poster-sized.
 */
export function fitZoom(available, pageWidth, { min = 0.5, max = 1.75 } = {}) {
  if (!(available > 0) || !(pageWidth > 0)) return 1;
  const zoom = Math.min(max, Math.max(min, available / pageWidth));
  return Math.floor(zoom * 1000) / 1000;
}

// Zoom picked by hand: the viewer's − and + walk these, the way Preview and
// the browser step, and a pinch lands anywhere between the ends.
export const ZOOM_MIN = 0.5;
export const ZOOM_MAX = 3;
const ZOOM_STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];

export function clampZoom(value) {
  const zoom = Number(value);
  if (!Number.isFinite(zoom)) return 1;
  return Math.round(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom)) * 1000) / 1000;
}

/** The next step up (`direction` > 0) or down from `current`. */
export function nextZoomStep(current, direction) {
  const zoom = clampZoom(current);
  if (direction > 0) return ZOOM_STEPS.find((step) => step > zoom + 0.001) ?? ZOOM_MAX;
  return [...ZOOM_STEPS].reverse().find((step) => step < zoom - 0.001) ?? ZOOM_MIN;
}
