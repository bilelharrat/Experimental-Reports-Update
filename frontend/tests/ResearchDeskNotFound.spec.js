import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/api.js", () => {
  const mock = { listCompanies: vi.fn() };
  return { default: mock, api: mock };
});

import { api } from "../src/api.js";
import ResearchDeskView from "../src/views/ResearchDeskView.vue";
import { lastCompanyId, setAppLanguage } from "../src/state.js";

// A company link can name a company this workspace does not have: most
// reports on file belong to companies that were never added, and every
// unknown path falls through to the desk's /:companyId route. The desk used
// to open whatever company it would have opened anyway, under the wrong URL.
// It now says the company is not here and points at its reports — but only
// once the company list has loaded, so a deep link never flashes it.

const companies = [
  { id: "globex", name: "Globex Corporation" },
  { id: "initech", name: "Initech" },
];

const DossierStub = {
  props: ["companyId", "company"],
  template: '<div data-dossier :data-company="companyId" />',
};

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/research-desk", name: "research-desk", component: ResearchDeskView, props: true },
      {
        path: "/research-desk/:companyId",
        name: "research-desk-company",
        component: ResearchDeskView,
        props: true,
      },
      { path: "/reports", name: "reports", component: { template: "<div>Reports</div>" } },
      { path: "/:companyId", name: "research", component: ResearchDeskView, props: true },
    ],
  });
}

async function openDesk(path, router = makeRouter()) {
  window.innerWidth = 1280;
  await router.push(path);
  await router.isReady();
  const wrapper = mount(
    { template: "<RouterView />" },
    { global: { plugins: [router], stubs: { CompanyDossierView: DossierStub } } },
  );
  await flushPromises();
  return { wrapper, router };
}

const notFound = (wrapper) => wrapper.find('[data-testid="desk-company-not-found"]');
const openCompany = (wrapper) =>
  wrapper.find("[data-dossier]").exists() ? wrapper.get("[data-dossier]").attributes("data-company") : "";

describe("Research Desk: a link to a company that is not here", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    lastCompanyId.value = "";
    api.listCompanies.mockResolvedValue(companies);
  });

  afterEach(() => {
    setAppLanguage("en");
    lastCompanyId.value = "";
  });

  it("says the company is not found and links to its reports", async () => {
    const { wrapper, router } = await openDesk("/open-artificial-intelligence-inc");

    expect(openCompany(wrapper)).toBe("");
    const state = notFound(wrapper);
    expect(state.exists()).toBe(true);
    expect(state.text()).toContain("Company not found");
    expect(state.text()).toContain("open-artificial-intelligence-inc");
    // It looked once more before saying so: the company may have been added
    // since the desk fetched its list.
    expect(api.listCompanies).toHaveBeenCalledTimes(2);

    await wrapper.get('[data-testid="desk-company-not-found-reports"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe(
      "/reports?company=open-artificial-intelligence-inc",
    );
  });

  it("never shows it while the company list is still loading", async () => {
    let release;
    api.listCompanies.mockReturnValueOnce(new Promise((resolve) => (release = resolve)));
    const { wrapper } = await openDesk("/research-desk/initech");

    // Loading: neither "not found" nor the empty desk.
    expect(notFound(wrapper).exists()).toBe(false);
    expect(wrapper.text()).not.toContain("No Company Selected");

    release(companies);
    await flushPromises();
    expect(notFound(wrapper).exists()).toBe(false);
    expect(openCompany(wrapper)).toBe("initech");
  });

  it("finds a company added after the list loaded", async () => {
    const { wrapper, router } = await openDesk("/globex");
    expect(openCompany(wrapper)).toBe("globex");

    // The toolbar's Add creates Newco, then opens it on this desk.
    api.listCompanies.mockResolvedValue([...companies, { id: "newco", name: "Newco" }]);
    await router.push("/newco");
    await flushPromises();

    expect(notFound(wrapper).exists()).toBe(false);
    expect(openCompany(wrapper)).toBe("newco");
  });

  it("looks again when a link it once missed is followed later", async () => {
    const { wrapper, router } = await openDesk("/research-desk/newco");
    expect(notFound(wrapper).exists()).toBe(true);

    // Newco is added afterwards; the desk's list is from before.
    api.listCompanies.mockResolvedValue([...companies, { id: "newco", name: "Newco" }]);
    await router.push("/research-desk/globex");
    await flushPromises();
    await router.push("/research-desk/newco");
    await flushPromises();
    expect(notFound(wrapper).exists()).toBe(false);
    expect(openCompany(wrapper)).toBe("newco");
  });

  it("never opens another company's dossier under the missing id", async () => {
    // The desk remembers Globex, which it would open on a bare visit.
    lastCompanyId.value = "globex";
    const { wrapper, router } = await openDesk("/globex");
    expect(openCompany(wrapper)).toBe("globex");

    await router.push("/research-desk/deleted-co");
    await flushPromises();
    expect(openCompany(wrapper)).toBe("");
    expect(notFound(wrapper).exists()).toBe(true);

    // Back to a real company: the state clears.
    await router.push("/research-desk/initech");
    await flushPromises();
    expect(notFound(wrapper).exists()).toBe(false);
    expect(openCompany(wrapper)).toBe("initech");
  });

  it("keeps the bare desk's default company", async () => {
    lastCompanyId.value = "initech";
    const { wrapper } = await openDesk("/research-desk");
    expect(notFound(wrapper).exists()).toBe(false);
    expect(openCompany(wrapper)).toBe("initech");
  });

  it("does not call a company missing when the list could not load", async () => {
    api.listCompanies.mockRejectedValue(new Error("offline"));
    const { wrapper } = await openDesk("/research-desk/globex");
    expect(notFound(wrapper).exists()).toBe(false);
    expect(wrapper.text()).toContain("No Company Selected");
  });

  it("speaks Chinese", async () => {
    setAppLanguage("zh");
    const { wrapper } = await openDesk("/research-desk/deleted-co");
    const state = notFound(wrapper);
    expect(state.text()).toContain("未找到该公司");
    expect(state.text()).toContain("deleted-co");
  });
});
