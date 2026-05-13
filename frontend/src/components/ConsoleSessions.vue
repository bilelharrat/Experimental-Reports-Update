<script setup>
// Archived-sessions dropdown + read-only transcript modal. Lives below
// the active tab strip in CompanyConsole; opens a modal when a row is
// clicked.

import { ref } from "vue";
import { X, Loader2 } from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";

const tr = useT();

const props = defineProps({
  companyId: { type: String, required: true },
  sessions: { type: Array, required: true }, // archived metas
});

const open = ref(false);
const modalSid = ref(null);
const modalMeta = ref(null);
const modalTurns = ref([]);
const modalLoading = ref(false);

function toggle() {
  open.value = !open.value;
}

async function openModal(sid) {
  modalSid.value = sid;
  modalMeta.value = props.sessions.find((s) => s.id === sid) || null;
  modalLoading.value = true;
  try {
    modalTurns.value = await api.console.getTurns(props.companyId, sid);
    // Refresh meta in case the summary landed since the list call.
    modalMeta.value = await api.console.getSession(props.companyId, sid);
  } catch (e) {
    modalTurns.value = [];
  } finally {
    modalLoading.value = false;
  }
  open.value = false;
}

function closeModal() {
  modalSid.value = null;
  modalMeta.value = null;
  modalTurns.value = [];
}

function turnTime(ts) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return "";
  }
}
</script>

<template>
  <div class="relative">
    <button
      @click="toggle"
      class="text-xs text-ink-muted hover:text-ink-primary px-2 py-1 rounded hover:bg-surface-muted focus-ring"
    >
      {{ tr("console.archived_label", { count: sessions.length }) }} ▾
    </button>
    <div
      v-if="open"
      class="absolute right-0 mt-1 w-72 bg-surface border border-subtle rounded-card shadow-card z-30 max-h-80 overflow-y-auto"
    >
      <div v-if="sessions.length === 0" class="p-3 text-xs text-ink-muted">
        {{ tr("console.no_archived") }}
      </div>
      <button
        v-for="s in sessions"
        :key="s.id"
        @click="openModal(s.id)"
        class="block w-full text-left px-3 py-2 hover:bg-surface-muted focus-ring"
      >
        <div class="text-sm text-ink-primary truncate">
          {{ s.summary?.headline || s.title }}
        </div>
        <div class="text-xs text-ink-muted">{{ turnTime(s.archived_at || s.created_at) }}</div>
      </button>
    </div>

    <!-- Read-only transcript modal -->
    <div
      v-if="modalSid"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      @click.self="closeModal"
    >
      <div
        class="bg-surface rounded-card shadow-card border border-subtle max-w-3xl w-full max-h-[80vh] flex flex-col"
      >
        <div class="flex items-center justify-between gap-3 p-4 border-b border-subtle">
          <div>
            <div class="font-display text-base font-semibold text-ink-primary truncate">
              {{ modalMeta?.summary?.headline || modalMeta?.title || "—" }}
            </div>
            <div class="text-xs text-ink-muted">
              {{ tr("console.read_only_transcript") }}
            </div>
          </div>
          <button
            @click="closeModal"
            class="p-1 rounded hover:bg-surface-muted focus-ring"
          >
            <X class="h-5 w-5 text-ink-muted" />
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
          <div v-if="modalLoading" class="flex items-center gap-2 text-ink-muted">
            <Loader2 class="h-4 w-4 animate-spin" />
            {{ tr("common.loading") }}
          </div>

          <div
            v-if="modalMeta?.summary?.bullets?.length"
            class="rounded-lg border border-subtle bg-surface-muted p-3 space-y-1"
          >
            <div class="text-xs uppercase tracking-wide text-ink-muted">
              {{ tr("console.summary_title") }}
            </div>
            <ul class="list-disc list-inside text-ink-secondary space-y-0.5">
              <li v-for="(b, i) in modalMeta.summary.bullets" :key="i">{{ b }}</li>
            </ul>
          </div>

          <div v-for="t in modalTurns" :key="t.id + ':' + t.role" class="space-y-1">
            <div class="text-xs uppercase tracking-wide text-ink-muted">
              <template v-if="t.role === 'user'">▶ {{ tr("console.you") }}</template>
              <template v-else>▶ {{ tr("console.claude") }}</template>
              <span class="ml-2 normal-case tracking-normal">{{ turnTime(t.ts) }}</span>
              <span
                v-if="t.role === 'assistant' && t.subtype === 'error'"
                class="ml-2 normal-case tracking-normal text-danger"
              >
                · {{ tr("console.failed") }}
              </span>
            </div>
            <div class="whitespace-pre-wrap text-ink-primary">
              {{ t.text || t.error || "" }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
