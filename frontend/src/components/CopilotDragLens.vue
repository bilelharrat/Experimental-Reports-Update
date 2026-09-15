<script setup>
import { computed, onBeforeUnmount, watch } from "vue";
import WarrenMark from "./WarrenMark.vue";
import { copilotLensDragging, endLensDrag, startLensDrag } from "../copilotDrag.js";
import { useT } from "../i18n.js";

const props = defineProps({
  visible: { type: Boolean, default: true },
  copilotOpen: { type: Boolean, default: false },
});

const t = useT();

const showLens = computed(() => props.visible && !props.copilotOpen);

watch(
  () => copilotLensDragging.value,
  (active) => {
    if (typeof document === "undefined") return;
    if (active) document.body.dataset.copilotDragging = "true";
    else delete document.body.dataset.copilotDragging;
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (typeof document !== "undefined") delete document.body.dataset.copilotDragging;
});
</script>

<template>
  <div
    v-if="showLens"
    class="copilot-drag-lens"
    draggable="true"
    role="button"
    tabindex="0"
    :aria-label="t('copilot.drag_tell_lens')"
    :title="t('copilot.drag_tell_lens')"
    @dragstart.stop="startLensDrag"
    @dragend.stop="endLensDrag"
  >
    <WarrenMark :size="20" />
    <span class="copilot-drag-lens-label">{{ t("copilot.drag_tell_short") }}</span>
  </div>
</template>
