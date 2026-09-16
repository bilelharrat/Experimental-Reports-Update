<script setup>
import { ref, watch, onMounted } from "vue";
import { useT } from "../../i18n.js";
import {
  ShieldCheck,
  Trash2,
  Loader2,
} from "lucide-vue-next";
import api from "../../api.js";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
  company: {
    type: Object,
    default: () => ({}),
  },
});

const t = useT();

const loading = ref(false);
const submitting = ref(false);
const decisions = ref([]);

const newDecision = ref({
  type: "watch",
  rationale: "",
});

async function loadDecisions() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    const res = await api.decisionRecords.list(props.companyId);
    if (res) {
      decisions.value = Array.isArray(res) ? res : (res.decisions || res.items || []);
    }
  } catch {
    decisions.value = [];
  } finally {
    loading.value = false;
  }
}

watch(() => props.companyId, loadDecisions, { immediate: true });
onMounted(loadDecisions);

async function addDecision() {
  if (!props.companyId || submitting.value || !newDecision.value.rationale.trim()) return;
  submitting.value = true;
  try {
    await api.decisionRecords.add(props.companyId, {
      type: newDecision.value.type,
      rationale: newDecision.value.rationale.trim(),
    });
    newDecision.value.rationale = "";
    await loadDecisions();
  } catch {
    // error handling
  } finally {
    submitting.value = false;
  }
}

async function removeDecision(decisionId) {
  if (!props.companyId || !decisionId) return;
  try {
    await api.decisionRecords.remove(props.companyId, decisionId);
    await loadDecisions();
  } catch {
    // error handling
  }
}

function verdictPillClass(verdict) {
  const v = (verdict || "").toLowerCase();
  if (v === "invest") return "bg-emerald-500/15 text-emerald-400 border-emerald-500/25";
  if (v === "pass") return "bg-rose-500/15 text-rose-400 border-rose-500/25";
  return "bg-amber-500/15 text-amber-400 border-amber-500/25";
}

function verdictLabel(verdict) {
  const v = (verdict || "").toLowerCase();
  if (v === "invest") return t("research_desk.invest");
  if (v === "pass") return t("research_desk.pass");
  return t("research_desk.watch");
}

function formatDate(iso) {
  if (!iso) return "";
  return String(iso).slice(0, 10);
}
</script>

<template>
  <div class="rounded-xl border border-white/[0.08] bg-[#1c1c1f] p-3.5 shadow-xs transition-all text-white">
    <!-- Header: Decision record + Stage -->
    <div class="flex items-center justify-between pb-3 border-b border-white/[0.06]">
      <div class="flex items-center gap-2">
        <ShieldCheck class="h-4 w-4 text-[#0a84ff]" />
        <span class="font-semibold text-white text-xs">
          {{ t("research_desk.decision_record_title") }}
        </span>
        <span v-if="company?.deal_stage" class="text-xs text-neutral-400">
          · {{ company.deal_stage }}
        </span>
      </div>

      <span class="text-xs font-mono text-neutral-400">
        {{ decisions.length }} {{ t("research_desk.decisions_count") }}
      </span>
    </div>

    <!-- Timeline of Decisions (MacDecisionTimeline.swift) -->
    <div class="mt-3 space-y-2">
      <!-- Empty state -->
      <div v-if="decisions.length === 0 && !loading" class="py-3 text-center text-xs text-neutral-400">
        {{ t("research_desk.no_formal_decisions") }}
      </div>

      <!-- Decision items -->
      <div
        v-for="dec in decisions"
        :key="dec.id || dec.created_at"
        class="rounded-lg bg-white/[0.03] border border-white/[0.04] p-2.5 space-y-1.5"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 flex-wrap">
            <span
              class="rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
              :class="verdictPillClass(dec.type || dec.verdict)"
            >
              {{ verdictLabel(dec.type || dec.verdict) }}
            </span>
            <span v-if="dec.author || dec.created_by" class="text-xs text-white font-medium">
              {{ dec.author || dec.created_by }}
            </span>
            <span class="text-[11px] text-neutral-400">
              {{ formatDate(dec.created_at || dec.date) }}
            </span>
          </div>

          <button
            v-if="dec.id"
            type="button"
            class="text-neutral-500 hover:text-rose-400 p-1"
            :title="t('research_desk.delete_decision')"
            @click="removeDecision(dec.id)"
          >
            <Trash2 class="h-3 w-3" />
          </button>
        </div>

        <p v-if="dec.rationale" class="text-xs text-neutral-300 leading-relaxed whitespace-pre-wrap">
          {{ dec.rationale }}
        </p>
      </div>
    </div>

    <!-- Inline Add Drawer with textarea for test compatibility -->
    <div class="mt-3 pt-3 border-t border-white/[0.06] space-y-2">
      <div class="flex items-start gap-2">
        <select
          v-model="newDecision.type"
          class="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-white focus:outline-hidden focus:border-[#0a84ff]"
        >
          <option value="invest" class="bg-[#1c1c1f] text-white">{{ t("research_desk.invest") }}</option>
          <option value="watch" class="bg-[#1c1c1f] text-white">{{ t("research_desk.watch") }}</option>
          <option value="pass" class="bg-[#1c1c1f] text-white">{{ t("research_desk.pass") }}</option>
        </select>

        <textarea
          v-model="newDecision.rationale"
          rows="1"
          :placeholder="t('research_desk.rationale_placeholder')"
          class="flex-1 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-white placeholder-neutral-500 focus:outline-hidden focus:border-[#0a84ff] resize-none"
          @keydown.enter.exact.prevent="addDecision"
        />

        <button
          type="button"
          class="rounded-lg bg-[#0a84ff] hover:bg-[#0071e3] px-3 py-1.5 text-xs font-semibold text-white transition-colors disabled:opacity-50 shrink-0"
          :disabled="submitting || !newDecision.rationale.trim()"
          @click="addDecision"
        >
          <Loader2 v-if="submitting" class="h-3.5 w-3.5 animate-spin" />
          <span v-else>{{ t("research_desk.save_decision") }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
