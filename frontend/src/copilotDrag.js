import { ref } from "vue";

export const COPILOT_LENS_MIME = "application/x-bsh-copilot-lens";
export const COPILOT_LENS_PLAIN = "copilot-lens";

export const copilotLensDragging = ref(false);
export const copilotDropHoverKey = ref(null);

export function setLensDragging(active) {
  copilotLensDragging.value = Boolean(active);
}

export function setDropHover(key) {
  copilotDropHoverKey.value = key || null;
}

export function clearDropHover() {
  copilotDropHoverKey.value = null;
}

export function isLensDrag(event) {
  if (copilotLensDragging.value) return true;
  const types = event?.dataTransfer?.types;
  if (!types) return false;
  const list = Array.from(types);
  return list.includes(COPILOT_LENS_MIME) || list.includes("text/plain");
}

export function startLensDrag(event) {
  if (!event?.dataTransfer) return;
  event.dataTransfer.effectAllowed = "copy";
  event.dataTransfer.setData(COPILOT_LENS_MIME, "1");
  event.dataTransfer.setData("text/plain", COPILOT_LENS_PLAIN);
  try {
    event.dataTransfer.setDragImage(event.currentTarget, 20, 20);
  } catch {
    /* setDragImage optional */
  }
  setLensDragging(true);
}

export function endLensDrag() {
  setLensDragging(false);
  clearDropHover();
}

export function acceptLensDrop(event) {
  if (!isLensDrag(event)) return false;
  event.preventDefault();
  event.stopPropagation();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  return true;
}
