import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const m = vi.hoisted(() => ({
  get: vi.fn(),
  patchCard: vi.fn(),
  moveCard: vi.fn(),
  patchBullet: vi.fn(),
  diveDeeper: vi.fn(),
  selectConclusion: vi.fn(),
  rerunSection: vi.fn(),
  patchAppendixBlock: vi.fn(),
  exportProjection: vi.fn(),
  history: vi.fn(),
  createTask: vi.fn(),
  updateTask: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: { memoEditor: m },
}));

import MemoStudioEditor from "../src/components/MemoStudioEditor.vue";

function baseState(overrides = {}) {
  const state = {
    company_id: "zainar-inc",
    company_name: "ZaiNar, Inc.",
    version_id: "v1",
    status: "draft",
    updated_at: "2026-07-03T12:00:00Z",
    sections: {
      executive_summary: {
        title: "Executive Summary",
        status: "ready_for_input",
        body: "ZaiNar has ARR of $24M with source coverage.",
        recommendation: "Conditional proceed.",
        round: "Growth round",
        top_gate: "Validate ARR.",
        source_class: "BSH primary diligence",
        source_refs: [{ title: "BSH diligence", source_class: "BSH primary diligence" }],
      },
      investment_thesis: {
        title: "Investment Thesis",
        status: "ready_for_input",
        cards: [
          {
            id: "thesis-1",
            title: "Existing networks become a positioning layer.",
            category: "Technology moat",
            included: true,
            rank: 1,
            expanded: true,
            source_class: "company material",
            source_refs: [{ title: "Company deck", source_class: "company material" }],
            bullets: [
              {
                id: "bullet-1",
                text: "Uses existing 5G and Wi-Fi networks.",
                source_class: "company material",
                source_refs: [{ title: "Company deck", source_class: "company material" }],
                children: [],
              },
            ],
          },
          {
            id: "thesis-2",
            title: "Metrics create a late-stage frame.",
            category: "Commercial traction",
            included: true,
            rank: 2,
            expanded: false,
            source_class: "BSH primary diligence",
            source_refs: [{ title: "BSH diligence", source_class: "BSH primary diligence" }],
            bullets: [],
          },
        ],
      },
      risks_mitigations: {
        title: "Risks and Mitigations",
        status: "ready_for_input",
        cards: [
          {
            id: "risk-1",
            title: "Revenue quality needs validation.",
            category: "Evidence gap",
            severity: "high",
            included: true,
            rank: 1,
            expanded: false,
            source_class: "BSH primary diligence",
            source_refs: [{ title: "BSH diligence", source_class: "BSH primary diligence" }],
            bullets: [],
          },
        ],
      },
      conclusion: {
        title: "Conclusion",
        status: "ready_for_input",
        selected_option_id: "conditional",
        options: [
          {
            id: "conditional",
            label: "Conditional proceed",
            text: "Proceed if evidence is confirmed.",
            source_class: "BSH primary diligence",
          },
          {
            id: "pass",
            label: "Pass",
            text: "Pass if evidence remains unresolved.",
            source_class: "BSH primary diligence",
          },
        ],
      },
      appendix: {
        title: "Appendix",
        status: "ready_for_input",
        blocks: [
          {
            id: "company_overview",
            title: "Company Overview",
            status: "ready",
            expanded: false,
            facts: ["Network-based PNT platform."],
            source_class: "company material",
          },
        ],
      },
    },
    ...overrides,
  };
  return state;
}

describe("MemoStudioEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    m.get.mockResolvedValue(baseState());
    m.patchCard.mockImplementation((companyId, sectionId, cardId, patch) => {
      const state = baseState();
      const card = state.sections[sectionId].cards.find((row) => row.id === cardId);
      Object.assign(card, patch);
      return Promise.resolve(state);
    });
    m.moveCard.mockResolvedValue(baseState({
      sections: {
        ...baseState().sections,
        investment_thesis: {
          ...baseState().sections.investment_thesis,
          cards: [
            { ...baseState().sections.investment_thesis.cards[1], rank: 1 },
            { ...baseState().sections.investment_thesis.cards[0], rank: 2 },
          ],
        },
      },
    }));
    m.patchBullet.mockResolvedValue(baseState());
    m.diveDeeper.mockResolvedValue(baseState({
      sections: {
        ...baseState().sections,
        investment_thesis: {
          ...baseState().sections.investment_thesis,
          cards: [
            {
              ...baseState().sections.investment_thesis.cards[0],
              bullets: [
                {
                  ...baseState().sections.investment_thesis.cards[0].bullets[0],
                  children: [{ id: "child-1", text: "Dive deeper point.", children: [] }],
                },
              ],
            },
            baseState().sections.investment_thesis.cards[1],
          ],
        },
      },
    }));
    m.selectConclusion.mockResolvedValue(baseState({
      sections: {
        ...baseState().sections,
        conclusion: {
          ...baseState().sections.conclusion,
          selected_option_id: "pass",
        },
      },
    }));
    m.rerunSection.mockResolvedValue(baseState({
      sections: {
        ...baseState().sections,
        investment_thesis: {
          ...baseState().sections.investment_thesis,
          last_rerun_status: "recorded",
        },
      },
    }));
    m.patchAppendixBlock.mockResolvedValue(baseState({
      sections: {
        ...baseState().sections,
        appendix: {
          ...baseState().sections.appendix,
          blocks: [
            {
              ...baseState().sections.appendix.blocks[0],
              expanded: true,
            },
          ],
        },
      },
    }));
    m.exportProjection.mockResolvedValue({
      blocked: true,
      block_reason: "Export blocked: key figures lack source/source-class coverage.",
      missing_sources: [
        {
          location: "Investment Thesis / Metrics",
          text: "ARR is $50M.",
          terms: ["$50M"],
        },
      ],
      source_coverage: {
        key_figure_count: 2,
        covered_key_figure_count: 1,
        missing_key_figure_count: 1,
        coverage: 0.5,
      },
      projection: {},
    });
    m.history.mockResolvedValue({
      versions: [
        {
          revision_id: "rev-0002",
          event: "memo_task_created",
          created_at: "2026-07-03T12:05:00Z",
        },
      ],
      audit_records: [
        {
          id: "audit-1",
          event: "memo_task_created",
          created_at: "2026-07-03T12:05:00Z",
        },
      ],
      memo_tasks: [
        {
          id: "task-1",
          title: "Discuss revenue quality",
          description: "Check ARR versus sources.",
          status: "proposed",
        },
      ],
    });
    m.createTask.mockResolvedValue({
      id: "task-2",
      title: "Discuss: Existing networks become a positioning layer.",
      status: "proposed",
    });
    m.updateTask.mockResolvedValue({ id: "task-1", status: "accepted" });
  });

  it("renders five memo sections and handles editor actions", async () => {
    const wrapper = mount(MemoStudioEditor, {
      props: { companyId: "zainar-inc" },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Executive Summary");
    expect(wrapper.text()).toContain("Investment Thesis");
    expect(wrapper.text()).toContain("Risks and Mitigations");
    expect(wrapper.text()).toContain("Conclusion");
    expect(wrapper.text()).toContain("Appendix");

    await wrapper.findAll("button").find((button) => button.text() === "Rerun").trigger("click");
    await flushPromises();
    expect(m.rerunSection).toHaveBeenCalledWith("zainar-inc", "executive_summary");

    await wrapper.find("input[type='checkbox']").setValue(false);
    await flushPromises();
    expect(m.patchCard).toHaveBeenCalledWith(
      "zainar-inc",
      "investment_thesis",
      "thesis-1",
      { included: false },
    );

    await wrapper.findAll("button").find((button) => button.text().includes("Dive Deeper")).trigger("click");
    await flushPromises();
    expect(m.diveDeeper).toHaveBeenCalledWith(
      "zainar-inc",
      "investment_thesis",
      "thesis-1",
      "bullet-1",
    );
    expect(wrapper.text()).toContain("Dive deeper point.");

    await wrapper.findAll("button").find((button) => button.text().includes("Edit")).trigger("click");
    await wrapper.find("textarea").setValue("Edited bullet.");
    await wrapper.findAll("button").find((button) => button.text() === "Save").trigger("click");
    await flushPromises();
    expect(m.patchBullet).toHaveBeenCalledWith(
      "zainar-inc",
      "investment_thesis",
      "thesis-1",
      "bullet-1",
      { text: "Edited bullet." },
    );

    await wrapper.findAll("button").find((button) => button.text().includes("Discuss")).trigger("click");
    await flushPromises();
    expect(m.createTask).toHaveBeenCalledWith(
      "zainar-inc",
      expect.objectContaining({
        action_type: "discuss",
        status: "proposed",
      }),
    );
    expect(wrapper.emitted("discuss")[0][0]).toMatchObject({
      company_id: "zainar-inc",
      card_id: "thesis-1",
      bullet_id: "bullet-1",
    });

    expect(wrapper.text()).toContain("Co-pilot Tasks");
    await wrapper.findAll("button").find((button) => button.text() === "Accept").trigger("click");
    await flushPromises();
    expect(m.updateTask).toHaveBeenCalledWith("zainar-inc", "task-1", { status: "accepted" });
    expect(wrapper.text()).toContain("Recoverable history");

    await wrapper.findAll("button").find((button) => button.text().includes("Pass")).trigger("click");
    await flushPromises();
    expect(m.selectConclusion).toHaveBeenCalledWith("zainar-inc", "pass");

    await wrapper.findAll("button").find((button) => button.text().includes("Company Overview")).trigger("click");
    await flushPromises();
    expect(m.patchAppendixBlock).toHaveBeenCalledWith(
      "zainar-inc",
      "company_overview",
      { expanded: true },
    );

    await wrapper.findAll("button").find((button) => button.text().includes("Export Memo")).trigger("click");
    await flushPromises();
    expect(m.exportProjection).toHaveBeenCalledWith("zainar-inc", { record: true });
    expect(wrapper.text()).toContain("Export blocked");
    expect(wrapper.text()).toContain("50% source coverage");
    expect(wrapper.text()).toContain("$50M");
  });
});
