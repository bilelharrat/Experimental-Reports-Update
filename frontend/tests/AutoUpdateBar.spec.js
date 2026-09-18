import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import AutoUpdateBar from "../src/components/AutoUpdateBar.vue";
import api from "../src/api.js";

vi.mock("../src/api.js", () => {
  const api = { putAutoUpdate: vi.fn() };
  return { api, default: api };
});

const CHANNEL = {
  id: "news_brief",
  label: { en: "News briefs", zh: "新闻简报" },
  description: { en: "AI briefings.", zh: "AI 简报。" },
  cadence: "6h",
  interval_hours: 6,
  choices: ["manual", "6h", "12h", "1d", "3d"],
  last_run_at: "2026-09-15T00:00:00+00:00",
  next_run_at: "2026-09-15T06:00:00+00:00",
};

describe("AutoUpdateBar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the same five choices with the active one checked", () => {
    const wrapper = mount(AutoUpdateBar, {
      props: { channelId: "news_brief", channel: CHANNEL },
    });
    const buttons = wrapper.findAll("button[role='radio']");
    expect(buttons).toHaveLength(5);
    expect(buttons.map((b) => b.text())).toEqual([
      "Manual",
      "Every 6h",
      "Every 12h",
      "Daily",
      "Every 3 days",
    ]);
    const checked = buttons.filter(
      (b) => b.attributes("aria-checked") === "true",
    );
    expect(checked).toHaveLength(1);
    expect(checked[0].text()).toBe("Every 6h");
  });

  it("saves the picked cadence and emits the updated channel", async () => {
    const updated = { ...CHANNEL, cadence: "3d", next_run_at: null };
    api.putAutoUpdate.mockResolvedValue(updated);
    const wrapper = mount(AutoUpdateBar, {
      props: { channelId: "news_brief", channel: CHANNEL },
    });

    await wrapper.findAll("button[role='radio']")[4].trigger("click");
    await flushPromises();

    expect(api.putAutoUpdate).toHaveBeenCalledWith("news_brief", {
      cadence: "3d",
    });
    expect(wrapper.emitted("updated")[0]).toEqual([updated]);
  });

  it("does not call the API when the active choice is clicked again", async () => {
    const wrapper = mount(AutoUpdateBar, {
      props: { channelId: "news_brief", channel: CHANNEL },
    });
    await wrapper.findAll("button[role='radio']")[1].trigger("click");
    await flushPromises();
    expect(api.putAutoUpdate).not.toHaveBeenCalled();
  });

  it("says nothing runs on its own when the channel is manual", () => {
    const wrapper = mount(AutoUpdateBar, {
      props: {
        channelId: "news_brief",
        channel: { ...CHANNEL, cadence: "manual", next_run_at: null },
      },
    });
    expect(wrapper.text()).toContain("Manual only");
    expect(wrapper.text()).not.toContain("Next run");
  });

  it("emits error when the save fails", async () => {
    api.putAutoUpdate.mockRejectedValue(new Error("nope"));
    const wrapper = mount(AutoUpdateBar, {
      props: { channelId: "news_brief", channel: CHANNEL },
    });
    await wrapper.findAll("button[role='radio']")[0].trigger("click");
    await flushPromises();
    expect(wrapper.emitted("error")).toBeTruthy();
    expect(wrapper.emitted("updated")).toBeFalsy();
  });
});
