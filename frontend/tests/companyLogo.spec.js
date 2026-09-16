import { describe, expect, it } from "vitest";
import {
  companyFallbackLogoUrl,
  companyLogoUrl,
  googleFaviconUrl,
  normalizeDomain,
  resolveCompanyDomain,
} from "../src/companyLogo.js";

describe("companyLogo", () => {
  describe("normalizeDomain", () => {
    it("strips protocols, paths, query params, and www prefixes", () => {
      expect(normalizeDomain("https://www.apple.com/iphone")).toBe("apple.com");
      expect(normalizeDomain("http://zainartech.com?ref=123")).toBe("zainartech.com");
      expect(normalizeDomain("www.nvidia.com")).toBe("nvidia.com");
      expect(normalizeDomain("  databricks.com/about  ")).toBe("databricks.com");
    });

    it("rejects invalid domains", () => {
      expect(normalizeDomain("")).toBe("");
      expect(normalizeDomain(null)).toBe("");
      expect(normalizeDomain("not a domain")).toBe("");
    });
  });

  describe("resolveCompanyDomain", () => {
    it("prioritizes explicit logo_domain", () => {
      const company = {
        name: "Custom Name",
        website: "https://wrong.com",
        logo_domain: "correct.com",
      };
      expect(resolveCompanyDomain(company)).toBe("correct.com");
    });

    it("uses website if logo_domain is absent", () => {
      const company = {
        name: "Acme",
        website: "https://www.acme.corp",
      };
      expect(resolveCompanyDomain(company)).toBe("acme.corp");
    });

    it("resolves domain from ticker when website is missing", () => {
      expect(resolveCompanyDomain({ ticker: "AAPL" })).toBe("apple.com");
      expect(resolveCompanyDomain({ ticker: "NVDA" })).toBe("nvidia.com");
      expect(resolveCompanyDomain({ ticker: "TSM" })).toBe("tsmc.com");
      expect(resolveCompanyDomain({ ticker: "GOOG" })).toBe("google.com");
    });

    it("resolves domain from company id or name", () => {
      expect(resolveCompanyDomain({ id: "anthropic" })).toBe("anthropic.com");
      expect(resolveCompanyDomain({ name: "OpenAI" })).toBe("openai.com");
      expect(resolveCompanyDomain({ id: "zainar-inc" })).toBe("zainartech.com");
      expect(resolveCompanyDomain({ name: "Cerebras Systems" })).toBe("cerebras.ai");
    });
  });

  describe("googleFaviconUrl", () => {
    it("generates 128px high-res Google CDN favicon URL", () => {
      const url = googleFaviconUrl("apple.com");
      expect(url).toContain("t1.gstatic.com/faviconV2");
      expect(url).toContain("apple.com");
      expect(url).toContain("size=128");
    });
  });

  describe("companyLogoUrl", () => {
    it("returns direct logo_url if provided on the company", () => {
      const company = { logo_url: "https://custom.cdn/logo.png" };
      expect(companyLogoUrl(company)).toBe("https://custom.cdn/logo.png");
    });

    it("returns Parqet vector SVG for public stock symbols", () => {
      const url = companyLogoUrl({ ticker: "AAPL" });
      expect(url).toContain("assets.parqet.com/logos/symbol/AAPL");
    });

    it("returns curated vector SVG for frontier AI labs", () => {
      const url = companyLogoUrl({ id: "anthropic" });
      expect(url).toContain("api.iconify.design/simple-icons:anthropic.svg");
    });

    it("resolves report companies by id or name", () => {
      expect(companyLogoUrl({ id: "ko", name: "Coca Cola Co" })).toContain("assets.parqet.com/logos/symbol/KO");
      expect(companyLogoUrl({ id: "open-artificial-intelligence-inc", name: "Open Artificial Intelligence" })).toContain("openai.svg");
      expect(companyLogoUrl({ id: "cienet-technologies-beijing-co-ltd", name: "CIeNET Technologies" })).toContain("cienet.com");
      expect(companyLogoUrl({ id: "ceinet-data-co-ltd-中经网数据有限公司", name: "CEInet Data" })).toContain("cei.cn");
      expect(companyLogoUrl({ id: "oxy", name: "Occidental Petroleum Corp /De/" })).toContain("assets.parqet.com/logos/symbol/OXY");
    });

    it("returns empty string when domain cannot be determined", () => {
      expect(companyLogoUrl(null)).toBe("");
      expect(companyLogoUrl({})).toBe("");
    });
  });

  describe("companyFallbackLogoUrl", () => {
    it("returns Google Edge CDN fallback for stock symbols", () => {
      const url = companyFallbackLogoUrl({ ticker: "NVDA" });
      expect(url).toContain("t1.gstatic.com");
      expect(url).toContain("nvidia.com");
    });

    it("returns DuckDuckGo fallback for generic domain", () => {
      const url = companyFallbackLogoUrl({ website: "https://example.com" });
      expect(url).toContain("icons.duckduckgo.com");
      expect(url).toContain("example.com");
    });
  });
});

