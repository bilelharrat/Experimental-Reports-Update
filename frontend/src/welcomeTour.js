import { ref } from "vue";

// Bump when the tour's content changes enough that returning users should
// see it again, the way iOS re-shows "What's New" after a major update.
// v2: the tour stopped describing the app from behind a modal and now walks it.
export const WELCOME_TOUR_VERSION = 2;
export const WELCOME_TOUR_KEY = "bsh.welcomeTourSeen";

export const welcomeTourOpen = ref(false);

/**
 * The guided tour.
 *
 * Every step after the welcome card drives the app to the screen it is talking
 * about and spotlights the real control there, the way Apple's in-app tours
 * work (Final Cut and Logic for iPad, Freeform, Swift Playgrounds, Tips): the
 * app moves under the callout instead of the tour describing it from a modal.
 *
 * - `route`   vue-router target for the step; omitted means "stay put".
 * - `target`  CSS selector for the element to spotlight. Missing targets are
 *             not an error: the step falls back to a centered callout over the
 *             real screen (this is what happens on narrow windows where the
 *             sidebar is a drawer).
 * - `placement` preferred side of the target for the callout.
 */
export const WELCOME_TOUR_STEPS = [
  { id: "welcome", kind: "hero" },
  {
    id: "home",
    route: { name: "home" },
    target: '[data-tour="home-search"]',
    placement: "bottom",
  },
  {
    id: "research",
    // The company list IS the research desk now — the nav row that used to
    // open a second copy of this list is gone.
    route: { name: "home" },
    target: '[data-tour="companies"]',
    placement: "right",
  },
  {
    id: "memo",
    route: { name: "reports" },
    target: '[data-tour="nav-reports"]',
    placement: "right",
  },
  {
    id: "markets",
    route: { name: "market-radar" },
    target: '[data-tour="nav-market"]',
    placement: "right",
  },
  {
    id: "tracking",
    route: { name: "tracking" },
    target: '[data-tour="nav-tracking"]',
    placement: "right",
  },
  {
    id: "warren",
    target: '[data-tour="warren"]',
    placement: "bottom",
  },
];

function readSeenVersion() {
  try {
    const raw = window.localStorage.getItem(WELCOME_TOUR_KEY);
    const version = Number.parseInt(raw ?? "", 10);
    return Number.isFinite(version) ? version : 0;
  } catch {
    return 0;
  }
}

function writeSeenVersion(version) {
  try {
    window.localStorage.setItem(WELCOME_TOUR_KEY, String(version));
  } catch {
    // localStorage unavailable — the tour simply shows again next time.
  }
}

export function shouldShowWelcomeTour() {
  return readSeenVersion() < WELCOME_TOUR_VERSION;
}

export function openWelcomeTour() {
  welcomeTourOpen.value = true;
}

/** First sign-in on this browser (or a newer tour): open it once. */
export function presentWelcomeTourIfNeeded() {
  if (welcomeTourOpen.value || !shouldShowWelcomeTour()) return false;
  welcomeTourOpen.value = true;
  return true;
}

/** Closing by any route counts as seen — a tour that nags is worse than none. */
export function closeWelcomeTour() {
  welcomeTourOpen.value = false;
  writeSeenVersion(WELCOME_TOUR_VERSION);
}
