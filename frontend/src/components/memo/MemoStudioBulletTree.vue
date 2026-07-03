<script setup>
import { ref } from "vue";
import { MessageSquare, Pencil, PlusCircle, Save, X } from "lucide-vue-next";
import { api } from "../../api.js";

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

const editingId = ref(null);
const draftText = ref("");
const busyId = ref(null);
const error = ref("");

function sourceLabel(item) {
  return item?.source_class || item?.source_refs?.[0]?.source_class || "unknown/pending";
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
  <ul class="space-y-2" :class="depth ? 'mt-2 border-l border-subtle pl-3' : ''">
    <li
      v-for="bullet in bullets"
      :key="bullet.id"
      class="rounded-lg border border-subtle bg-surface px-3 py-2"
    >
      <div v-if="editingId === bullet.id" class="space-y-2">
        <textarea
          v-model="draftText"
          rows="3"
          class="w-full rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-sm text-ink-primary focus-ring"
        />
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            @click="saveBullet(bullet)"
            :disabled="busyId === bullet.id"
            class="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60 focus-ring"
          >
            <Save class="h-3.5 w-3.5" />
            Save
          </button>
          <button
            type="button"
            @click="cancelEdit"
            class="inline-flex items-center gap-1 rounded-full border border-subtle px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
          >
            <X class="h-3.5 w-3.5" />
            Cancel
          </button>
        </div>
      </div>
      <div v-else>
        <p class="text-sm leading-relaxed text-ink-secondary">{{ bullet.text }}</p>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <span class="rounded-full border border-subtle bg-surface-muted px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">
            {{ sourceLabel(bullet) }}
          </span>
          <button
            type="button"
            @click="startEdit(bullet)"
            class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
          >
            <Pencil class="h-3.5 w-3.5" />
            Edit
          </button>
          <button
            type="button"
            @click="diveDeeper(bullet)"
            :disabled="busyId === bullet.id"
            class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted disabled:opacity-60 focus-ring"
          >
            <PlusCircle class="h-3.5 w-3.5" />
            Dive Deeper
          </button>
          <button
            type="button"
            @click="discuss(bullet)"
            class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
          >
            <MessageSquare class="h-3.5 w-3.5" />
            Discuss
          </button>
        </div>
      </div>
      <p v-if="error && busyId === bullet.id" class="mt-2 text-xs text-danger">
        {{ error }}
      </p>
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
