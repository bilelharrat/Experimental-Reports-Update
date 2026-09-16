<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Bell,
  Building2,
  ChevronLeft,
  FileText,
  Gauge,
  Newspaper,
  Search,
  TrendingUp,
  X,
} from "lucide-vue-next";
import { useT } from "../i18n.js";
import { WELCOME_TOUR_STEPS } from "../welcomeTour.js";
import BrandMark from "./BrandMark.vue";
import PulseECGIcon from "./PulseECGIcon.vue";
import WarrenMark from "./WarrenMark.vue";

const props = defineProps({
  open: { type: Boolean, default: false },
});

const emit = defineEmits(["close"]);
const t = useT();
const router = useRouter();
const route = useRoute();

// How long to wait for a step's target to exist after navigating before giving
// up and centering the callout. A cold route chunk can take a few frames.
const TARGET_TIMEOUT_MS = 1600;
const SPOTLIGHT_PADDING = 8;
const CALLOUT_WIDTH = 380;
const VIEWPORT_MARGIN = 16;
const CALLOUT_GAP = 14;

const step = ref(0);
const spot = ref(null);
const seeking = ref(false);
const panel = ref(null);
// Where the app was when the tour started, so a tour is never destructive.
const entryRoute = ref(null);
let seekToken = 0;

// The hero page lists what the app does; each step after it walks one desk.
const featureRows = computed(() => [
  { id: "home", icon: Search, title: t("welcome.row_home_title"), body: t("welcome.row_home_body") },
  { id: "memo", icon: FileText, title: t("welcome.row_memo_title"), body: t("welcome.row_memo_body") },
  { id: "markets", icon: TrendingUp, title: t("welcome.row_markets_title"), body: t("welcome.row_markets_body") },
  { id: "tracking", icon: Gauge, title: t("welcome.row_tracking_title"), body: t("welcome.row_tracking_body") },
  { id: "warren", icon: null, title: t("welcome.row_warren_title"), body: t("welcome.row_warren_body") },
]);

// Copy for each step, merged onto the navigation catalog in welcomeTour.js.
const content = computed(() => ({
  welcome: { title: t("welcome.title"), body: t("welcome.subtitle") },
  home: {
    icon: Search,
    title: t("welcome.home_title"),
    body: t("welcome.home_body"),
    tips: [
      { text: t("welcome.home_tip_command"), keys: ["⌘", "K"] },
      { text: t("welcome.home_tip_add") },
    ],
  },
  research: {
    icon: Building2,
    title: t("welcome.research_title"),
    body: t("welcome.research_body"),
    tips: [
      { text: t("welcome.research_tip_files") },
      { text: t("welcome.research_tip_decision") },
    ],
  },
  memo: {
    icon: FileText,
    title: t("welcome.memo_title"),
    body: t("welcome.memo_body"),
    tips: [
      { text: t("welcome.memo_tip_new"), keys: ["⌘", "N"] },
      { text: t("welcome.memo_tip_studio") },
    ],
  },
  markets: {
    icon: TrendingUp,
    title: t("welcome.markets_title"),
    body: t("welcome.markets_body"),
    tips: [
      { text: t("welcome.markets_tip_pulse"), pulse: true },
      { text: t("welcome.markets_tip_news"), icon: Newspaper },
      { text: t("welcome.markets_tip_alerts"), icon: Bell },
    ],
  },
  tracking: {
    icon: Gauge,
    title: t("welcome.tracking_title"),
    body: t("welcome.tracking_body"),
    tips: [{ text: t("welcome.tracking_tip_badge") }],
  },
  warren: {
    warren: true,
    title: t("welcome.warren_title"),
    body: t("welcome.warren_body"),
    tips: [
      { text: t("welcome.warren_tip_open") },
      { text: t("welcome.warren_tip_drag") },
      { text: t("welcome.warren_tip_name") },
    ],
  },
}));

const steps = computed(() =>
  WELCOME_TOUR_STEPS.map((entry) => ({ ...entry, ...(content.value[entry.id] || {}) })),
);

const current = computed(() => steps.value[step.value] || steps.value[0]);
const isHero = computed(() => current.value.kind === "hero");
const isFirst = computed(() => step.value === 0);
const isLast = computed(() => step.value === steps.value.length - 1);
// A spotlit step dims through the cutout; hero and unanchored steps dim flat.
const isSpotlit = computed(() => Boolean(spot.value) && !isHero.value);

const spotlightStyle = computed(() => {
  const s = spot.value;
  if (!s) return {};
  return {
    top: `${s.top}px`,
    left: `${s.left}px`,
    width: `${s.width}px`,
    height: `${s.height}px`,
    borderRadius: `${s.radius}px`,
  };
});

/** Place the callout beside the target, clamped into the viewport. */
const calloutStyle = computed(() => {
  const s = spot.value;
  const vw = typeof window === "undefined" ? 1024 : window.innerWidth;
  const vh = typeof window === "undefined" ? 768 : window.innerHeight;
  const width = Math.min(CALLOUT_WIDTH, vw - VIEWPORT_MARGIN * 2);

  if (!s || isHero.value) {
    return {
      width: `${isHero.value ? Math.min(560, vw - VIEWPORT_MARGIN * 2) : width}px`,
      left: "50%",
      top: "50%",
      transform: "translate(-50%, -50%)",
    };
  }

  const place = current.value.placement || "bottom";
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  let left;
  let top;

  if (place === "right" || place === "left") {
    const right = s.left + s.width + CALLOUT_GAP;
    const fitsRight = right + width + VIEWPORT_MARGIN <= vw;
    left = place === "right" && fitsRight ? right : s.left - width - CALLOUT_GAP;
    if (left < VIEWPORT_MARGIN) left = fitsRight ? right : VIEWPORT_MARGIN;
    top = clamp(s.top + s.height / 2 - 150, VIEWPORT_MARGIN, Math.max(VIEWPORT_MARGIN, vh - 340));
  } else {
    left = clamp(s.left + s.width / 2 - width / 2, VIEWPORT_MARGIN, Math.max(VIEWPORT_MARGIN, vw - width - VIEWPORT_MARGIN));
    const below = s.top + s.height + CALLOUT_GAP;
    const fitsBelow = below + 300 + VIEWPORT_MARGIN <= vh;
    top = fitsBelow ? below : Math.max(VIEWPORT_MARGIN, s.top - 300 - CALLOUT_GAP);
  }

  return { width: `${width}px`, left: `${left}px`, top: `${top}px` };
});

function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * One frame, or 32ms, whichever lands first. Browsers suspend
 * requestAnimationFrame in background tabs and hidden windows, so a tour that
 * waited on rAF alone would freeze mid-step and never find its control.
 */
function raf() {
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(finish);
    setTimeout(finish, 32);
  });
}

/** Poll for a step's target: the route's view may still be mounting. */
async function waitForTarget(selector, token) {
  if (!selector || typeof document === "undefined") return null;
  const deadline = Date.now() + TARGET_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (token !== seekToken) return null;
    const el = document.querySelector(selector);
    if (el) {
      const box = el.getBoundingClientRect();
      if (box.width > 0 && box.height > 0) return el;
    }
    await raf();
  }
  return null;
}

function measure(el) {
  if (!el) {
    spot.value = null;
    return;
  }
  const box = el.getBoundingClientRect();
  if (box.width <= 0 || box.height <= 0) {
    spot.value = null;
    return;
  }
  const style = typeof getComputedStyle === "function" ? getComputedStyle(el) : null;
  const radius = Number.parseFloat(style?.borderRadius || "") || 10;
  spot.value = {
    top: box.top - SPOTLIGHT_PADDING,
    left: box.left - SPOTLIGHT_PADDING,
    width: box.width + SPOTLIGHT_PADDING * 2,
    height: box.height + SPOTLIGHT_PADDING * 2,
    radius: radius + SPOTLIGHT_PADDING,
    selector: currentSelector(),
  };
}

function currentSelector() {
  return current.value.target || null;
}

/** Drive the app to this step's screen, then spotlight its control. */
async function applyStep() {
  const entry = current.value;
  const token = (seekToken += 1);

  if (entry.kind === "hero" || !entry.target) {
    spot.value = null;
  }

  if (entry.route && router) {
    seeking.value = true;
    try {
      await router.push(entry.route);
    } catch {
      // A redirect or an identical route rejects; the step still shows.
    }
  }

  if (token !== seekToken) return;
  await nextTick();

  if (entry.kind === "hero" || !entry.target) {
    seeking.value = false;
    spot.value = null;
    return;
  }

  const el = await waitForTarget(entry.target, token);
  if (token !== seekToken) return;

  if (el && typeof el.scrollIntoView === "function") {
    const box = el.getBoundingClientRect();
    const vh = typeof window === "undefined" ? 768 : window.innerHeight;
    if (box.top < 0 || box.bottom > vh) {
      el.scrollIntoView({
        block: "center",
        behavior: prefersReducedMotion() ? "auto" : "smooth",
      });
      await raf();
      await raf();
    }
  }

  if (token !== seekToken) return;
  measure(el);
  seeking.value = false;
}

function remeasure() {
  const selector = currentSelector();
  if (!props.open || !selector || isHero.value) return;
  measure(document.querySelector(selector));
}

function goTo(index) {
  const next = Math.max(0, Math.min(steps.value.length - 1, index));
  if (next === step.value) return;
  step.value = next;
  applyStep();
}

function advance() {
  if (isLast.value) {
    emit("close");
    return;
  }
  goTo(step.value + 1);
}

function back() {
  goTo(step.value - 1);
}

/** Tapping the dimmed area moves on, the way Apple's coach marks do. */
function onScrimClick() {
  if (isHero.value) return;
  advance();
}

function onKeydown(event) {
  if (event.key === "Escape") {
    event.stopPropagation();
    emit("close");
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    if (!isLast.value) goTo(step.value + 1);
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    back();
  }
}

function bindViewportListeners(on) {
  if (typeof window === "undefined") return;
  const method = on ? "addEventListener" : "removeEventListener";
  window[method]("resize", remeasure);
  window[method]("scroll", remeasure, true);
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      entryRoute.value = route?.fullPath || null;
      step.value = 0;
      spot.value = null;
      seeking.value = false;
      bindViewportListeners(true);
      nextTick(() => {
        panel.value?.focus?.();
        applyStep();
      });
    } else {
      seekToken += 1;
      seeking.value = false;
      spot.value = null;
      bindViewportListeners(false);
      // Put the app back where the tour found it: a walkthrough should not
      // silently relocate the person who skipped it.
      const returnTo = entryRoute.value;
      entryRoute.value = null;
      if (returnTo && router && route?.fullPath !== returnTo) {
        router.push(returnTo).catch(() => {});
      }
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  seekToken += 1;
  bindViewportListeners(false);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet-scrim">
      <div v-if="open" class="welcome-tour-root fixed inset-0 z-[70]" data-testid="welcome-tour">
        <!-- The dim. Flat for the hero and for steps whose control isn't on
             screen; a cutout around the control everywhere else. -->
        <button
          type="button"
          class="welcome-tour-scrim absolute inset-0"
          :class="{ 'is-flat': !isSpotlit }"
          :aria-label="t('welcome.continue')"
          tabindex="-1"
          @click="onScrimClick"
        />
        <div
          v-if="isSpotlit"
          class="welcome-tour-spotlight"
          :class="{ 'is-still': prefersReducedMotion() }"
          :style="spotlightStyle"
          data-testid="welcome-tour-spotlight"
          aria-hidden="true"
        />

        <div
          ref="panel"
          class="welcome-tour-callout sheet-panel"
          :class="{ 'is-hero': isHero, 'is-anchored': isSpotlit }"
          :style="calloutStyle"
          role="dialog"
          aria-modal="true"
          :aria-label="t('welcome.title')"
          tabindex="-1"
          @keydown="onKeydown"
        >
          <button
            v-if="!isLast"
            type="button"
            class="icon-btn absolute right-2.5 top-2.5 z-10"
            :aria-label="t('welcome.close')"
            data-testid="welcome-tour-skip"
            @click="emit('close')"
          >
            <X :size="15" />
          </button>

          <div class="welcome-tour-body" :class="isHero ? 'px-8 pt-10' : 'px-6 pt-6'">
            <!-- Hero: what the app does, then the walk begins. -->
            <template v-if="isHero">
              <div class="flex flex-col items-center text-center">
                <div class="welcome-tour-hero-tile" aria-hidden="true">
                  <BrandMark :size="44" />
                </div>
                <h2 class="mt-5 text-title1 text-ink-primary" data-testid="welcome-tour-title">
                  {{ current.title }}
                </h2>
                <p class="mt-2 max-w-[40ch] text-callout text-ink-muted">
                  {{ current.body }}
                </p>
                <ul class="mt-7 w-full space-y-4 text-left">
                  <li v-for="row in featureRows" :key="row.id" class="flex items-start gap-4">
                    <div class="welcome-tour-row-icon" aria-hidden="true">
                      <WarrenMark v-if="row.id === 'warren'" :size="36" />
                      <component :is="row.icon" v-else :size="20" />
                    </div>
                    <div class="min-w-0">
                      <div class="text-headline text-ink-primary">{{ row.title }}</div>
                      <div class="text-subheadline text-ink-muted">{{ row.body }}</div>
                    </div>
                  </li>
                </ul>
              </div>
            </template>

            <!-- A step on the real screen: compact, left-aligned, beside the
                 control it is describing. -->
            <template v-else>
              <div class="flex items-start gap-3">
                <div class="welcome-tour-glyph" :class="{ 'is-warren': current.warren }" aria-hidden="true">
                  <WarrenMark v-if="current.warren" :size="38" />
                  <component :is="current.icon" v-else :size="20" />
                </div>
                <div class="min-w-0 flex-1 pr-6">
                  <h2 class="text-headline font-semibold text-ink-primary" data-testid="welcome-tour-title">
                    {{ current.title }}
                  </h2>
                  <p class="mt-1.5 text-subheadline text-ink-secondary">
                    {{ current.body }}
                  </p>
                </div>
              </div>
              <ul v-if="current.tips?.length" class="mt-4 space-y-2">
                <li v-for="(tip, index) in current.tips" :key="index" class="welcome-tour-tip">
                  <span class="welcome-tour-tip-icon" aria-hidden="true">
                    <PulseECGIcon v-if="tip.pulse" :size="15" />
                    <component :is="tip.icon" v-else-if="tip.icon" :size="15" />
                    <span v-else class="welcome-tour-tip-dot" />
                  </span>
                  <span class="min-w-0 flex-1 text-footnote text-ink-primary">{{ tip.text }}</span>
                  <span v-if="tip.keys" class="flex shrink-0 items-center gap-0.5">
                    <kbd v-for="key in tip.keys" :key="key" class="kbd">{{ key }}</kbd>
                  </span>
                </li>
              </ul>
            </template>
          </div>

          <div class="flex flex-col gap-3" :class="isHero ? 'px-8 pb-7 pt-2' : 'px-6 pb-5 pt-3'">
            <div
              class="welcome-tour-dots"
              role="tablist"
              :aria-label="t('welcome.page_of', { current: step + 1, total: steps.length })"
            >
              <button
                v-for="(entry, index) in steps"
                :key="entry.id"
                type="button"
                role="tab"
                class="welcome-tour-dot"
                :aria-selected="index === step"
                :aria-label="t('welcome.page_of', { current: index + 1, total: steps.length })"
                @click="goTo(index)"
              />
            </div>
            <div class="flex items-center gap-2">
              <button
                v-if="!isFirst"
                type="button"
                class="btn-plain"
                data-testid="welcome-tour-back"
                @click="back"
              >
                <ChevronLeft :size="16" />
                {{ t("welcome.back") }}
              </button>
              <button
                type="button"
                class="btn-filled ml-auto min-w-[9.5rem] justify-center"
                data-testid="welcome-tour-next"
                @click="advance"
              >
                {{ isLast ? t("welcome.get_started") : t("welcome.continue") }}
              </button>
            </div>
            <p v-if="isHero" class="text-center text-caption1 text-ink-subtle">
              {{ t("welcome.replay_hint") }}
            </p>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
