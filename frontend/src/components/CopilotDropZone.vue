<script setup>
import { computed, inject } from "vue";
import { Crosshair } from "lucide-vue-next";
import {
  acceptLensDrop,
  clearDropHover,
  copilotDropHoverKey,
  copilotLensDragging,
  endLensDrag,
  setDropHover,
} from "../copilotDrag.js";
import { activateCopilotTarget, dropZoneKey } from "../copilotTargets.js";
import { useT } from "../i18n.js";

const props = defineProps({
  companyId: { type: String, required: true },
  surface: { type: String, required: true },
  tab: { type: String, default: null },
  targetKind: { type: String, required: true },
  selection: { type: Object, default: () => ({}) },
  targetId: { type: String, default: "" },
  inspectable: { type: Boolean, default: true },
  block: { type: Boolean, default: false },
});

const openCopilot = inject("openCopilot", null);
const t = useT();

const zoneKey = computed(() =>
  dropZoneKey(
    props.targetKind,
    props.targetId
      || props.selection?.bullet_id
      || props.selection?.claim
      || props.selection?.metric_label
      || props.selection?.file_id
      || props.selection?.warning
      || props.selection?.code,
  ),
);

const fullSelection = computed(() => ({
  target_kind: props.targetKind,
  ...props.selection,
}));

const lensDragging = computed(() => copilotLensDragging.value);

const isHover = computed(
  () => lensDragging.value && copilotDropHoverKey.value === zoneKey.value,
);

function onDragEnter(event) {
  if (!acceptLensDrop(event)) return;
  setDropHover(zoneKey.value);
}

function onDragOver(event) {
  if (!acceptLensDrop(event)) return;
  setDropHover(zoneKey.value);
}

function onDragLeave(event) {
  if (event.currentTarget?.contains?.(event.relatedTarget)) return;
  if (copilotDropHoverKey.value === zoneKey.value) clearDropHover();
}

function onDrop(event) {
  if (!acceptLensDrop(event)) return;
  endLensDrag();
  inspectTarget();
}

function inspectTarget() {
  if (!openCopilot) return;
  activateCopilotTarget(openCopilot, {
    companyId: props.companyId,
    surface: props.surface,
    tab: props.tab,
    selection: fullSelection.value,
  });
}
</script>

<template>
  <div
    class="copilot-drop-zone"
    :class="{
      'copilot-drop-zone-block': block,
      'copilot-drop-zone-hover': isHover,
      'copilot-drop-zone-ready': lensDragging,
    }"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <slot />
    <button
      v-if="inspectable"
      type="button"
      class="copilot-drop-inspect focus-ring"
      :title="t('copilot.drag_tell_inspect')"
      :aria-label="t('copilot.drag_tell_inspect')"
      @click.stop="inspectTarget"
    >
      <Crosshair class="h-3 w-3" />
      <span class="copilot-drop-inspect-label">{{ t("copilot.drag_tell_inspect") }}</span>
    </button>
  </div>
</template>
