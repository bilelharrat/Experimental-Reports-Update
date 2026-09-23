// How wide Warren's rail is.
//
// The Mac app lets you drag its side panel (MacRootView.swift:
// `minWidth: 340, idealWidth: 400, maxWidth: 580`), so the web twin drags
// too. The cap is higher here because a browser window is usually wider
// than a Mac split view, and a long answer or an attached document reads
// badly in a 392px column.

export const COPILOT_MIN_WIDTH = 340;
export const COPILOT_MAX_WIDTH = 880;
export const COPILOT_DEFAULT_WIDTH = 392;
export const COPILOT_WIDE_WIDTH = 720;

// Never past this share of the window: the desk behind it still has to be
// usable, which is the whole point of a rail.
const MAX_VIEWPORT_SHARE = 0.6;

const KEY = "bsh.copilot.width";

export function clampCopilotWidth(value) {
  const width = Math.round(Number(value));
  if (!Number.isFinite(width)) return COPILOT_DEFAULT_WIDTH;
  return Math.min(COPILOT_MAX_WIDTH, Math.max(COPILOT_MIN_WIDTH, width));
}

/** The widest this window can give the rail. */
export function fitCopilotWidth(value, viewportWidth) {
  const room = Math.round((Number(viewportWidth) || 0) * MAX_VIEWPORT_SHARE);
  const ceiling = Math.max(COPILOT_MIN_WIDTH, room || COPILOT_MAX_WIDTH);
  return Math.min(clampCopilotWidth(value), ceiling);
}

export function readCopilotWidth() {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? clampCopilotWidth(raw) : COPILOT_DEFAULT_WIDTH;
  } catch {
    // Private windows and blocked site data: the default is fine.
    return COPILOT_DEFAULT_WIDTH;
  }
}

export function writeCopilotWidth(value) {
  try {
    window.localStorage.setItem(KEY, String(clampCopilotWidth(value)));
  } catch {
    // Not worth failing a drag over.
  }
}
