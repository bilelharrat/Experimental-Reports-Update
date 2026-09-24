import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive, ref } from "vue";
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
import { DEFAULT_BUREAU_DESK, DEFAULT_DESIGN, setBureauDesk, setDesign } from "../src/design.js";
import { setCompanySort, setLastCompanyId } from "../src/state.js";

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

const workspaceCompanies = ref([]);

function mountTour(open = true) {
  return mount(WelcomeTour, {
    props: { open },
    attachTo: document.body,
    global: { provide: { workspaceCompanies } },
  });
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

  it("shows the look step once more to people who finished the v2 tour", () => {
    expect(WELCOME_TOUR_VERSION).toBe(3);
    window.localStorage.setItem(WELCOME_TOUR_KEY, "2");
    expect(shouldShowWelcomeTour()).toBe(true);
    window.localStorage.setItem(WELCOME_TOUR_KEY, "3");
    expect(shouldShowWelcomeTour()).toBe(false);
  });

  it("gives every step after the welcome card a screen to visit", () => {
    const [hero, ...walk] = WELCOME_TOUR_STEPS;
    expect(hero.kind).toBe("hero");
    expect(walk.length).toBeGreaterThan(0);
    for (const entry of walk) {
      // A step either drives the app somewhere or points at something here.
      expect(Boolean(entry.route) || Boolean(entry.target)).toBe(true);
      // It points at a control, or (a choice) asks over the screen it visits.
      if (entry.kind === "choice") expect(entry.route).toBeTruthy();
      else expect(entry.target).toBeTruthy();
    }
  });

  it("asks for a look near the end, just before the last page", () => {
    const ids = WELCOME_TOUR_STEPS.map((entry) => entry.id);
    expect(ids.indexOf("look")).toBe(ids.length - 2);
    expect(WELCOME_TOUR_STEPS.find((entry) => entry.id === "look")).toMatchObject({
      kind: "choice",
      route: { name: "home" },
    });
  });
});

describe("WelcomeTour", () => {
  let wrapper;

  beforeEach(() => {
    push.mockClear();
    mockRoute.fullPath = "/";
    workspaceCompanies.value = [
      { id: "zeta", name: "Zeta Labs" },
      { id: "acme", name: "Acme Inc." },
    ];
    setCompanySort("az");
    setLastCompanyId("");
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
    // the company list is where research starts; the markets step points at
    // the Market row
    plantTarget('[data-tour="companies"]');
    plantTarget('[data-tour="company-folder"]', { top: 300, left: 12, width: 244, height: 150 });
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
    expect(push).toHaveBeenLastCalledWith({ name: "home" });

    // A company opens like a folder: going to its desk opens it in the
    // sidebar, and the open folder is what the step spotlights.
    await next();
    expect(title()).toBe("Open a company like a folder");
    expect(push).toHaveBeenLastCalledWith({ name: "research", params: { companyId: "acme" } });
    expect(spotlight()).not.toBeNull();

    await next();
    expect(title()).toBe("Investment memos");
    expect(push).toHaveBeenLastCalledWith({ name: "reports" });

    await next();
    expect(title()).toBe("Markets, Pulse and News");
    expect(push).toHaveBeenLastCalledWith({ name: "market-radar" });

    await next();
    expect(title()).toBe("Tracking");
    expect(push).toHaveBeenLastCalledWith({ name: "tracking" });

    // Having seen the app, choose how it looks, over Home, with nothing
    // spotlit: the callout holds the choices.
    await next();
    expect(title()).toBe("Choose a look");
    expect(push).toHaveBeenLastCalledWith({ name: "home" });
    expect(spotlight()).toBeNull();
    expect(document.body.querySelector("[data-testid='design-look-cards']")).not.toBeNull();

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

  it("opens the last company visited for the folder step, else the top of the list", async () => {
    const folderStep = WELCOME_TOUR_STEPS.findIndex((entry) => entry.id === "folders");
    const reach = async () => {
      wrapper?.unmount();
      push.mockClear();
      wrapper = mountTour();
      await flushPromises();
      for (let i = 0; i < folderStep; i += 1) await next();
      expect(title()).toBe("Open a company like a folder");
    };

    setLastCompanyId("zeta");
    await reach();
    expect(push).toHaveBeenLastCalledWith({ name: "research", params: { companyId: "zeta" } });

    // A last company that's gone falls back to the list's first, A to Z.
    setLastCompanyId("deleted-co");
    await reach();
    expect(push).toHaveBeenLastCalledWith({ name: "research", params: { companyId: "acme" } });

    // No companies yet: the step stays home and centres its callout.
    workspaceCompanies.value = [];
    await reach();
    expect(push).toHaveBeenLastCalledWith({ name: "home" });
    expect(spotlight()).toBeNull();
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

describe("WelcomeTour look step", () => {
  let wrapper;
  const lookIndex = WELCOME_TOUR_STEPS.findIndex((entry) => entry.id === "look");
  const card = (id) => document.body.querySelector(`[data-testid='design-look-${id}']`);
  const deskPicker = () => document.body.querySelector("[data-testid='bureau-desk-picker']");

  async function openLookStep() {
    wrapper = mountTour();
    await flushPromises();
    document.body.querySelectorAll(".welcome-tour-dot")[lookIndex].click();
    await flushPromises();
    await flushPromises();
    expect(title()).toBe("Choose a look");
  }

  beforeEach(() => {
    push.mockClear();
    mockRoute.fullPath = "/";
    workspaceCompanies.value = [];
    window.localStorage.clear();
    setDesign(DEFAULT_DESIGN);
    setBureauDesk(DEFAULT_BUREAU_DESK);
  });

  afterEach(() => {
    wrapper?.unmount();
    document.body.innerHTML = "";
    setDesign(DEFAULT_DESIGN);
    setBureauDesk(DEFAULT_BUREAU_DESK);
    window.localStorage.clear();
  });

  it("offers Summit Glass, Bureau and Folio, with Summit Glass the default and current", async () => {
    await openLookStep();
    const cards = [...document.body.querySelectorAll(".look-card")];
    expect(cards.map((el) => el.dataset.testid)).toEqual([
      "design-look-glass",
      "design-look-bureau",
      "design-look-folio",
    ]);
    expect(card("glass").dataset.selected).toBe("true");
    expect(card("glass").querySelector("input").checked).toBe(true);
    expect(card("glass").querySelector(".look-card-default").textContent.trim()).toBe("Default");
    expect(card("bureau").querySelector(".look-card-default")).toBeNull();
    expect(card("bureau").dataset.selected).toBe("false");
    expect(card("bureau").textContent).toContain("The page laid on a desk");
    // One radio group, each card a radio named by its own words.
    const radios = [...document.body.querySelectorAll(".look-card input[type='radio']")];
    expect(radios).toHaveLength(3);
    expect(new Set(radios.map((radio) => radio.name)).size).toBe(1);
    expect(radios.every((radio) => radio.closest("label"))).toBe(true);
    // No desk colors until Bureau is picked.
    expect(deskPicker()).toBeNull();
  });

  it("applies the design picked at once, with Bureau's desk colors while it is on", async () => {
    await openLookStep();
    card("bureau").querySelector("input").click();
    await flushPromises();
    expect(document.documentElement.dataset.design).toBe("bureau");
    expect(card("bureau").dataset.selected).toBe("true");
    expect(card("glass").dataset.selected).toBe("false");
    expect(deskPicker()).not.toBeNull();
    expect(document.body.querySelector("[data-testid='bureau-desk-onyx']").dataset.selected).toBe("true");

    document.body.querySelector("[data-testid='bureau-desk-navy'] input").click();
    await flushPromises();
    expect(document.documentElement.dataset.desk).toBe("navy");
    expect(window.localStorage.getItem("bsh.research.bureauDesk")).toBe("navy");

    card("folio").querySelector("input").click();
    await flushPromises();
    expect(document.documentElement.dataset.design).toBe("folio");
    expect(deskPicker()).toBeNull();
    // The desk waits for Bureau to come back.
    expect(document.documentElement.dataset.desk).toBe("navy");
  });

  it("leaves the arrow keys to its radio groups", async () => {
    await openLookStep();
    const radio = card("glass").querySelector("input");
    radio.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    await flushPromises();
    expect(title()).toBe("Choose a look");
    // Anywhere else in the callout they still turn the page.
    const panel = document.body.querySelector("[role='dialog']");
    panel.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    await flushPromises();
    expect(title()).toBe("Meet Warren");
  });
});
