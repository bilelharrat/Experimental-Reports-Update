import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("../src/api.js", () => ({ api: { refreshCompany: vi.fn() }, withApiToken: (u) => u }));

import CompanyCard from "../src/components/CompanyCard.vue";
import { setAppLanguage } from "../src/state.js";

// The search results are where a partner picks which entity a memo is about.
// Search fills legal_name and disambiguator first, and the API returns them;
// the card now shows them, with the company's own domain, so a lookalike is
// told apart before anything is spent on it.

function mountCard(company) {
  return mount(CompanyCard, {
    props: { company },
    global: { stubs: { Monogram: true, AiMark: true } },
  });
}

const identity = (wrapper) => wrapper.find('[data-testid="company-identity"]');

describe("CompanyCard identity", () => {
  beforeEach(() => setAppLanguage("en"));
  afterEach(() => setAppLanguage("en"));

  it("shows the legal entity, the disambiguator and the domain", () => {
    const wrapper = mountCard({
      id: "github-inc",
      name: "GitHub",
      legal_name: "GitHub, Inc.",
      disambiguator: "Microsoft subsidiary, developer platform",
      website: "https://github.com",
      parent_company: "Microsoft",
      status: "subsidiary",
    });
    // The disambiguator already names the parent, so it is not said twice.
    expect(identity(wrapper).text()).toBe(
      "GitHub, Inc. · Microsoft subsidiary, developer platform · github.com",
    );
  });

  it("tells two entities with one name apart", () => {
    const pbc = mountCard({
      id: "openai",
      name: "OpenAI",
      legal_name: "OpenAI Group PBC",
      website: "https://openai.com",
    });
    const foundation = mountCard({
      id: "openai-foundation",
      name: "OpenAI",
      legal_name: "OpenAI Foundation",
      disambiguator: "Nonprofit that controls the OpenAI group",
      status: "nonprofit",
    });
    expect(identity(pbc).text()).toBe("OpenAI Group PBC · openai.com");
    expect(identity(foundation).text()).toBe(
      "OpenAI Foundation · Nonprofit that controls the OpenAI group",
    );
  });

  it("names the parent when nothing else does", () => {
    const wrapper = mountCard({
      id: "cienet",
      name: "CIeNET Technologies",
      legal_name: "CIeNET Technologies (Beijing) Co., Ltd.",
      parent_company: "ALTEN",
    });
    expect(identity(wrapper).text()).toBe(
      "CIeNET Technologies (Beijing) Co., Ltd. · Subsidiary of ALTEN",
    );
  });

  it("skips a legal name that only repeats the display name", () => {
    const wrapper = mountCard({ id: "acme", name: "Acme Inc.", legal_name: "ACME INC.", logo_domain: "acme.example" });
    expect(identity(wrapper).text()).toBe("acme.example");
  });

  it("shows no identity line when the record has none", () => {
    expect(identity(mountCard({ id: "x", name: "Plain Co" })).exists()).toBe(false);
  });

  it("speaks Chinese", () => {
    setAppLanguage("zh");
    const wrapper = mountCard({ id: "cienet", name: "CIeNET", parent_company: "ALTEN" });
    expect(identity(wrapper).text()).toBe("ALTEN 旗下子公司");
  });
});
