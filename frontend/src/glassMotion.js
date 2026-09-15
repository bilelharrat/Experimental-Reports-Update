// Glass motion: selection that glides instead of blinking, the web's answer
// to matchedGeometryEffect in the Mac terminal (MacGlassStyles.swift).
//
// - useGlider() drives one levitating glass pill that springs between the
//   selected rows of a source list (Sidebar.vue).
// - installGlassMotion() is a document-wide FLIP for .segmented thumbs and
//   .workspace-tab underlines, so every existing control glides without
//   touching its template. The CSS side is the glass-glide keyframes in
//   style.css.

import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const raf =
  typeof window !== "undefined" && typeof window.requestAnimationFrame === "function"
    ? (cb) => window.requestAnimationFrame(cb)
    : (cb) => setTimeout(cb, 16);

const caf =
  typeof window !== "undefined" && typeof window.cancelAnimationFrame === "function"
    ? (id) => window.cancelAnimationFrame(id)
    : (id) => clearTimeout(id);

function prefersReducedMotion() {
  return Boolean(
    typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );
}

/**
 * Track the row matching `selector` inside `containerRef` and expose the
 * geometry for a `.nav-glider` element. The first placement is instant so
 * the pill doesn't fly in from the top on load.
 */
export function useGlider(containerRef, selector, { enabled = ref(true) } = {}) {
  const style = ref({ "--glider-y": "0px", "--glider-h": "0px" });
  const visible = ref(false);
  const instant = ref(true);
  let mutationObserver = null;
  let resizeObserver = null;
  let frame = 0;

  function measure() {
    frame = 0;
    const root = containerRef.value;
    const row = enabled.value && root ? root.querySelector(selector) : null;
    if (!root || !row) {
      visible.value = false;
      instant.value = true;
      return;
    }
    const rootRect = root.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    style.value = {
      "--glider-y": `${Math.round(rowRect.top - rootRect.top)}px`,
      "--glider-h": `${Math.round(rowRect.height)}px`,
    };
    if (!visible.value) {
      instant.value = true;
      visible.value = true;
      raf(() => raf(() => (instant.value = false)));
    }
  }

  function schedule() {
    if (frame) caf(frame);
    frame = raf(measure);
  }

  // Glide at click time instead of when the route finishes resolving (lazy
  // views take a beat); the observer confirms the spot once it lands.
  function moveTo(row) {
    const root = containerRef.value;
    if (!enabled.value || !root || !row || !root.contains(row)) return;
    const rootRect = root.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    style.value = {
      "--glider-y": `${Math.round(rowRect.top - rootRect.top)}px`,
      "--glider-h": `${Math.round(rowRect.height)}px`,
    };
    visible.value = true;
  }

  onMounted(() => {
    const root = containerRef.value;
    if (!root) return;
    if (typeof MutationObserver !== "undefined") {
      mutationObserver = new MutationObserver(schedule);
      mutationObserver.observe(root, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ["class"],
      });
    }
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(schedule);
      resizeObserver.observe(root);
    }
    schedule();
  });

  watch(enabled, schedule);

  onBeforeUnmount(() => {
    mutationObserver?.disconnect();
    resizeObserver?.disconnect();
    if (frame) caf(frame);
  });

  return { style, visible, instant, moveTo };
}

const SELECTED_ATTRS = ["aria-selected", "data-selected", "aria-checked"];
const MOVER_SELECTOR = ".segmented-item, .workspace-tab";

function isSelected(el) {
  return SELECTED_ATTRS.some((attr) => el.getAttribute(attr) === "true");
}

function groupOf(el) {
  if (el.classList.contains("segmented-item")) return el.closest(".segmented");
  return el.closest('[role="tablist"]') || el.parentElement;
}

function selectedIn(group) {
  const items = group.querySelectorAll(MOVER_SELECTOR);
  for (const item of items) {
    if (groupOf(item) === group && isSelected(item)) return item;
  }
  return null;
}

function glide(from, to) {
  const a = from.getBoundingClientRect();
  const b = to.getBoundingClientRect();
  if (!a.width || !b.width) return;
  const dx = a.left - b.left;
  const sx = a.width / b.width;
  if (Math.abs(dx) < 1 && Math.abs(sx - 1) < 0.01) return;
  to.style.setProperty("--glide-dx", `${dx}px`);
  to.style.setProperty("--glide-sx", String(sx));
  to.removeAttribute("data-glide");
  // Reading layout restarts the animation when the same item is re-selected.
  void to.offsetWidth;
  to.setAttribute("data-glide", "true");
  const done = () => to.removeAttribute("data-glide");
  to.addEventListener("animationend", done, { once: true });
  setTimeout(done, 900);
}

/** Install the document-wide glide. Returns an uninstall function. */
export function installGlassMotion(root = typeof document !== "undefined" ? document.body : null) {
  if (!root || typeof MutationObserver === "undefined") return () => {};
  const lastSelected = new WeakMap();

  function remember(scope) {
    for (const item of scope.querySelectorAll(MOVER_SELECTOR)) {
      if (isSelected(item)) {
        const group = groupOf(item);
        if (group) lastSelected.set(group, item);
      }
    }
  }

  remember(root);

  const observer = new MutationObserver((records) => {
    const groups = new Set();
    for (const record of records) {
      if (record.type === "childList") {
        for (const node of record.addedNodes) {
          if (node.nodeType === 1) remember(node);
        }
        continue;
      }
      const target = record.target;
      if (target.nodeType !== 1 || !target.matches(MOVER_SELECTOR)) continue;
      const group = groupOf(target);
      if (group) groups.add(group);
    }
    const animate = !prefersReducedMotion();
    for (const group of groups) {
      const next = selectedIn(group);
      const previous = lastSelected.get(group);
      if (next) lastSelected.set(group, next);
      if (animate && next && previous && previous !== next && previous.isConnected) {
        glide(previous, next);
      }
    }
  });

  observer.observe(root, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: SELECTED_ATTRS,
  });

  return () => observer.disconnect();
}
