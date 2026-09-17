import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import CompanyDossierView from "../src/components/research/CompanyDossierView.vue";

vi.mock("../src/api.js", () => {
  const api = {
    listCompanyReports: vi.fn().mockResolvedValue([]),
    listCompanyDocuments: vi.fn().mockResolvedValue({ rows: [] }),
    researchFileUrl: vi.fn(() => "/x"),
    fileUrl: vi.fn(() => "/x"),
  };
  return { api, default: api, withApiToken: (u) => u };
});

function mountDossier() {
  return mount(CompanyDossierView, {
    props: { companyId: "zainar-inc", company: { id: "zainar-inc", name: "ZaiNar" } },
    global: {
      stubs: {
        UnifiedDocumentsView: { template: '<div data-testid="documents" />' },
        MacTabBar: {
          props: ["items", "modelValue"],
          emits: ["update:modelValue"],
          template:
            '<nav><button v-for="i in items" :key="i.id" :data-tab="i.id"' +
            ' @click="$emit(\'update:modelValue\', i.id)">{{ i.label }}</button></nav>',
        },
      },
    },
  });
}

describe("CompanyDossierView files tab", () => {
  it("offers a Files tab, because uploading is how evidence reaches a memo run", () => {
    // The old company page owned the only upload surface and lost its route;
    // the backend endpoints never went away, so this is the way back in.
    const wrapper = mountDossier();
    const tabs = wrapper.findAll("[data-tab]").map((b) => b.attributes("data-tab"));
    expect(tabs).toContain("files");
  });

  it("mounts the documents view on that tab", async () => {
    const wrapper = mountDossier();
    expect(wrapper.find('[data-testid="documents"]').exists()).toBe(false);
    await wrapper.find('[data-tab="files"]').trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="documents"]').exists()).toBe(true);
  });
});
