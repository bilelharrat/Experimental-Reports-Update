import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Monogram from "../src/components/Monogram.vue";

describe("Monogram", () => {
  it("renders initials when company has no logo", () => {
    const wrapper = mount(Monogram, {
      props: {
        company: { name: "Mystery Co" },
      },
    });
    expect(wrapper.text()).toContain("MC");
    expect(wrapper.find("img").exists()).toBe(false);
  });

  it("renders an img candidate when company logo is available", () => {
    const wrapper = mount(Monogram, {
      props: {
        company: { ticker: "AAPL", name: "Apple Inc." },
      },
    });
    const img = wrapper.find("img");
    expect(img.exists()).toBe(true);
    expect(img.attributes("src")).toContain("AAPL");
    // Before load event, initials are present as smooth placeholder
    expect(wrapper.text()).toContain("AA");
  });

  it("switches to logo presentation on load and hides initials text", async () => {
    const wrapper = mount(Monogram, {
      props: {
        company: { ticker: "NVDA", name: "Nvidia" },
      },
    });
    const img = wrapper.get("img");
    await img.trigger("load");
    expect(wrapper.classes()).toContain("monogram-has-logo");
    expect(wrapper.find(".monogram-initials").exists()).toBe(false);
  });

  it("falls back to secondary CDN and then initials if error triggers", async () => {
    const wrapper = mount(Monogram, {
      props: {
        company: { ticker: "GOOG", name: "Google" },
      },
    });
    const img = wrapper.get("img");
    expect(img.attributes("src")).toContain("GOOG");
    // Trigger first error (switches to fallback)
    await img.trigger("error");
    expect(img.attributes("src")).toContain("t1.gstatic.com");
    // Trigger second error (marks failed)
    await img.trigger("error");
    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.find(".monogram-initials").exists()).toBe(true);
    expect(wrapper.text()).toContain("GO");
  });

  it("respects showLogo=false to force initials only", () => {
    const wrapper = mount(Monogram, {
      props: {
        company: { ticker: "AAPL" },
        showLogo: false,
      },
    });
    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.text()).toContain("AA");
  });

  it("renders user initials when company is not provided", () => {
    const wrapper = mount(Monogram, {
      props: {
        name: "Warren Buffett",
        tinted: true,
      },
    });
    expect(wrapper.text()).toContain("WB");
    expect(wrapper.find("img").exists()).toBe(false);
  });
});
