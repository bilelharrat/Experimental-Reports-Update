<script setup>
import { ref } from "vue";
import { MessageSquare, Pencil, PlusCircle, Save, X } from "lucide-vue-next";
import { api } from "../../api.js";
import { TARGET_KINDS } from "../../copilotTargets.js";
import { useT } from "../../i18n.js";
import CopilotDropZone from "../CopilotDropZone.vue";

defineOptions({ name: "MemoStudioBulletTree" });

const props = defineProps({
  companyId: { type: String, required: true },
  sectionId: { type: String, required: true },
  cardId: { type: String, required: true },
  cardTitle: { type: String, default: "" },
  bullets: { type: Array, default: () => [] },
  depth: { type: Number, default: 0 },
});

const emit = defineEmits(["updated", "discuss"]);
const t = useT();

const editingId = ref(null);
const draftText = ref("");
const busyId = ref(null);
const error = ref("");

function sourceLabel(item) {
  return item?.source_class || item?.source_refs?.[0]?.source_class || t("memo.source_pending");
}

function startEdit(bullet) {
  editingId.value = bullet.id;
  draftText.value = bullet.text || "";
  error.value = "";
}

function cancelEdit() {
  editingId.value = null;
  draftText.value = "";
}

async function saveBullet(bullet) {
  busyId.value = bullet.id;
  error.value = "";
  try {
    const state = await api.memoEditor.patchBullet(
      props.companyId,
      props.sectionId,
      props.cardId,
      bullet.id,
      { text: draftText.value },
    );
    emit("updated", state);
    cancelEdit();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    busyId.value = null;
  }
}

async function diveDeeper(bullet) {
  busyId.value = bullet.id;
  error.value = "";
  try {
    const state = await api.memoEditor.diveDeeper(
      props.companyId,
      props.sectionId,
      props.cardId,
      bullet.id,
    );
    emit("updated", state);
    emit("discuss", {
      section_id: props.sectionId,
      section_title: props.sectionId,
      card_id: props.cardId,
      card_title: props.cardTitle,
      bullet_id: bullet.id,
      bullet_text: bullet.text,
      dive_deeper: true,
    });
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    busyId.value = null;
  }
}

function discuss(bullet) {
  emit("discuss", {
    section_id: props.sectionId,
    card_id: props.cardId,
    card_title: props.cardTitle,
    bullet_id: bullet.id,
    bullet_text: bullet.text,
  });
}
</script>

<template>
  <ul class="divide-y divide-subtle" :class="depth ? 'mt-2 border-l border-subtle pl-3' : 'border-y border-subtle'">
    <li
      v-for="bullet in bullets"
      :key="bullet.id"
      class="group py-3"
    >
      <CopilotDropZone
        :company-id="companyId"
        surface="memo_studio"
        tab="memo"
        :target-kind="TARGET_KINDS.MEMO_BULLET"
        :target-id="bullet.id"
        block
        :selection="{
          section_id: sectionId,
          section_title: sectionId,
          card_id: cardId,
          card_title: cardTitle,
          bullet_id: bullet.id,
          bullet_text: bullet.text,
          source_refs: bullet.source_refs || [],
          source_class: bullet.source_class,
        }"
      >
      <div v-if="editingId === bullet.id" class="space-y-2">
        <textarea
          v-model="draftText"
          rows="3"
          class="field focus-ring"
        />
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            @click="saveBullet(bullet)"
            :disabled="busyId === bullet.id"
            class="btn-filled btn-sm focus-ring"
          >
            <Save class="h-3.5 w-3.5" />
            {{ busyId === bullet.id ? t("common.saving") : t("memo.save") }}
          </button>
          <button
            type="button"
            @click="cancelEdit"
            class="inline-flex items-center gap-1 rounded-full border border-subtle px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
          >
            <X class="h-3.5 w-3.5" />
            {{ t("common.cancel") }}
          </button>
        </div>
      </div>
      <div v-else>
        <p class="text-sm leading-relaxed text-ink-secondary">{{ bullet.text }}</p>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <span class="rounded-full border border-subtle bg-surface-muted px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">
            {{ sourceLabel(bullet) }}
          </span>
          <span class="ml-auto flex items-center gap-1 transition sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
            <button
              type="button"
              @click="startEdit(bullet)"
              class="grid h-7 w-7 place-items-center rounded-full border border-subtle text-ink-secondary hover:bg-surface-muted focus-ring"
              :aria-label="t('memo.edit')"
              :title="t('memo.edit')"
            >
              <Pencil class="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              @click="diveDeeper(bullet)"
              :disabled="busyId === bullet.id"
              class="grid h-7 w-7 place-items-center rounded-full border border-subtle text-ink-secondary hover:bg-surface-muted disabled:opacity-60 focus-ring"
              :aria-label="t('memo.dive_deeper')"
              :title="t('memo.dive_deeper')"
            >
              <PlusCircle class="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              @click="discuss(bullet)"
              class="grid h-7 w-7 place-items-center rounded-full border border-subtle text-ink-secondary hover:bg-surface-muted focus-ring"
              :aria-label="t('memo.discuss')"
              :title="t('memo.discuss')"
            >
              <MessageSquare class="h-3.5 w-3.5" />
            </button>
          </span>
        </div>
      </div>
      <p v-if="error && busyId === bullet.id" class="mt-2 text-xs text-danger">
        {{ error }}
      </p>
      </CopilotDropZone>
      <MemoStudioBulletTree
        v-if="bullet.children?.length"
        :company-id="companyId"
        :section-id="sectionId"
        :card-id="cardId"
        :card-title="cardTitle"
        :bullets="bullet.children"
        :depth="depth + 1"
        @updated="$emit('updated', $event)"
        @discuss="$emit('discuss', $event)"
      />
    </li>
  </ul>
</template>
