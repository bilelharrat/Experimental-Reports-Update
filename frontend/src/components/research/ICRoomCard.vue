<script setup>
// Web twin of MacICRoomView.swift: live votes with the tally bar and vote
// form, the red-team argument, comparable past decisions, and reference
// calls with the log-call sheet. Section switching uses the glass segments.
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import api from "../../api.js";
import { t } from "../../i18n.js";
import { sessionName } from "../../auth.js";
import {
  Users,
  Plus,
  Minus,
  Flag,
  PlusCircle,
  MinusCircle,
  Trash2,
  Phone,
  BadgeCheck,
} from "lucide-vue-next";
import { formatRelativeTime } from "../../formatters.js";

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

const router = useRouter();

const activeTab = ref("votes");
const meetings = ref([]);
const refs = ref(null);
const comparables = ref(null);
const redTeam = ref(null);
const loading = ref(false);

// Vote form (ICRoomForm)
const voteChoice = ref("invest");
const conviction = ref(3);
const voteNote = ref("");
const castingVote = ref(false);

// Close-meeting sheet
const showCloseSheet = ref(false);
const closeRecord = ref(true);
const closeExplanation = ref("");
const closing = ref(false);

// Log-call sheet (MacReferenceCallSheet)
const showAddRef = ref(false);
const refForm = ref(null);
const savingRef = ref(false);

const RELATIONS = [
  ["customer", "Customer"],
  ["former_employee", "Former employee"],
  ["investor", "Investor"],
  ["partner", "Partner"],
  ["founder_peer", "Founder peer"],
  ["other", "Other"],
];

const openMeeting = computed(() => meetings.value.find((m) => !m.closed_at));
const memberName = computed(() => sessionName.value || t("research_desk.recorded_you"));

function voteLabel(vote) {
  if (vote === "invest") return t("research_desk.invest");
  if (vote === "pass") return t("research_desk.pass");
  return t("research_desk.icroom_more_work");
}

function voteTint(vote) {
  if (vote === "invest") return "var(--mac-green)";
  if (vote === "pass") return "var(--mac-red)";
  return "var(--mac-orange)";
}

function relationLabel(relation) {
  const found = RELATIONS.find(([id]) => id === relation);
  return found ? found[1] : String(relation || "").replaceAll("_", " ");
}

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
    if (refsRes.status === "fulfilled") refs.value = refsRes.value;
    if (compsRes.status === "fulfilled") comparables.value = compsRes.value;
    if (redRes.status === "fulfilled") redTeam.value = redRes.value;
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.companyId,
  () => {
    activeTab.value = "votes";
    voteChoice.value = "invest";
    conviction.value = 3;
    voteNote.value = "";
    showCloseSheet.value = false;
    showAddRef.value = false;
    loadICData();
  },
  { immediate: true },
);

async function openNewMeeting() {
  try {
    await api.openICMeeting(props.companyId, { title: "" });
    await loadICData();
  } catch {
    // reload shows the truth
  }
}

async function castVote() {
  if (!openMeeting.value?.id || castingVote.value) return;
  castingVote.value = true;
  try {
    await api.castICVote(props.companyId, openMeeting.value.id, {
      vote: voteChoice.value,
      conviction: conviction.value,
      note: voteNote.value.trim(),
    });
    voteNote.value = "";
    await loadICData();
  } catch {
    // reload shows the truth
  } finally {
    castingVote.value = false;
  }
}

function openCloseSheet() {
  closeRecord.value = Boolean(openMeeting.value?.tally?.majority);
  closeExplanation.value = "";
  showCloseSheet.value = true;
}

async function closeMeeting() {
  if (!openMeeting.value?.id || closing.value) return;
  closing.value = true;
  try {
    await api.closeICMeeting(props.companyId, openMeeting.value.id, {
      record_decision: closeRecord.value && Boolean(openMeeting.value?.tally?.majority),
      explanation: closeExplanation.value.trim(),
    });
    showCloseSheet.value = false;
    await loadICData();
  } catch {
    // reload shows the truth
  } finally {
    closing.value = false;
  }
}

async function runRedTeam() {
  try {
    await api.startRedTeam(props.companyId);
    redTeam.value = { ...(redTeam.value || {}), status: "running" };
  } catch {
    // reload shows the truth
  }
}

function openLogCall() {
  refForm.value = {
    contact: "",
    role: "",
    relation: "customer",
    call_date: new Date().toISOString().slice(0, 10),
    rating: 0,
    strengths: "",
    concerns: "",
    quotes: "",
    notes: "",
  };
  showAddRef.value = true;
}

async function saveRefCall() {
  if (!refForm.value?.contact.trim() || savingRef.value) return;
  savingRef.value = true;
  try {
    await api.addReferenceCall(props.companyId, {
      ...refForm.value,
      rating: refForm.value.rating || null,
    });
    showAddRef.value = false;
    await loadICData();
  } catch {
    // keep the sheet open so nothing typed is lost
  } finally {
    savingRef.value = false;
  }
}

async function deleteRefCall(itemId) {
  try {
    await api.deleteReferenceCall(props.companyId, itemId);
    await loadICData();
  } catch {
    // reload shows the truth
  }
}

function showComparable(companyId) {
  router.push({ name: "research-desk-company", params: { companyId } });
}
</script>

<template>
  <div class="mac-card flex flex-col gap-2.5 p-2.5">
    <!-- Label("IC room", person.3.sequence) -->
    <div class="flex items-center">
      <span class="mac-t-headline flex items-center gap-2">
        <Users class="mac-c-accent h-4 w-4" stroke-width="2.2" />
        {{ t("research_desk.ic_room_title") }}
      </span>
      <span class="flex-1" />
      <span v-if="loading" class="mac-spinner" />
    </div>

    <!-- Section glass segments -->
    <div class="mac-segmented w-full">
      <button
        v-for="[tab, label] in [
          ['votes', t('research_desk.votes_tab')],
          ['red', t('research_desk.red_team_tab')],
          ['comps', t('research_desk.comps_tab')],
          ['refs', t('research_desk.refs_tab')],
        ]"
        :key="tab"
        type="button"
        class="mac-segment"
        :class="{ 'is-selected': activeTab === tab }"
        @click="activeTab = tab"
      >
        {{ label }}
      </button>
    </div>

    <!-- Votes -->
    <div v-if="activeTab === 'votes'" class="flex flex-col gap-2">
      <template v-if="openMeeting">
        <div class="flex items-center gap-2">
          <span class="mac-t-caption10 font-semibold">{{ openMeeting.title }}</span>
          <span class="mac-t-caption10 mac-c-secondary">
            {{ t("research_desk.icroom_open_since", { when: formatRelativeTime(openMeeting.created_at) }) }}
          </span>
          <span class="flex-1" />
          <button type="button" class="mac-btn mac-btn--sm" @click="openCloseSheet">
            {{ t("research_desk.icroom_close_meeting") }}
          </button>
        </div>

        <template v-if="openMeeting.tally">
          <div class="flex flex-wrap items-center gap-2">
            <span
              v-for="[key, label, tint] in [
                ['invest', t('research_desk.invest'), 'var(--mac-green)'],
                ['pass', t('research_desk.pass'), 'var(--mac-red)'],
                ['more_work', t('research_desk.icroom_more_work'), 'var(--mac-orange)'],
              ]"
              :key="key"
              class="mac-t-caption10 mac-mono rounded-full px-[7px] py-[2px] font-semibold"
              :style="{ color: tint, background: `color-mix(in srgb, ${tint} 12%, transparent)` }"
            >
              {{ openMeeting.tally[key] || 0 }} {{ label }}
            </span>
            <span class="flex-1" />
            <span v-if="openMeeting.tally.average_conviction != null" class="mac-t-caption10 mac-c-secondary">
              {{ t("research_desk.icroom_conviction_avg", { avg: openMeeting.tally.average_conviction.toFixed(1) }) }}
            </span>
            <span
              v-if="openMeeting.tally.tied"
              class="mac-t-caption10 font-semibold"
              :style="{ color: 'var(--mac-orange)' }"
            >
              {{ t("research_desk.icroom_tied") }}
            </span>
          </div>

          <div
            v-if="openMeeting.tally.total > 0"
            class="flex h-1.5 w-full gap-px overflow-hidden rounded-full"
          >
            <span :style="{ background: 'var(--mac-green)', width: `${(100 * (openMeeting.tally.invest || 0)) / openMeeting.tally.total}%` }" />
            <span :style="{ background: 'var(--mac-orange)', width: `${(100 * (openMeeting.tally.more_work || 0)) / openMeeting.tally.total}%` }" />
            <span :style="{ background: 'var(--mac-red)', width: `${(100 * (openMeeting.tally.pass || 0)) / openMeeting.tally.total}%` }" />
          </div>
        </template>

        <div
          v-for="v in openMeeting.votes || []"
          :key="v.member"
          class="flex items-center gap-1.5"
        >
          <span class="mac-t-caption10 font-medium">{{ v.member_name || v.member }}</span>
          <span class="mac-status-pill" :style="{ '--tint': voteTint(v.vote) }">{{ voteLabel(v.vote) }}</span>
          <span v-if="v.conviction" class="mac-t-caption10 mac-c-secondary">★{{ v.conviction }}</span>
          <span v-if="v.note" class="mac-t-caption10 mac-c-secondary truncate">{{ v.note }}</span>
        </div>

        <div class="mac-divider" />

        <!-- Vote form -->
        <div class="flex flex-wrap items-center gap-2">
          <div class="mac-segmented w-[210px]">
            <button
              v-for="[vote, label] in [
                ['invest', t('research_desk.invest')],
                ['more_work', t('research_desk.icroom_more_work')],
                ['pass', t('research_desk.pass')],
              ]"
              :key="vote"
              type="button"
              class="mac-segment"
              :class="{ 'is-selected': voteChoice === vote }"
              @click="voteChoice = vote"
            >
              {{ label }}
            </button>
          </div>

          <!-- Stepper ★n -->
          <span class="flex items-center gap-1">
            <span class="mac-t-caption10 mac-mono w-6">★{{ conviction }}</span>
            <span class="flex overflow-hidden rounded-md" style="box-shadow: var(--mac-btn-edge)">
              <button
                type="button"
                class="flex h-[18px] w-[18px] items-center justify-center border-none"
                style="background: var(--mac-btn-bg)"
                :disabled="conviction <= 1"
                @click="conviction = Math.max(1, conviction - 1)"
              >
                <Minus class="h-2.5 w-2.5" />
              </button>
              <span class="w-px" style="background: var(--mac-hairline)" />
              <button
                type="button"
                class="flex h-[18px] w-[18px] items-center justify-center border-none"
                style="background: var(--mac-btn-bg)"
                :disabled="conviction >= 5"
                @click="conviction = Math.min(5, conviction + 1)"
              >
                <Plus class="h-2.5 w-2.5" />
              </button>
            </span>
          </span>

          <input
            v-model="voteNote"
            type="text"
            class="mac-field min-w-0 flex-1"
            style="font-size: 11px; padding: 3px 7px"
            :placeholder="t('research_desk.icroom_note_ph')"
          />

          <button
            type="button"
            class="mac-btn mac-btn--sm mac-btn--prominent"
            :disabled="castingVote"
            @click="castVote"
          >
            {{ t("research_desk.icroom_vote_as", { name: memberName }) }}
          </button>
        </div>
      </template>

      <template v-else>
        <div class="flex items-center gap-2">
          <span class="mac-t-caption10 mac-c-secondary">
            {{
              meetings.length === 0
                ? t("research_desk.icroom_no_meeting")
                : t("research_desk.icroom_no_open_meeting", { count: meetings.length })
            }}
          </span>
          <span class="flex-1" />
          <button type="button" class="mac-btn mac-btn--sm" @click="openNewMeeting">
            <Plus class="h-3 w-3" />
            <span>{{ t("research_desk.icroom_open_meeting") }}</span>
          </button>
        </div>
        <div v-for="m in meetings.slice(0, 3)" :key="m.id" class="flex items-center gap-1.5">
          <span class="mac-t-caption10">{{ m.title }}</span>
          <span v-if="m.tally" class="mac-t-caption10 mac-mono mac-c-secondary" :title="t('research_desk.icroom_tally_help')">
            {{ m.tally.invest }}/{{ m.tally.pass }}/{{ m.tally.more_work }}
          </span>
          <span
            v-if="m.decision_id"
            class="mac-t-caption10 flex items-center gap-1"
            :style="{ color: 'var(--mac-green)' }"
          >
            <BadgeCheck class="h-3 w-3" />
            {{ t("research_desk.icroom_decision_recorded") }}
          </span>
          <span class="flex-1" />
          <span class="mac-t-caption10 mac-c-secondary">{{ formatRelativeTime(m.closed_at || m.created_at) }}</span>
        </div>
      </template>
    </div>

    <!-- Red team -->
    <div v-else-if="activeTab === 'red'" class="flex flex-col gap-2">
      <div class="flex items-center gap-2">
        <span class="mac-t-caption10 mac-c-secondary min-w-0 flex-1">
          {{
            redTeam?.result && redTeam?.generated_at
              ? t("research_desk.icroom_red_argued", {
                  when: formatRelativeTime(redTeam.generated_at),
                  blocks: redTeam.memo_blocks_used ?? redTeam.provenance?.memo_blocks_used ?? 0,
                  concerns: redTeam.reference_concerns ?? redTeam.provenance?.reference_concerns ?? 0,
                })
              : t("research_desk.icroom_red_hint")
          }}
        </span>
        <button
          type="button"
          class="mac-btn mac-btn--sm shrink-0"
          :disabled="redTeam?.status === 'running'"
          @click="runRedTeam"
        >
          <span v-if="redTeam?.status === 'running'" class="mac-spinner" style="width: 11px; height: 11px" />
          <Flag v-else class="h-3 w-3" />
          <span>
            {{
              redTeam?.status === "running"
                ? t("research_desk.icroom_red_arguing")
                : redTeam?.result
                  ? t("research_desk.icprep_rerun")
                  : t("research_desk.icroom_red_run")
            }}
          </span>
        </button>
      </div>

      <span v-if="redTeam?.error && !redTeam?.result" class="mac-t-caption10" :style="{ color: 'var(--mac-red)' }">
        {{ redTeam.error }}
      </span>

      <template v-if="redTeam?.result">
        <p class="mac-t-callout select-text">{{ redTeam.result.counter_thesis }}</p>

        <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.icroom_kill_risks") }}</span>
        <div
          v-for="(k, idx) in redTeam.result.kill_risks || []"
          :key="idx"
          class="flex flex-col gap-0.5 rounded-md p-1.5"
          style="background: color-mix(in srgb, var(--mac-secondary) 5%, transparent)"
        >
          <span class="flex items-center gap-1.5">
            <span
              class="h-[7px] w-[7px] shrink-0 rounded-full"
              :style="{
                background:
                  k.severity === 'high'
                    ? 'var(--mac-red)'
                    : k.severity === 'medium'
                      ? 'var(--mac-orange)'
                      : 'var(--mac-secondary)',
              }"
            />
            <span class="mac-t-caption10 font-semibold">{{ k.risk }}</span>
            <span v-if="k.memo_section" class="mac-t-caption10 mac-c-secondary">§ {{ k.memo_section }}</span>
          </span>
          <span class="mac-t-caption10 mac-c-secondary">{{ k.why }}</span>
          <span class="mac-t-caption10 mac-c-tertiary">{{ t("research_desk.icroom_needs", { evidence: k.evidence_needed }) }}</span>
        </div>

        <template v-for="[title, items] in [
          [t('research_desk.icroom_questionable'), redTeam.result.questionable_assumptions],
          [t('research_desk.icroom_change_mind'), redTeam.result.what_would_change_my_mind],
        ]" :key="title">
          <template v-if="items?.length">
            <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ title }}</span>
            <span v-for="(item, idx) in items" :key="idx" class="mac-t-caption10 flex select-text gap-1.5">
              <span>•</span>
              <span>{{ item }}</span>
            </span>
          </template>
        </template>

        <template v-if="redTeam.result.pre_mortem">
          <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.icroom_pre_mortem") }}</span>
          <p class="mac-t-caption10 select-text">{{ redTeam.result.pre_mortem }}</p>
        </template>

        <template v-if="redTeam.result.questions_for_founders?.length">
          <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.icroom_founder_questions") }}</span>
          <span v-for="(item, idx) in redTeam.result.questions_for_founders" :key="idx" class="mac-t-caption10 flex select-text gap-1.5">
            <span>•</span>
            <span>{{ item }}</span>
          </span>
        </template>
      </template>
    </div>

    <!-- Comparables -->
    <div v-else-if="activeTab === 'comps'" class="flex flex-col gap-2">
      <template v-if="comparables?.items?.length">
        <div
          v-for="c in comparables.items"
          :key="c.company_id"
          class="flex flex-col gap-[3px] rounded-md p-1.5"
          style="background: color-mix(in srgb, var(--mac-secondary) 5%, transparent)"
        >
          <span class="flex items-center gap-1.5">
            <button
              type="button"
              class="mac-t-caption10 border-none bg-transparent p-0 font-semibold"
              @click="showComparable(c.company_id)"
            >
              {{ c.company_name }}
            </button>
            <span
              v-if="c.decision?.verdict"
              class="mac-status-pill"
              :style="{ '--tint': voteTint(c.decision.verdict === 'watch' ? 'more_work' : c.decision.verdict) }"
            >
              {{ c.decision.verdict.replace(/^./, (ch) => ch.toUpperCase()) }}
            </span>
            <span
              v-if="c.retrospective?.verdict && c.retrospective.verdict !== 'still_right'"
              class="mac-t-caption10"
              :style="{ color: 'var(--mac-orange)' }"
            >
              {{ c.retrospective.verdict.replaceAll("_", " ") }}
            </span>
            <span class="flex-1" />
            <span class="mac-t-caption10 mac-mono mac-c-secondary">
              {{ t("research_desk.icroom_overlap", { score: c.score }) }}
            </span>
          </span>
          <span v-if="c.decision?.explanation" class="mac-t-caption10 mac-c-secondary line-clamp-2">
            {{ c.decision.explanation }}
          </span>
          <span v-if="c.why?.length" class="mac-t-caption10 mac-c-tertiary line-clamp-2">
            {{ c.why.join(" · ") }}
          </span>
        </div>
      </template>
      <span v-else class="mac-t-caption10 mac-c-secondary">
        {{ t("research_desk.icroom_no_comparables") }}
      </span>
      <span v-if="comparables?.basis" class="mac-t-caption10 mac-c-tertiary">{{ comparables.basis }}</span>
    </div>

    <!-- References -->
    <div v-else-if="activeTab === 'refs'" class="flex flex-col gap-2">
      <div class="flex items-center gap-2">
        <span v-if="refs" class="mac-t-caption10 mac-c-secondary">
          {{ t("research_desk.icroom_refs_summary", {
            count: refs.count ?? refs.items?.length ?? 0,
            avg: refs.average_rating != null ? ` · avg ${refs.average_rating.toFixed(1)} / 5` : "",
            concerns: refs.concern_count ?? 0,
          }) }}
        </span>
        <span class="flex-1" />
        <button type="button" class="mac-btn mac-btn--sm" @click="openLogCall">
          <Phone class="h-3 w-3" />
          <span>{{ t("research_desk.icroom_log_call") }}</span>
        </button>
      </div>

      <div
        v-for="r in refs?.items || []"
        :key="r.id"
        class="flex flex-col gap-[3px] rounded-md p-1.5"
        style="background: color-mix(in srgb, var(--mac-secondary) 5%, transparent)"
      >
        <span class="flex items-center gap-1.5">
          <span class="mac-t-caption10 font-semibold">{{ r.contact }}</span>
          <span class="mac-t-caption10 mac-c-secondary">{{ relationLabel(r.relation) }}</span>
          <span v-if="r.role" class="mac-t-caption10 mac-c-secondary">· {{ r.role }}</span>
          <span v-if="r.rating" class="mac-t-caption10" :style="{ color: 'var(--mac-yellow)' }">
            {{ "★".repeat(r.rating) }}
          </span>
          <span class="flex-1" />
          <span class="mac-t-caption10 mac-c-secondary">{{ r.call_date || "" }}</span>
          <button
            type="button"
            class="mac-c-secondary border-none bg-transparent p-0.5"
            @click="deleteRefCall(r.id)"
          >
            <Trash2 class="h-3 w-3" />
          </button>
        </span>
        <span v-for="(s, idx) in r.strengths || []" :key="`s-${idx}`" class="mac-t-caption10 flex items-center gap-1" :style="{ color: 'var(--mac-green)' }">
          <PlusCircle class="h-3 w-3 shrink-0" />{{ s }}
        </span>
        <span v-for="(s, idx) in r.concerns || []" :key="`c-${idx}`" class="mac-t-caption10 flex items-center gap-1" :style="{ color: 'var(--mac-red)' }">
          <MinusCircle class="h-3 w-3 shrink-0" />{{ s }}
        </span>
        <span v-for="(q, idx) in r.quotes || []" :key="`q-${idx}`" class="mac-t-caption10 mac-c-secondary italic">
          “{{ q }}”
        </span>
      </div>
    </div>

    <!-- Close-meeting sheet (MacCloseMeetingSheet) -->
    <div
      v-if="showCloseSheet && openMeeting"
      class="mac-desk fixed inset-0 z-50 flex items-center justify-center p-4"
      style="background: transparent"
      role="dialog"
      aria-modal="true"
    >
      <div class="fixed inset-0" style="background: rgba(0, 0, 0, 0.28)" @click="showCloseSheet = false" />
      <div
        class="relative flex w-full max-w-[460px] flex-col gap-3 rounded-[12px] p-5"
        style="background: var(--mac-canvas); box-shadow: 0 0 0 1px var(--mac-hairline), 0 24px 60px rgba(0, 0, 0, 0.35)"
      >
        <span class="mac-t-headline-sys">{{ t("research_desk.icroom_close_title", { title: openMeeting.title }) }}</span>
        <span v-if="openMeeting.tally" class="mac-t-caption10 mac-c-secondary">
          {{ t("research_desk.icroom_tally_line", {
            invest: openMeeting.tally.invest,
            pass: openMeeting.tally.pass,
            more: openMeeting.tally.more_work,
          }) }}
          <template v-if="openMeeting.tally.majority">
            {{ t("research_desk.icroom_majority", { verdict: openMeeting.tally.majority.replaceAll("_", " ") }) }}
          </template>
          <template v-else-if="openMeeting.tally.leading">
            {{ t("research_desk.icroom_leading", { verdict: openMeeting.tally.leading.replaceAll("_", " ") }) }}
          </template>
          <template v-else>{{ t("research_desk.icroom_tied_arrow") }}</template>
        </span>
        <label class="flex items-center gap-2">
          <input v-model="closeRecord" type="checkbox" :disabled="!openMeeting.tally?.majority" />
          <span class="mac-t-caption10">{{ t("research_desk.icroom_record_majority") }}</span>
        </label>
        <textarea
          v-model="closeExplanation"
          rows="3"
          class="mac-field w-full resize-y"
          style="line-height: 1.4"
          :placeholder="t('research_desk.icroom_close_ph')"
        />
        <div class="flex items-center gap-2">
          <span class="flex-1" />
          <button type="button" class="mac-btn" @click="showCloseSheet = false">
            {{ t("research_desk.cancel") }}
          </button>
          <button type="button" class="mac-btn mac-btn--prominent" :disabled="closing" @click="closeMeeting">
            {{ t("research_desk.icroom_close_meeting_btn") }}
          </button>
        </div>
      </div>
    </div>

    <!-- Log-call sheet (MacReferenceCallSheet) -->
    <div
      v-if="showAddRef && refForm"
      class="mac-desk fixed inset-0 z-50 flex items-center justify-center p-4"
      style="background: transparent"
      role="dialog"
      aria-modal="true"
    >
      <div class="fixed inset-0" style="background: rgba(0, 0, 0, 0.28)" @click="showAddRef = false" />
      <div
        class="relative flex max-h-[80vh] w-full max-w-[480px] flex-col overflow-hidden rounded-[12px]"
        style="background: var(--mac-canvas); box-shadow: 0 0 0 1px var(--mac-hairline), 0 24px 60px rgba(0, 0, 0, 0.35)"
      >
        <div class="flex items-center p-4">
          <span class="mac-t-headline-sys">{{ t("research_desk.icroom_log_call_title") }}</span>
          <span class="flex-1" />
          <button type="button" class="mac-btn" @click="showAddRef = false">
            {{ t("research_desk.cancel") }}
          </button>
        </div>
        <div class="mac-divider" />

        <div class="mac-scroll flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-4">
          <div class="mac-tile flex flex-col" style="border-radius: 10px">
            <div class="flex items-center gap-4 px-2.5 py-2">
              <span class="mac-t-body w-32 shrink-0">{{ t("research_desk.icroom_contact") }}</span>
              <input v-model="refForm.contact" type="text" class="mac-field min-w-0 flex-1" />
            </div>
            <div class="mac-divider mx-2.5" />
            <div class="flex items-center gap-4 px-2.5 py-2">
              <span class="mac-t-body w-32 shrink-0">{{ t("research_desk.icroom_role") }}</span>
              <input v-model="refForm.role" type="text" class="mac-field min-w-0 flex-1" />
            </div>
            <div class="mac-divider mx-2.5" />
            <div class="flex items-center gap-4 px-2.5 py-2">
              <span class="mac-t-body w-32 shrink-0">{{ t("research_desk.icroom_relation") }}</span>
              <span class="flex-1" />
              <div class="mac-popup">
                <select v-model="refForm.relation">
                  <option v-for="[id, label] in RELATIONS" :key="id" :value="id">{{ label }}</option>
                </select>
              </div>
            </div>
            <div class="mac-divider mx-2.5" />
            <div class="flex items-center gap-4 px-2.5 py-2">
              <span class="mac-t-body w-32 shrink-0">{{ t("research_desk.icroom_call_date") }}</span>
              <span class="flex-1" />
              <input v-model="refForm.call_date" type="date" class="mac-field mac-mono" style="font-size: 12px" />
            </div>
            <div class="mac-divider mx-2.5" />
            <div class="flex items-center gap-4 px-2.5 py-2">
              <span class="mac-t-body w-32 shrink-0">{{ t("research_desk.icroom_rating") }}</span>
              <span class="flex-1" />
              <div class="mac-popup">
                <select v-model.number="refForm.rating">
                  <option :value="0">—</option>
                  <option v-for="n in 5" :key="n" :value="n">{{ "★".repeat(n) }}</option>
                </select>
              </div>
            </div>
          </div>

          <div class="mac-tile flex flex-col" style="border-radius: 10px">
            <div
              v-for="[key, label] in [
                ['strengths', t('research_desk.icroom_strengths')],
                ['concerns', t('research_desk.icroom_concerns')],
                ['quotes', t('research_desk.icroom_quotes')],
                ['notes', t('research_desk.icroom_notes')],
              ]"
              :key="key"
              class="flex flex-col gap-1 px-2.5 py-2"
              :class="key !== 'strengths' ? 'mac-hairline-t' : ''"
            >
              <span class="mac-t-caption10 mac-c-secondary">{{ label }}</span>
              <textarea v-model="refForm[key]" rows="2" class="mac-field w-full resize-y" style="line-height: 1.4" />
            </div>
          </div>
        </div>

        <div class="mac-divider" />
        <div class="flex items-center p-3">
          <span class="flex-1" />
          <button
            type="button"
            class="mac-btn mac-btn--prominent"
            :disabled="savingRef || !refForm.contact.trim()"
            @click="saveRefCall"
          >
            <span v-if="savingRef" class="mac-spinner" style="width: 12px; height: 12px" />
            <span v-else>{{ t("research_desk.icprep_save") }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
