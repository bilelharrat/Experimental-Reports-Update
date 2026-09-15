<script setup>
// "About Acme ⌄" under the Ask Warren title: which company Warren is reading,
// switchable from any page (the Mac's company menu in the Ask toolbar).
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { Check, ChevronDown, Search } from "lucide-vue-next";
import Monogram from "./Monogram.vue";
import { useT } from "../i18n.js";

const props = defineProps({
  companies: { type: Array, default: () => [] },
  // Most recent first; shown above the full list.
  recentIds: { type: Array, default: () => [] },
  modelValue: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue"]);

const t = useT();
const open = ref(false);
const query = ref("");
const root = ref(null);
const filterInput = ref(null);

const byId = computed(() => new Map(props.companies.map((company) => [company.id, company])));
const selected = computed(() => byId.value.get(props.modelValue) || null);
const showFilter = computed(() => props.companies.length > 7);

const recent = computed(() => {
  if (query.value.trim()) return [];
  return props.recentIds
    .map((id) => byId.value.get(id))
    .filter(Boolean)
    .slice(0, 3);
});

const rest = computed(() => {
  const q = query.value.trim().toLowerCase();
  const recentSet = new Set(recent.value.map((company) => company.id));
  return [...props.companies]
    .filter((company) => company?.id && !recentSet.has(company.id))
    .filter((company) => {
      if (!q) return true;
      return `${company.name || ""} ${company.ticker || ""}`.toLowerCase().includes(q);
    })
    .sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")))
    .slice(0, 60);
});

function toggle() {
  open.value = !open.value;
  if (!open.value) return;
  query.value = "";
  if (showFilter.value) nextTick(() => filterInput.value?.focus());
}

function choose(company) {
  open.value = false;
  if (company.id !== props.modelValue) emit("update:modelValue", company.id);
}

function onKeydown(event) {
  if (event.key === "Escape" && open.value) {
    // Close the menu only; Escape again closes the panel.
    event.stopPropagation();
    open.value = false;
  }
}

function onDocPointerDown(event) {
  if (open.value && !root.value?.contains(event.target)) open.value = false;
}

onMounted(() => document.addEventListener("pointerdown", onDocPointerDown));
onBeforeUnmount(() => document.removeEventListener("pointerdown", onDocPointerDown));
</script>

<template>
  <div ref="root" class="relative min-w-0" @keydown="onKeydown">
    <button
      type="button"
      class="warren-about focus-ring"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :title="t('copilot.switch_company')"
      @click="toggle"
    >
      <span class="shrink-0 text-ink-muted">{{ t("copilot.about") }}</span>
      <span
        class="min-w-0 truncate font-semibold"
        :class="selected ? 'text-ink-primary' : 'text-accent-ink'"
      >
        {{ selected?.name || t("copilot.choose_company") }}
      </span>
      <ChevronDown class="h-3.5 w-3.5 shrink-0 text-ink-muted" />
    </button>

    <div v-if="open" class="toolbar-menu warren-about-menu" role="listbox">
      <div v-if="showFilter" class="relative mb-1">
        <Search
          class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted"
        />
        <input
          ref="filterInput"
          v-model="query"
          type="search"
          autocomplete="off"
          spellcheck="false"
          class="field field-sm !pl-8"
          :placeholder="t('copilot.filter_companies')"
          :aria-label="t('copilot.filter_companies')"
        />
      </div>

      <template v-if="recent.length">
        <div class="warren-menu-label">{{ t("copilot.recent") }}</div>
        <button
          v-for="company in recent"
          :key="`recent-${company.id}`"
          type="button"
          class="toolbar-menu-item"
          role="option"
          :aria-selected="company.id === modelValue"
          @click="choose(company)"
        >
          <Monogram :company="company" :size="20" tinted />
          <span class="min-w-0 flex-1 truncate">{{ company.name }}</span>
          <Check v-if="company.id === modelValue" class="h-3.5 w-3.5 shrink-0" />
        </button>
      </template>

      <div v-if="recent.length && rest.length" class="warren-menu-label">
        {{ t("copilot.all_companies") }}
      </div>
      <button
        v-for="company in rest"
        :key="company.id"
        type="button"
        class="toolbar-menu-item"
        role="option"
        :aria-selected="company.id === modelValue"
        @click="choose(company)"
      >
        <Monogram :company="company" :size="20" tinted />
        <span class="min-w-0 flex-1 truncate">{{ company.name }}</span>
        <span v-if="company.ticker" class="shrink-0 text-caption1 text-ink-muted">{{ company.ticker }}</span>
        <Check v-if="company.id === modelValue" class="h-3.5 w-3.5 shrink-0" />
      </button>

      <p v-if="!recent.length && !rest.length" class="px-2.5 py-2 text-footnote text-ink-muted">
        {{ t("toolbar.no_matches") }}
      </p>
    </div>
  </div>
</template>
