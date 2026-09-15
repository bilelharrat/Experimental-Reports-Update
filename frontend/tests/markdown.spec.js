import { describe, expect, it } from "vitest";
import { renderMarkdown } from "../src/markdown.js";

describe("renderMarkdown", () => {
  it("keeps dollar amounts as text instead of inline math", () => {
    const html = renderMarkdown("Tokyo GX and the reported ~$5B pipeline target both carry **$0** in bear.");
    expect(html).not.toContain("md-math");
    expect(html).toContain("~$5B pipeline target");
    expect(html).toContain("<strong>$0</strong>");
  });

  it("still renders real inline math", () => {
    expect(renderMarkdown("Growth is $g = r - d$ here.")).toContain('<span class="md-math">g = r - d</span>');
  });

  it("leaves underscores inside file names alone but italicizes _words_", () => {
    const html = renderMarkdown("See growth_bridge.md and _this note_.");
    expect(html).toContain("growth_bridge.md");
    expect(html).toContain("<em>this note</em>");
  });
});
