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
  // The point the editor just scrolled to (one Warren edited): it glows.
  focusBulletId: { type: String, default: "" },
});

const emit = defineEmits(["updated", "discuss"]);
const t = useT();

const FOCUS_GLOW = {
  background: "color-mix(in srgb, var(--mac-accent) 12%, transparent)",
  boxShadow: "0 0 0 4px color-mix(in srgb, var(--mac-accent) 12%, transparent)",
};

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
  <ul :class="depth ? 'mt-1.5 border-l pl-3' : ''" :style="depth ? { borderColor: 'var(--mac-hairline)' } : {}">
    <li
      v-for="(bullet, bulletIndex) in bullets"
      :key="bullet.id"
      :data-bullet-id="bullet.id"
      class="group py-2"
      :class="bulletIndex > 0 || depth ? 'mac-hairline-t' : ''"
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
      <div v-if="editingId === bullet.id" class="flex flex-col gap-2">
        <textarea
          v-model="draftText"
          rows="3"
          class="mac-field w-full resize-y"
          style="line-height: 1.4"
        />
        <div class="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            class="mac-btn mac-btn--sm mac-btn--prominent"
            :disabled="busyId === bullet.id"
            @click="saveBullet(bullet)"
          >
            <Save class="h-3 w-3" />
            {{ busyId === bullet.id ? t("common.saving") : t("memo.save") }}
          </button>
          <button type="button" class="mac-btn mac-btn--sm" @click="cancelEdit">
            <X class="h-3 w-3" />
            {{ t("common.cancel") }}
          </button>
        </div>
      </div>
      <div
        v-else
        class="rounded-[4px] transition-[background-color,box-shadow] duration-700"
        :data-focused="bullet.id === focusBulletId || null"
        :style="bullet.id === focusBulletId ? FOCUS_GLOW : null"
      >
        <p class="mac-t-caption" style="line-height: 1.5">{{ bullet.text }}</p>
        <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span class="mac-status-tag" :style="{ '--tint': 'var(--mac-secondary)' }">
            {{ sourceLabel(bullet) }}
          </span>
          <span class="ml-auto flex items-center gap-1 transition sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
            <button
              type="button"
              class="mac-btn mac-btn--mini mac-btn--plain"
              :aria-label="t('memo.edit')"
              :title="t('memo.edit')"
              @click="startEdit(bullet)"
            >
              <Pencil class="h-3 w-3" />
            </button>
            <button
              type="button"
              class="mac-btn mac-btn--mini mac-btn--plain"
              :disabled="busyId === bullet.id"
              :aria-label="t('memo.dive_deeper')"
              :title="t('memo.dive_deeper')"
              @click="diveDeeper(bullet)"
            >
              <PlusCircle class="h-3 w-3" />
            </button>
            <button
              type="button"
              class="mac-btn mac-btn--mini mac-btn--plain"
              :aria-label="t('memo.discuss')"
              :title="t('memo.discuss')"
              @click="discuss(bullet)"
            >
              <MessageSquare class="h-3 w-3" />
            </button>
          </span>
        </div>
      </div>
      <p v-if="error && busyId === bullet.id" class="mac-t-caption10 mt-1.5" :style="{ color: 'var(--mac-red)' }">
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
        :focus-bullet-id="focusBulletId"
        @updated="$emit('updated', $event)"
        @discuss="$emit('discuss', $event)"
      />
    </li>
  </ul>
</template>
