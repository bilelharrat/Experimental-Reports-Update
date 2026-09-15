<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Command, CornerDownLeft, Search } from "lucide-vue-next";
import Monogram from "./Monogram.vue";
import { parseMarketCommand, routeForMarketCommand, suggestMarketCommands } from "../marketCommands.js";
import { useT } from "../i18n.js";

const props = defineProps({
  open: { type: Boolean, default: false },
  companies: { type: Array, default: () => [] },
});

const emit = defineEmits(["close"]);
const t = useT();
const router = useRouter();
const query = ref("");
const active = ref(0);
const inputRef = ref(null);

const suggestions = computed(() =>
  suggestMarketCommands(query.value, { companies: props.companies, limit: 8 }),
);

watch(
  () => props.open,
  async (value) => {
    if (!value) return;
    query.value = "";
    active.value = 0;
    await nextTick();
    inputRef.value?.focus();
  },
);

watch(query, () => {
  active.value = 0;
});

function close() {
  emit("close");
}

function run(row) {
  const cmd =
    row ||
    suggestions.value[active.value] ||
    parseMarketCommand(query.value);
  if (!cmd || cmd.action === "help") return;
  const target = routeForMarketCommand(cmd);
  close();
  if (target) router.push(target);
}

function onKeydown(event) {
  if (!props.open) return;
  if (event.key === "Escape") {
    event.preventDefault();
    close();
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    active.value = Math.min(active.value + 1, Math.max(suggestions.value.length - 1, 0));
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    active.value = Math.max(active.value - 1, 0);
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    run(suggestions.value[active.value]);
  }
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div
    v-if="open"
    class="yf-cmd-backdrop"
    role="dialog"
    :aria-label="t('cmd.palette_label')"
    @click.self="close"
  >
    <div class="yf-cmd-panel">
      <div class="yf-cmd-input-wrap">
        <Search class="h-5 w-5 shrink-0 text-ink-muted" />
        <input
          ref="inputRef"
          v-model="query"
          type="text"
          class="yf-cmd-input focus-ring"
          :placeholder="t('cmd.placeholder')"
          :aria-label="t('cmd.placeholder')"
          autocomplete="off"
          spellcheck="false"
        />
        <kbd class="yf-cmd-kbd">{{ t("cmd.esc") }}</kbd>
      </div>
      <div class="yf-cmd-list" role="listbox">
        <button
          v-for="(row, index) in suggestions"
          :key="row.id"
          type="button"
          class="yf-cmd-item focus-ring"
          role="option"
          :aria-selected="index === active"
          :data-active="index === active"
          @mouseenter="active = index"
          @click="run(row)"
        >
          <Monogram
            v-if="row.companyId"
            :company="{ id: row.companyId, name: row.subtitle || row.title, ticker: row.ticker }"
            :size="30"
            tinted
          />
          <span v-else class="yf-cmd-glyph">
            <Command class="h-4 w-4" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-callout font-semibold text-ink-primary">
              {{ row.title }}
            </span>
            <span class="block truncate text-caption1 text-ink-muted">
              {{ row.subtitle }}
            </span>
          </span>
          <CornerDownLeft v-if="index === active" class="h-4 w-4 shrink-0 text-ink-muted" />
        </button>
      </div>
      <p class="yf-cmd-hint">{{ t("cmd.hint") }}</p>
    </div>
  </div>
</template>
