import { describe, expect, it } from "vitest";
import {
  buildDiscussPrompt,
  buildDiveDeeperPrompt,
  extractCitations,
  parseResearchTask,
  parseStructuredOutputs,
  resolveCitationTarget,
  resolveCopilotAction,
  stripResearchTaskBlock,
  stripStructuredBlocks,
} from "../src/copilotActions.js";

const t = (key) => {
  if (key === "copilot.prompt_discuss_selection") {
    return "Challenge this memo point ({bullet}).";
  }
  return key;
};

describe("copilotActions", () => {
  it("builds discuss prompts from memo selection", () => {
    const prompt = buildDiscussPrompt({
      section_title: "Risks",
      bullet_text: "Customer concentration is high.",
    });
    expect(prompt).toContain("Risks");
    expect(prompt).toContain("Customer concentration");
  });

  it("extracts parenthetical file citations", () => {
    const cites = extractCitations("Per (deck.pdf p.18) revenue grew.");
    expect(cites).toHaveLength(1);
    expect(cites[0].file).toBe("deck.pdf");
    expect(cites[0].page).toBe("18");
  });

  it("parses research task blocks", () => {
    const text =
      'Answer.\n```json\n{"research_task":{"title":"Follow up","description":"Check 10-K"}}\n```';
    expect(parseResearchTask(text)?.title).toBe("Follow up");
    expect(stripResearchTaskBlock(text)).not.toContain("```json");
  });

  it("resolves server action keys", () => {
    const action = resolveCopilotAction(
      {
        id: "discuss_selection",
        label_key: "copilot.action_discuss_selection",
        prompt_key: "copilot.prompt_discuss_selection",
      },
      t,
      { selection: { bullet_text: "ARR is recurring" } },
    );
    expect(action.label).toBe("copilot.action_discuss_selection");
    expect(action.prompt).toContain("ARR is recurring");
  });

  it("builds dive-deeper prompts", () => {
    const prompt = buildDiveDeeperPrompt({ bullet_text: "ARR grew 40%" });
    expect(prompt).toContain("dive-deeper");
    expect(prompt).toContain("ARR grew 40%");
  });

  it("parses structured output blocks", () => {
    const text =
      '```json\n{"suggested_edit":{"text":"Shorter"}}\n```\n```json\n{"research_task":{"title":"Task"}}\n```';
    const outputs = parseStructuredOutputs(text);
    expect(outputs.suggested_edit.text).toBe("Shorter");
    expect(outputs.research_task.title).toBe("Task");
    expect(stripStructuredBlocks(text)).not.toContain("```json");
  });

  it("resolves citation targets against indexed files", () => {
    const target = resolveCitationTarget(
      { file: "deck.pdf", page: "3" },
      [{ id: "f1", filename: "deck.pdf" }],
    );
    expect(target.kind).toBe("file");
    expect(target.file.id).toBe("f1");
  });
});
