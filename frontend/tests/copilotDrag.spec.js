import { describe, expect, it, beforeEach, vi } from "vitest";
import {
  COPILOT_LENS_MIME,
  acceptLensDrop,
  copilotLensDragging,
  endLensDrag,
  isLensDrag,
  startLensDrag,
} from "../src/copilotDrag.js";

describe("copilotDrag", () => {
  beforeEach(() => {
    endLensDrag();
  });

  it("detects lens drag from active dragging state", () => {
    copilotLensDragging.value = true;
    expect(isLensDrag({ dataTransfer: { types: [] } })).toBe(true);
  });

  it("starts drag with custom and plain mime types", () => {
    const setData = vi.fn();
    startLensDrag({
      dataTransfer: {
        effectAllowed: "",
        setData,
        setDragImage: () => {},
      },
      currentTarget: document.createElement("div"),
    });
    expect(copilotLensDragging.value).toBe(true);
    expect(setData).toHaveBeenCalledWith(COPILOT_LENS_MIME, "1");
    expect(setData).toHaveBeenCalledWith("text/plain", "copilot-lens");
  });

  it("accepts drop when lens is dragging", () => {
    copilotLensDragging.value = true;
    const event = {
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
      dataTransfer: { dropEffect: "", types: [] },
    };
    expect(acceptLensDrop(event)).toBe(true);
    expect(event.preventDefault).toHaveBeenCalled();
  });
});
