import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const m = vi.hoisted(() => ({
  get: vi.fn(),
  patchCard: vi.fn(),
  moveCard: vi.fn(),
  reorderCards: vi.fn(),
  patchBullet: vi.fn(),
  diveDeeper: vi.fn(),
  selectConclusion: vi.fn(),
  rerunSection: vi.fn(),
  patchAppendixBlock: vi.fn(),
  exportProjection: vi.fn(),
  addCard: vi.fn(),
  deleteCard: vi.fn(),
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
    expect(wrapper.text()).toContain("0 of 5 sections ready");

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

    await wrapper.find("button[aria-label='Dive deeper']").trigger("click");
    await flushPromises();
    expect(m.diveDeeper).toHaveBeenCalledWith(
      "zainar-inc",
      "investment_thesis",
      "thesis-1",
      "bullet-1",
    );
    expect(wrapper.text()).toContain("Dive deeper point.");

    await wrapper.find("button[aria-label='Edit']").trigger("click");
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

    await wrapper.find("button[aria-label='Discuss']").trigger("click");
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

    expect(wrapper.text()).toContain("Co-Pilot Tasks");
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

  it("wires the studio flow: provenance, generate, rating pins, card CRUD", async () => {
    const seeded = baseState();
    seeded.agent_run = {
      report_id: "abc123",
      run_id: "r1",
      mode: "studio",
      seeded_at: "2026-09-01T08:00:00Z",
    };
    m.get.mockResolvedValue(seeded);
    m.patchCard.mockResolvedValue(seeded);
    m.addCard.mockResolvedValue(seeded);
    m.deleteCard.mockResolvedValue(seeded);
    const wrapper = mount(MemoStudioEditor, {
      props: { companyId: "zainar-inc", generateAvailable: true },
    });
    await flushPromises();

    // Provenance banner names the seeding run.
    expect(wrapper.text()).toContain("studio");
    expect(wrapper.text()).toContain("Cards seeded by the");

    // The header Generate button emits up to the Report view.
    const generateButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Generate report");
    expect(generateButton).toBeTruthy();
    await generateButton.trigger("click");
    expect(wrapper.emitted("generate")).toBeTruthy();

    // Editing a risk rating pins it (and keeps severity in sync).
    const ratingSelect = wrapper
      .findAll("select")
      .find((select) =>
        select
          .findAll("option")
          .some((option) => option.text() === "10/10"),
      );
    expect(ratingSelect).toBeTruthy();
    await ratingSelect.setValue("9/10");
    await flushPromises();
    expect(m.patchCard).toHaveBeenCalledWith(
      "zainar-inc",
      "risks_mitigations",
      expect.any(String),
      { agent_rating: "9/10", severity: "high" },
    );

    // Add card: reveal the title input, type, save.
    const addButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Add card");
    await addButton.trigger("click");
    const titleInput = wrapper.find("input[placeholder='New card title']");
    expect(titleInput.exists()).toBe(true);
    await titleInput.setValue("Key-person dependency");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Save card")
      .trigger("click");
    await flushPromises();
    expect(m.addCard).toHaveBeenCalledWith(
      "zainar-inc",
      "investment_thesis",
      { title: "Key-person dependency" },
    );

    // Remove card.
    await wrapper.find("button[aria-label='Remove card']").trigger("click");
    await flushPromises();
    expect(m.deleteCard).toHaveBeenCalled();
    wrapper.unmount();
  });

  it("reorders cards by dragging from the grip handle", async () => {
    const state = baseState();
    m.get.mockResolvedValue(state);
    m.reorderCards.mockResolvedValue(state);
    const wrapper = mount(MemoStudioEditor, {
      props: { companyId: "zainar-inc" },
    });
    await flushPromises();

    const grips = wrapper.findAll("button[aria-label='Drag to reorder']");
    expect(grips.length).toBeGreaterThan(1);
    // Arm the drag from the first thesis card's handle, then drop it on
    // the second thesis card.
    await grips.at(0).trigger("mousedown");
    let articles = wrapper.findAll("article");
    await articles.at(0).trigger("dragstart");
    // Dragging over the second card reorders the list LIVE, before any
    // drop: the preview puts the dragged card after it.
    await articles.at(1).trigger("dragover");
    articles = wrapper.findAll("article");
    expect(articles.at(0).text()).toContain(
      "Metrics create a late-stage frame.",
    );
    expect(articles.at(1).text()).toContain(
      "Existing networks become a positioning layer.",
    );
    // Releasing commits the previewed order.
    await articles.at(0).trigger("drop");
    await flushPromises();

    expect(m.reorderCards).toHaveBeenCalledWith(
      "zainar-inc",
      "investment_thesis",
      ["thesis-2", "thesis-1"],
    );
  });
});
