import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive } from "vue";
import WelcomeTour from "../src/components/WelcomeTour.vue";
import {
  WELCOME_TOUR_KEY,
  WELCOME_TOUR_STEPS,
  WELCOME_TOUR_VERSION,
  closeWelcomeTour,
  presentWelcomeTourIfNeeded,
  shouldShowWelcomeTour,
  welcomeTourOpen,
} from "../src/welcomeTour.js";

const push = vi.fn(() => Promise.resolve());
const mockRoute = reactive({ fullPath: "/" });

vi.mock("vue-router", () => ({
  useRouter: () => ({ push }),
  useRoute: () => mockRoute,
}));

/**
 * The tour measures real elements, and jsdom gives everything a zero-sized
 * rect. Plant a control the tour can find and give it a believable box.
 */
function plantTarget(selector, box = { top: 120, left: 12, width: 190, height: 34 }) {
  const el = document.createElement("div");
  const [, attr, value] = selector.match(/\[([\w-]+)="([^"]+)"\]/);
  el.setAttribute(attr, value);
  el.getBoundingClientRect = () => ({
    ...box,
    right: box.left + box.width,
    bottom: box.top + box.height,
    x: box.left,
    y: box.top,
    toJSON: () => ({}),
  });
  document.body.appendChild(el);
  return el;
}

function mountTour(open = true) {
  return mount(WelcomeTour, { props: { open }, attachTo: document.body });
}

function title() {
  return document.body.querySelector("[data-testid='welcome-tour-title']")?.textContent.trim();
}

function spotlight() {
  return document.body.querySelector("[data-testid='welcome-tour-spotlight']");
}

function click(testId) {
  document.body.querySelector(`[data-testid='${testId}']`).click();
}

/** Continue, then let the step navigate and find its control. */
async function next() {
  click("welcome-tour-next");
  await flushPromises();
  await flushPromises();
}

describe("welcome tour state", () => {
  beforeEach(() => {
    window.localStorage.clear();
    welcomeTourOpen.value = false;
  });

  it("shows once on a fresh browser and not again after closing", () => {
    expect(shouldShowWelcomeTour()).toBe(true);
    expect(presentWelcomeTourIfNeeded()).toBe(true);
    expect(welcomeTourOpen.value).toBe(true);
    // A second sign-in while it is open must not reset it.
    expect(presentWelcomeTourIfNeeded()).toBe(false);

    closeWelcomeTour();
    expect(welcomeTourOpen.value).toBe(false);
    expect(window.localStorage.getItem(WELCOME_TOUR_KEY)).toBe(String(WELCOME_TOUR_VERSION));
    expect(shouldShowWelcomeTour()).toBe(false);
    expect(presentWelcomeTourIfNeeded()).toBe(false);
  });

  it("re-shows when the tour version is newer than the one seen", () => {
    window.localStorage.setItem(WELCOME_TOUR_KEY, String(WELCOME_TOUR_VERSION - 1));
    expect(shouldShowWelcomeTour()).toBe(true);
    window.localStorage.setItem(WELCOME_TOUR_KEY, "garbage");
    expect(shouldShowWelcomeTour()).toBe(true);
  });

  it("gives every step after the welcome card a screen to visit", () => {
    const [hero, ...walk] = WELCOME_TOUR_STEPS;
    expect(hero.kind).toBe("hero");
    expect(walk.length).toBeGreaterThan(0);
    for (const entry of walk) {
      // A step either drives the app somewhere or points at something here.
      expect(Boolean(entry.route) || Boolean(entry.target)).toBe(true);
      expect(entry.target).toBeTruthy();
    }
  });
});

describe("WelcomeTour", () => {
  let wrapper;

  beforeEach(() => {
    push.mockClear();
    mockRoute.fullPath = "/";
  });

  afterEach(() => {
    wrapper?.unmount();
    document.body.innerHTML = "";
  });

  it("renders nothing while closed", () => {
    wrapper = mountTour(false);
    expect(document.body.querySelector("[data-testid='welcome-tour']")).toBeNull();
  });

  it("opens on the welcome card without moving the app", async () => {
    wrapper = mountTour();
    await flushPromises();
    expect(title()).toBe("Welcome to BSH Research Center");
    expect(push).not.toHaveBeenCalled();
    expect(spotlight()).toBeNull();
    expect(document.body.querySelector("[data-testid='welcome-tour-back']")).toBeNull();

    const dots = document.body.querySelectorAll(".welcome-tour-dot");
    expect(dots.length).toBe(WELCOME_TOUR_STEPS.length);
    expect(dots[0].getAttribute("aria-selected")).toBe("true");
  });

  it("walks the app to each feature it explains and spotlights its control", async () => {
    plantTarget('[data-tour="home-search"]', { top: 180, left: 300, width: 520, height: 46 });
    plantTarget('[data-tour="nav-research-desk"]');
    plantTarget('[data-tour="nav-reports"]');
    plantTarget('[data-tour="nav-market"]');
    plantTarget('[data-tour="nav-tracking"]');
    plantTarget('[data-tour="warren"]', { top: 10, left: 900, width: 110, height: 30 });

    wrapper = mountTour();
    await flushPromises();

    await next();
    expect(title()).toBe("Start with a company");
    expect(push).toHaveBeenLastCalledWith({ name: "home" });
    // The real search field is cut out of the dim, not drawn in the card.
    expect(spotlight()).not.toBeNull();
    expect(spotlight().style.left).toBe("292px"); // 300 less the 8px halo

    await next();
    expect(title()).toBe("The Research Desk");
    expect(push).toHaveBeenLastCalledWith({ name: "research-desk" });

    await next();
    expect(title()).toBe("Investment memos");
    expect(push).toHaveBeenLastCalledWith({ name: "reports" });

    await next();
    expect(title()).toBe("Markets, Pulse and News");
    expect(push).toHaveBeenLastCalledWith({ name: "market-radar" });

    await next();
    expect(title()).toBe("Tracking");
    expect(push).toHaveBeenLastCalledWith({ name: "tracking" });

    // Warren lives in the toolbar on every screen, so this step stays put.
    const pushesBeforeWarren = push.mock.calls.length;
    await next();
    expect(title()).toBe("Meet Warren");
    expect(push.mock.calls.length).toBe(pushesBeforeWarren);
    expect(spotlight()).not.toBeNull();

    expect(document.body.querySelector("[data-testid='welcome-tour-next']").textContent.trim()).toBe("Get started");
    // The last step has no skip control: the only way out is Get started.
    expect(document.body.querySelector("[data-testid='welcome-tour-skip']")).toBeNull();

    click("welcome-tour-next");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("centres the callout when the step's control isn't on screen", async () => {
    // No sidebar planted: narrow windows keep it in a drawer.
    wrapper = mountTour();
    await flushPromises();
    await next();

    expect(title()).toBe("Start with a company");
    expect(push).toHaveBeenLastCalledWith({ name: "home" });
    expect(spotlight()).toBeNull();
    const callout = document.body.querySelector("[role='dialog']");
    expect(callout.style.transform).toBe("translate(-50%, -50%)");
  });

  it("returns the app to where the tour started when it closes", async () => {
    mockRoute.fullPath = "/tracking";
    wrapper = mountTour();
    await flushPromises();
    await next();
    expect(push).toHaveBeenLastCalledWith({ name: "home" });

    mockRoute.fullPath = "/";
    await wrapper.setProps({ open: false });
    await flushPromises();
    expect(push).toHaveBeenLastCalledWith("/tracking");
  });

  it("goes back a step and skips from the close control", async () => {
    wrapper = mountTour();
    await flushPromises();
    await next();
    click("welcome-tour-back");
    await flushPromises();
    expect(title()).toBe("Welcome to BSH Research Center");

    click("welcome-tour-skip");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("supports the arrow keys and Escape", async () => {
    wrapper = mountTour();
    await flushPromises();
    const panel = document.body.querySelector("[role='dialog']");
    panel.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    await flushPromises();
    expect(title()).toBe("Start with a company");
    panel.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    await flushPromises();
    expect(title()).toBe("Welcome to BSH Research Center");
    panel.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("restarts from the welcome card each time it opens", async () => {
    wrapper = mountTour();
    await flushPromises();
    await next();
    await wrapper.setProps({ open: false });
    await wrapper.setProps({ open: true });
    await flushPromises();
    expect(title()).toBe("Welcome to BSH Research Center");
  });
});
