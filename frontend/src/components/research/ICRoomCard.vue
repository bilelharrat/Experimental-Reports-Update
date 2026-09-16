<script setup>
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";

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

const activeTab = ref("votes");
const meetings = ref([]);
const refs = ref([]);
const comparables = ref([]);
const redTeam = ref(null);
const loading = ref(false);

const openMeeting = computed(() => meetings.value.find((m) => m.is_open ?? m.isOpen));

// Form state for casting vote
const voteChoice = ref("invest");
const conviction = ref(3);
const voteNote = ref("");
const castingVote = ref(false);

async function loadICData() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    const [meetingsRes, refsRes, compsRes, redRes] = await Promise.allSettled([
      api.getICMeetings(props.companyId),
      api.getReferenceCalls(props.companyId),
      api.getICComparables(props.companyId),
      api.getRedTeam(props.companyId),
    ]);

    if (meetingsRes.status === "fulfilled") {
      meetings.value = meetingsRes.value?.items ?? meetingsRes.value ?? [];
    }
    if (refsRes.status === "fulfilled") {
      refs.value = refsRes.value?.items ?? refsRes.value ?? [];
    }
    if (compsRes.status === "fulfilled") {
      comparables.value = compsRes.value?.items ?? compsRes.value ?? [];
    }
    if (redRes.status === "fulfilled") {
      redTeam.value = redRes.value;
    }
  } finally {
    loading.value = false;
  }
}

async function castVote() {
  if (!openMeeting.value?.id) return;
  castingVote.value = true;
  try {
    await api.castICVote(props.companyId, openMeeting.value.id, {
      vote: voteChoice.value,
      conviction: conviction.value,
      note: voteNote.value.trim(),
    });
    voteNote.value = "";
    await loadICData();
  } catch (err) {
    console.error("Failed to cast vote", err);
  } finally {
    castingVote.value = false;
  }
}

watch(
  () => props.companyId,
  () => {
    loadICData();
  },
  { immediate: true },
);
</script>

<template>
  <div class="rounded-2xl border border-border/40 bg-surface/90 dark:bg-[#1c1c1e]/90 p-5 shadow-sm backdrop-blur-md">
    <!-- Header -->
    <div class="flex items-center justify-between pb-3 border-b border-border/30">
      <div class="flex items-center gap-2.5">
        <svg class="h-5 w-5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
        <h3 class="font-semibold text-foreground text-sm tracking-tight">
          {{ t("research_desk.ic_room_title") }}
        </h3>
      </div>

      <button
        type="button"
        class="rounded-lg p-1.5 text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-colors"
        :title="t('research_desk.refresh')"
        :disabled="loading"
        @click="loadICData"
      >
        <svg
          class="h-4 w-4"
          :class="{ 'animate-spin': loading }"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
          <path d="M21 3v5h-5" />
          <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
          <path d="M3 21v-5h5" />
        </svg>
      </button>
    </div>

    <!-- Sub-tabs -->
    <div class="flex items-center gap-1 border-b border-border/30 pt-3 pb-2 text-xs">
      <button
        type="button"
        class="rounded-lg px-3 py-1 font-medium transition-colors"
        :class="activeTab === 'votes' ? 'bg-primary/10 text-primary font-semibold' : 'text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'votes'"
      >
        {{ t("research_desk.votes_tab") }}
      </button>
      <button
        type="button"
        class="rounded-lg px-3 py-1 font-medium transition-colors"
        :class="activeTab === 'red' ? 'bg-primary/10 text-primary font-semibold' : 'text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'red'"
      >
        {{ t("research_desk.red_team_tab") }}
      </button>
      <button
        type="button"
        class="rounded-lg px-3 py-1 font-medium transition-colors"
        :class="activeTab === 'comps' ? 'bg-primary/10 text-primary font-semibold' : 'text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'comps'"
      >
        {{ t("research_desk.comps_tab") }}
      </button>
      <button
        type="button"
        class="rounded-lg px-3 py-1 font-medium transition-colors"
        :class="activeTab === 'refs' ? 'bg-primary/10 text-primary font-semibold' : 'text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'refs'"
      >
        {{ t("research_desk.refs_tab") }}
      </button>
    </div>

    <!-- Tab 1: Votes -->
    <div v-if="activeTab === 'votes'" class="pt-4 space-y-4 text-xs">
      <div v-if="openMeeting" class="space-y-3">
        <div class="flex items-center justify-between">
          <span class="font-semibold text-foreground">{{ openMeeting.title }}</span>
          <span class="text-[11px] font-mono text-emerald-500">{{ t("research_desk.open_status") }}</span>
        </div>

        <!-- Tally pills -->
        <div v-if="openMeeting.tally" class="flex items-center gap-3">
          <span class="rounded px-2 py-0.5 font-mono text-[11px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            {{ openMeeting.tally.invest || 0 }} {{ t("research_desk.invest") }}
          </span>
          <span class="rounded px-2 py-0.5 font-mono text-[11px] bg-rose-500/10 text-rose-600 dark:text-rose-400">
            {{ openMeeting.tally.pass || 0 }} {{ t("research_desk.pass") }}
          </span>
          <span class="rounded px-2 py-0.5 font-mono text-[11px] bg-amber-500/10 text-amber-600 dark:text-amber-400">
            {{ openMeeting.tally.more_work || openMeeting.tally.watch || 0 }} {{ t("research_desk.watch") }}
          </span>
        </div>

        <!-- Individual votes -->
        <div v-if="openMeeting.votes?.length" class="space-y-1.5 pt-2">
          <div
            v-for="v in openMeeting.votes"
            :key="v.id || v.member"
            class="flex items-center justify-between rounded-lg bg-muted/20 p-2 text-xs"
          >
            <div class="flex items-center gap-2">
              <span class="font-medium text-foreground">{{ v.display_name || v.displayName || v.member }}</span>
              <span
                class="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase"
                :class="
                  v.vote === 'invest'
                    ? 'bg-emerald-500/10 text-emerald-600'
                    : v.vote === 'pass'
                    ? 'bg-rose-500/10 text-rose-600'
                    : 'bg-amber-500/10 text-amber-600'
                "
              >
                {{ v.vote }}
              </span>
              <span v-if="v.conviction" class="text-amber-500 font-mono text-[11px]">
                ★ {{ v.conviction }}
              </span>
            </div>
            <span v-if="v.note" class="text-muted-foreground text-[11px] truncate max-w-[200px]">
              {{ v.note }}
            </span>
          </div>
        </div>

        <!-- Cast vote form -->
        <div class="rounded-xl border border-border/30 bg-muted/10 p-3 space-y-3">
          <div class="flex items-center gap-3">
            <label class="font-medium text-muted-foreground text-[11px]">
              {{ t("research_desk.cast_vote") }}
            </label>
            <select
              v-model="voteChoice"
              class="rounded border border-border/40 bg-surface px-2 py-1 text-xs text-foreground"
            >
              <option value="invest">{{ t("research_desk.invest") }}</option>
              <option value="watch">{{ t("research_desk.watch") }}</option>
              <option value="pass">{{ t("research_desk.pass") }}</option>
            </select>

            <span class="font-medium text-muted-foreground text-[11px]">
              {{ t("research_desk.conviction") }}
            </span>
            <input
              v-model.number="conviction"
              type="range"
              min="1"
              max="5"
              class="w-20"
            />
            <span class="font-mono text-xs">{{ conviction }}</span>
          </div>

          <div class="flex items-center gap-2">
            <input
              v-model="voteNote"
              type="text"
              :placeholder="t('research_desk.vote_notes_ph')"
              class="flex-1 rounded-lg border border-border/40 bg-surface px-2.5 py-1 text-xs text-foreground"
            />
            <button
              type="button"
              class="btn-filled rounded-lg px-3 py-1 text-xs text-white"
              :disabled="castingVote"
              @click="castVote"
            >
              {{ t("research_desk.cast_vote") }}
            </button>
          </div>
        </div>
      </div>

      <div v-else class="py-4 text-center text-muted-foreground text-xs">
        {{ t("research_desk.no_decisions") }}
      </div>
    </div>

    <!-- Tab 2: Red Team -->
    <div v-else-if="activeTab === 'red'" class="pt-4 space-y-3 text-xs">
      <div v-if="redTeam?.critiques?.length" class="space-y-2">
        <div
          v-for="(c, idx) in redTeam.critiques"
          :key="idx"
          class="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 space-y-1"
        >
          <span class="font-semibold text-rose-600 dark:text-rose-400 text-xs">{{ c.thesis || c.title }}</span>
          <p class="text-muted-foreground text-[11px]">{{ c.counter_argument || c.body }}</p>
        </div>
      </div>
      <div v-else class="py-4 text-center text-muted-foreground text-xs">
        {{ t("research_desk.no_red_team") }}
      </div>
    </div>

    <!-- Tab 3: Comparables -->
    <div v-else-if="activeTab === 'comps'" class="pt-4 space-y-3 text-xs">
      <div v-if="comparables.length" class="space-y-2">
        <div
          v-for="(comp, idx) in comparables"
          :key="idx"
          class="flex items-center justify-between rounded-lg border border-border/30 bg-muted/10 p-2.5"
        >
          <div>
            <p class="font-semibold text-foreground text-xs">{{ comp.name }}</p>
            <p class="text-[11px] text-muted-foreground">{{ comp.sector }} · {{ comp.outcome }}</p>
          </div>
          <span class="font-mono text-xs font-semibold text-foreground">{{ comp.multiple || comp.valuation }}</span>
        </div>
      </div>
      <div v-else class="py-4 text-center text-muted-foreground text-xs">
        {{ t("research_desk.no_comps") }}
      </div>
    </div>

    <!-- Tab 4: References -->
    <div v-else-if="activeTab === 'refs'" class="pt-4 space-y-3 text-xs">
      <div v-if="refs.length" class="space-y-2">
        <div
          v-for="(refItem, idx) in refs"
          :key="idx"
          class="rounded-xl border border-border/30 bg-muted/10 p-3 space-y-1"
        >
          <div class="flex items-center justify-between">
            <span class="font-semibold text-foreground">{{ refItem.referee || refItem.name }}</span>
            <span class="font-mono text-amber-500">★ {{ refItem.rating || 5 }}/5</span>
          </div>
          <p class="text-muted-foreground text-[11px]">{{ refItem.relationship }}</p>
          <p v-if="refItem.notes" class="text-foreground text-[11px] pt-1 italic">
            "{{ refItem.notes }}"
          </p>
        </div>
      </div>
      <div v-else class="py-4 text-center text-muted-foreground text-xs">
        {{ t("research_desk.no_ref_calls") }}
      </div>
    </div>
  </div>
</template>
