<script setup>
// The viewer's Export menu (R25): PDF for sharing (when its PDF is ready),
// Word for editing, both languages as a .zip. Every entry is an explicit
// export (purpose=export) and is reported to the parent for telemetry.
import { onBeforeUnmount, onMounted, ref } from "vue";
import { ChevronDown, Download } from "lucide-vue-next";
import { useT } from "../../i18n.js";

defineProps({
  // [{ id, label, hint?, href, download? }]
  options: { type: Array, default: () => [] },
  // Drop the button's label (narrow headers): the icon and chevron remain.
  compact: { type: Boolean, default: false },
});

const emit = defineEmits(["select"]);
const t = useT();

const open = ref(false);
const root = ref(null);

function choose(option) {
  open.value = false;
  emit("select", option);
}

function onPointerDown(event) {
  if (open.value && root.value && !root.value.contains(event.target)) open.value = false;
}

function onKeydown(event) {
  if (event.key === "Escape" && open.value) {
    event.stopPropagation();
    open.value = false;
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
  <div ref="root" class="relative">
    <button
      type="button"
      class="inline-flex items-center gap-1 rounded border border-subtle bg-surface px-2.5 py-1 text-xs font-medium text-ink-secondary hover:bg-surface-muted hover:text-ink-primary focus-ring"
      :title="t('viewer.export_menu')"
      :aria-label="t('viewer.export_menu')"
      aria-haspopup="menu"
      :aria-expanded="open"
      data-testid="viewer-export"
      @click="open = !open"
    >
      <Download class="h-3.5 w-3.5" />
      <span v-if="!compact" class="max-sm:hidden">{{ t("documents.export") }}</span>
      <ChevronDown class="h-3 w-3 text-ink-muted" />
    </button>
    <div v-if="open" class="toolbar-menu !min-w-[14.5rem]" role="menu" data-testid="viewer-export-menu">
      <a
        v-for="option in options"
        :key="option.id"
        :href="option.href"
        :download="option.download || ''"
        class="toolbar-menu-item flex-col !items-start !gap-0"
        role="menuitem"
        :data-testid="`viewer-export-${option.id}`"
        @click="choose(option)"
      >
        <span>{{ option.label }}</span>
        <span v-if="option.hint" class="text-caption1 text-ink-muted">{{ option.hint }}</span>
      </a>
    </div>
  </div>
</template>
