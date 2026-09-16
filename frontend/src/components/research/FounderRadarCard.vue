<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useT } from "../../i18n.js";
import { Users, RotateCw, GitFork, Star, ExternalLink, Award, Briefcase } from "lucide-vue-next";
import { api } from "../../api.js";
import { confirmTokenSpend } from "../../confirmTokens.js";

const t = useT();

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

const loading = ref(false);
const searching = ref(false);
const founderData = ref(null);

async function loadFounders() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    const res = await api.getFounderDossier(props.companyId);
    founderData.value = res;
  } catch (err) {
    founderData.value = null;
  } finally {
    loading.value = false;
  }
}

async function deepSearch() {
  if (!props.companyId || searching.value) return;
  if (!confirmTokenSpend()) return;
  searching.value = true;
  try {
    const res = await api.deepSearchFounder(props.companyId);
    founderData.value = res;
  } catch (err) {
    // fallback
  } finally {
    searching.value = false;
  }
}

watch(() => props.companyId, loadFounders, { immediate: true });
onMounted(loadFounders);

const foundersList = computed(() => {
  if (founderData.value?.founders?.length) {
    return founderData.value.founders;
  }
  if (props.company?.team_profiles?.length) {
    return props.company.team_profiles;
  }
  if (props.company?.leadership?.length) {
    return props.company.leadership;
  }
  return [];
});

const traction = computed(() => {
  return founderData.value?.developer_traction || props.company?.developer_traction || null;
});
</script>

<template>
  <div class="rounded-xl border border-border/40 bg-card/60 p-5 backdrop-blur-md">
    <!-- Header -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-border/40 pb-3">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Users class="h-4 w-4 text-primary" />
          {{ t("research_desk.founders_team_radar") }}
        </h3>
        <p class="text-xs text-muted-foreground">
          {{ t("research_desk.founders_subtitle") }}
        </p>
      </div>

      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-md border border-border/50 bg-background/50 px-2.5 py-1 text-xs font-medium text-foreground transition hover:bg-muted disabled:opacity-50"
        :disabled="searching || loading"
        @click="deepSearch"
      >
        <RotateCw class="h-3 w-3" :class="{ 'animate-spin': searching || loading }" />
        <span>{{ searching ? "Scanning…" : t("research_desk.refresh") }}</span>
      </button>
    </div>

    <!-- Developer Traction Banner if available -->
    <div
      v-if="traction"
      class="mb-4 flex flex-wrap items-center gap-4 rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs"
    >
      <div class="flex items-center gap-1.5 font-medium text-foreground">
        <GitFork class="h-3.5 w-3.5 text-primary" />
        <span>{{ t("research_desk.open_source_traction") }}:</span>
      </div>
      <div v-if="traction.stars != null" class="flex items-center gap-1 font-mono text-muted-foreground">
        <Star class="h-3 w-3 text-amber-400" />
        <span>{{ traction.stars }} {{ t("research_desk.stars") }}</span>
      </div>
      <div v-if="traction.velocity" class="font-mono text-muted-foreground">
        {{ t("research_desk.velocity") }}: {{ traction.velocity }}
      </div>
      <div v-if="traction.repo" class="ml-auto">
        <a
          :href="traction.repo"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-1 text-primary hover:underline"
        >
          <span>{{ t("research_desk.repository") }}</span>
          <ExternalLink class="h-3 w-3" />
        </a>
      </div>
    </div>

    <!-- Founders List -->
    <div v-if="foundersList.length" class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div
        v-for="(person, idx) in foundersList"
        :key="person.name || idx"
        class="flex flex-col justify-between rounded-lg border border-border/40 bg-background/40 p-3.5 transition hover:border-border/80"
      >
        <div>
          <div class="flex items-start justify-between gap-2">
            <div>
              <h4 class="text-sm font-semibold text-foreground">
                {{ person.name }}
              </h4>
              <p class="text-xs text-muted-foreground">
                {{ person.role || person.title || "Founder" }}
              </p>
            </div>
            <span
              v-if="person.exits?.length || person.prior_exits"
              class="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400"
            >
              <Award class="h-2.5 w-2.5" />
              {{ t("research_desk.prior_exit") }}
            </span>
          </div>

          <p v-if="person.bio || person.background" class="mt-2 text-xs leading-relaxed text-muted-foreground">
            {{ person.bio || person.background }}
          </p>
        </div>

        <div v-if="person.prior_companies?.length || person.education" class="mt-3 border-t border-border/30 pt-2 text-[11px] text-muted-foreground">
          <div v-if="person.prior_companies?.length" class="flex items-center gap-1">
            <Briefcase class="h-3 w-3 shrink-0" />
            <span>Ex-{{ person.prior_companies.join(", ") }}</span>
          </div>
          <div v-else-if="person.education" class="truncate">
            {{ person.education }}
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="py-8 text-center text-xs text-muted-foreground">
      {{ t("research_desk.no_team_profiles") }}
    </div>
  </div>
</template>
