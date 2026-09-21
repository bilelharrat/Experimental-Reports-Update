import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/api.js", () => {
  const mock = { listCompanies: vi.fn() };
  return { default: mock, api: mock };
});

import ResearchDeskView from "../src/views/ResearchDeskView.vue";
import { companySort, lastCompanyId } from "../src/state.js";

// The bare Research Desk row has no company in its URL, so the desk picks
// one. It used to take the first company the API happened to return, which
// was nobody's choice; it now reopens the company you were last working on,
// and otherwise the top of the sidebar list as you have it sorted.

const companies = [
  { id: "zeta", name: "Zeta Labs" },
  { id: "acme", name: "Acme Inc." },
  { id: "mid", name: "Middle Co" },
];

const DossierStub = {
  props: ["companyId", "company"],
  template: '<div data-dossier :data-company="companyId" />',
};

async function mountDesk({ width = 1280 } = {}) {
  window.innerWidth = width;
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/research-desk", name: "research-desk", component: ResearchDeskView }],
  });
  router.push("/research-desk");
  await router.isReady();
  const wrapper = mount(ResearchDeskView, {
    props: { companies },
    global: { plugins: [router], stubs: { CompanyDossierView: DossierStub } },
  });
  await flushPromises();
  return wrapper;
}

function openCompany(wrapper) {
  return wrapper.find("[data-dossier]").exists()
    ? wrapper.get("[data-dossier]").attributes("data-company")
    : "";
}

describe("Research Desk default company", () => {
  afterEach(() => {
    lastCompanyId.value = "";
    companySort.value = "az";
  });

  it("reopens the company you last worked on", async () => {
    lastCompanyId.value = "mid";
    expect(openCompany(await mountDesk())).toBe("mid");
  });

  it("reopens it on a phone too", async () => {
    lastCompanyId.value = "mid";
    expect(openCompany(await mountDesk({ width: 390 }))).toBe("mid");
  });

  it("falls back to the top of the sidebar list, not the API's first row", async () => {
    companySort.value = "az";
    // API order starts with Zeta; A–Z starts with Acme.
    expect(openCompany(await mountDesk())).toBe("acme");
  });

  it("ignores a remembered company that no longer exists", async () => {
    lastCompanyId.value = "deleted-co";
    expect(openCompany(await mountDesk())).toBe("acme");
  });

  it("waits for a pick on a phone when nothing is remembered", async () => {
    expect(openCompany(await mountDesk({ width: 390 }))).toBe("");
  });
});
