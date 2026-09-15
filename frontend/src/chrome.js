// Shell chrome state shared by App.vue, Sidebar.vue, and the desks.

import { onBeforeUnmount, onMounted, ref, watch } from "vue";

/** True while a desk's large title is on screen; the toolbar's small title
 *  stays hidden until it scrolls away (the macOS/iOS large-title handoff). */
export const largeTitleVisible = ref(false);

let largeTitleOwner = 0;
let registeredTitles = 0;
let autoObserver = null;

/** Register the element holding a desk's large title. The element may appear
 *  later (a company header renders once its record loads). */
export function useLargeTitle(elRef) {
  const id = ++largeTitleOwner;
  let observer = null;
  let mounted = false;

  function observe(el) {
    observer?.disconnect();
    observer = null;
    if (!mounted || largeTitleOwner !== id) return;
    if (!el || typeof IntersectionObserver === "undefined") {
      largeTitleVisible.value = false;
      return;
    }
    largeTitleVisible.value = true;
    observer = new IntersectionObserver(
      ([entry]) => {
        if (largeTitleOwner === id) largeTitleVisible.value = entry.isIntersecting;
      },
      // The toolbar covers the top 52px, so a title tucked under it is gone.
      { rootMargin: "-52px 0px 0px 0px" },
    );
    observer.observe(el);
  }

  onMounted(() => {
    mounted = true;
    registeredTitles += 1;
    autoObserver?.disconnect();
    autoObserver = null;
    observe(elRef.value);
  });

  watch(elRef, (el) => observe(el));

  onBeforeUnmount(() => {
    mounted = false;
    registeredTitles -= 1;
    observer?.disconnect();
    if (largeTitleOwner === id) largeTitleVisible.value = false;
  });
}

/** For desks that don't register a title themselves: watch the first h1 in
 *  the routed view so every page gets the same handoff. */
export function autoObserveLargeTitle(root) {
  autoObserver?.disconnect();
  autoObserver = null;
  if (registeredTitles > 0 || !root || typeof IntersectionObserver === "undefined") return;
  const h1 = root.querySelector("h1");
  if (!h1) {
    largeTitleVisible.value = false;
    return;
  }
  autoObserver = new IntersectionObserver(
    ([entry]) => {
      if (registeredTitles === 0) largeTitleVisible.value = entry.isIntersecting;
    },
    { rootMargin: "-52px 0px 0px 0px" },
  );
  autoObserver.observe(h1);
}

/** Reactive media query. Where matchMedia is missing (tests) it reports
 *  `fallback`, so the desktop layout is the default. */
export function useMediaQuery(query, fallback = true) {
  const matches = ref(fallback);
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return matches;
  }
  const mql = window.matchMedia(query);
  matches.value = mql.matches;
  const onChange = (event) => {
    matches.value = event.matches;
  };
  onMounted(() => mql.addEventListener?.("change", onChange));
  onBeforeUnmount(() => mql.removeEventListener?.("change", onChange));
  return matches;
}
