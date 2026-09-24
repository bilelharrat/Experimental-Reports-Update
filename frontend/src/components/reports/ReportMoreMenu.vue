<script setup>
// The viewer header's overflow menu: Print, Copy link, and the review moves
// the reader's permissions allow (G2) — Request review (memo:edit);
// Approve, Back to draft and Withdraw (memo:approve). Each review move asks
// twice, the app's confirm pattern; the parent makes the call.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Ban, Check, CircleCheck, Link2, MoreHorizontal, Printer, Send, Undo2 } from "lucide-vue-next";
import { useT } from "../../i18n.js";
import { useTwoStepArm } from "../../reportStatus.js";

const props = defineProps({
  canPrint: { type: Boolean, default: false },
  canCopyLink: { type: Boolean, default: false },
  linkCopied: { type: Boolean, default: false },
  // A link the clipboard refused, shown for copying by hand.
  fallbackLink: { type: String, default: "" },
  // Review states the reader may move to, in order (reviewActions()).
  reviewMoves: { type: Array, default: () => [] },
  busy: { type: String, default: "" },
});

const emit = defineEmits(["print", "copy-link", "review"]);
const t = useT();

const open = ref(false);
const root = ref(null);
const arm = useTwoStepArm();

const hasItems = computed(() => props.canPrint || props.canCopyLink || props.reviewMoves.length > 0);

const MOVE_ICONS = { in_review: Send, approved: CircleCheck, draft: Undo2, withdrawn: Ban };

function moveLabel(state) {
  if (props.busy === state) return t("review.saving");
  if (arm.armed.value === state) return t(`review.confirm.${state}`);
  return t(`review.action.${state}`);
}

function onReview(state) {
  if (props.busy) return;
  if (!arm.trigger(state)) return;
  open.value = false;
  emit("review", state);
}

function onPrint() {
  open.value = false;
  emit("print");
}

function onCopy() {
  emit("copy-link");
}

function toggle() {
  open.value = !open.value;
  if (!open.value) arm.reset();
}

function onPointerDown(event) {
  if (open.value && root.value && !root.value.contains(event.target)) {
    open.value = false;
    arm.reset();
  }
}

function onKeydown(event) {
  if (event.key === "Escape" && open.value) {
    event.stopPropagation();
    open.value = false;
    arm.reset();
  }
}

onMounted(() => {
  document.addEventListener("pointerdown", onPointerDown);
  document.addEventListener("keydown", onKeydown, true);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onPointerDown);
  document.removeEventListener("keydown", onKeydown, true);
});
</script>

<template>
  <div v-if="hasItems" ref="root" class="relative">
    <button
      type="button"
      class="inline-flex items-center rounded border border-subtle bg-surface p-1.5 text-xs text-ink-muted hover:bg-surface-muted hover:text-ink-primary focus-ring"
      :title="t('viewer.more')"
      :aria-label="t('viewer.more')"
      aria-haspopup="menu"
      :aria-expanded="open"
      data-testid="viewer-more"
      @click="toggle"
    >
      <MoreHorizontal class="h-3.5 w-3.5" />
    </button>
    <div v-if="open" class="toolbar-menu !min-w-[14rem]" role="menu" data-testid="viewer-more-menu">
      <button
        v-if="canPrint"
        type="button"
        class="toolbar-menu-item"
        role="menuitem"
        data-testid="viewer-print"
        @click="onPrint"
      >
        <Printer class="h-3.5 w-3.5 text-ink-muted" />
        {{ t("viewer.print") }}
      </button>
      <button
        v-if="canCopyLink"
        type="button"
        class="toolbar-menu-item"
        role="menuitem"
        data-testid="viewer-copy-link"
        @click="onCopy"
      >
        <Check v-if="linkCopied" class="h-3.5 w-3.5 text-success" />
        <Link2 v-else class="h-3.5 w-3.5 text-ink-muted" />
        {{ linkCopied ? t("viewer.link_copied") : t("viewer.copy_link") }}
      </button>
      <div v-if="fallbackLink" class="px-2.5 pb-1.5 pt-0.5">
        <div class="text-caption1 text-ink-muted">{{ t("viewer.copy_failed") }}</div>
        <input
          class="field field-sm mt-1 w-full"
          readonly
          :value="fallbackLink"
          :aria-label="t('viewer.copy_link')"
          data-testid="viewer-link-fallback"
          @focus="$event.target.select()"
        />
      </div>
      <template v-if="reviewMoves.length">
        <div
          class="px-2.5 pb-0.5 pt-1.5 text-caption1 font-semibold text-ink-muted"
          :class="canPrint || canCopyLink ? 'mt-1 border-t border-subtle' : ''"
        >
          {{ t("review.heading") }}
        </div>
        <button
          v-for="state in reviewMoves"
          :key="state"
          type="button"
          class="toolbar-menu-item"
          :class="arm.armed.value === state ? 'font-semibold' : ''"
          role="menuitem"
          :disabled="Boolean(busy)"
          :data-testid="`viewer-review-${state}`"
          @click="onReview(state)"
        >
          <component :is="MOVE_ICONS[state] || Check" class="h-3.5 w-3.5 text-ink-muted" />
          {{ moveLabel(state) }}
        </button>
      </template>
    </div>
  </div>
</template>
