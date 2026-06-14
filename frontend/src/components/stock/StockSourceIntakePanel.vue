<script setup>
import { FileText, Link, Upload } from "lucide-vue-next";

const props = defineProps({
  trackers: { type: Array, default: () => [] },
  sources: { type: Array, default: () => [] },
  sourceTrackerIds: { type: Array, default: () => [] },
  fileForm: { type: Object, default: () => ({}) },
  linkForm: { type: Object, default: () => ({}) },
  noteForm: { type: Object, default: () => ({}) },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits([
  "toggle-source-tracker",
  "update-file-form",
  "update-link-form",
  "update-note-form",
  "file-picked",
  "submit-file-source",
  "submit-link-source",
  "submit-note-source",
]);

function fmtDate(value) {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function sourceState(source) {
  if (source.extraction_status === "missing") return "missing";
  if (source.ocr_needed || source.extraction_status === "ocr_needed") return "ocr needed";
  return source.extraction_status || "metadata";
}

function updateFileForm(field, value) {
  emit("update-file-form", { ...props.fileForm, [field]: value });
}

function updateLinkForm(field, value) {
  emit("update-link-form", { ...props.linkForm, [field]: value });
}

function updateNoteForm(field, value) {
  emit("update-note-form", { ...props.noteForm, [field]: value });
}
</script>

<template>
  <section class="space-y-4">
    <div class="grid gap-4 xl:grid-cols-[22rem_1fr]">
      <aside class="rounded-lg border border-subtle bg-surface p-4">
        <h2 class="text-sm font-semibold">Assign Source</h2>
        <div class="mt-3 space-y-2">
          <label
            v-for="tracker in trackers"
            :key="tracker.id"
            class="flex items-center gap-2 text-sm"
          >
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-subtle"
              :checked="sourceTrackerIds.includes(tracker.id)"
              @change="emit('toggle-source-tracker', tracker.id)"
            />
            <span class="truncate">{{ tracker.display_name }}</span>
          </label>
        </div>
        <div class="mt-5 space-y-3">
          <input
            :value="fileForm.title"
            class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            placeholder="File title"
            @input="updateFileForm('title', $event.target.value)"
          />
          <input
            type="file"
            class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            @change="emit('file-picked', $event)"
          />
          <button
            type="button"
            class="inline-flex w-full items-center justify-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
            :disabled="busy || !sourceTrackerIds.length || !fileForm.file"
            @click="emit('submit-file-source')"
          >
            <Upload class="h-4 w-4" />
            Upload File
          </button>
        </div>
        <div class="mt-5 space-y-3 border-t border-subtle pt-4">
          <input
            :value="linkForm.title"
            class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            placeholder="Link title"
            @input="updateLinkForm('title', $event.target.value)"
          />
          <input
            :value="linkForm.url"
            class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            placeholder="https://source.example"
            @input="updateLinkForm('url', $event.target.value)"
          />
          <textarea
            :value="linkForm.notes"
            class="min-h-20 w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            placeholder="Source notes"
            @input="updateLinkForm('notes', $event.target.value)"
          ></textarea>
          <button
            type="button"
            class="inline-flex w-full items-center justify-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white focus-ring disabled:opacity-50"
            :disabled="busy || !sourceTrackerIds.length || !linkForm.url"
            @click="emit('submit-link-source')"
          >
            <Link class="h-4 w-4" />
            Attach Link
          </button>
        </div>
        <div class="mt-5 space-y-3 border-t border-subtle pt-4">
          <input
            :value="noteForm.title"
            class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            placeholder="Note title"
            @input="updateNoteForm('title', $event.target.value)"
          />
          <textarea
            :value="noteForm.body"
            class="min-h-24 w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            placeholder="Analyst note"
            @input="updateNoteForm('body', $event.target.value)"
          ></textarea>
          <button
            type="button"
            class="inline-flex w-full items-center justify-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
            :disabled="busy || !sourceTrackerIds.length || !noteForm.body"
            @click="emit('submit-note-source')"
          >
            <FileText class="h-4 w-4" />
            Add Note
          </button>
        </div>
      </aside>
      <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
        <table class="min-w-full text-left text-sm">
          <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th class="px-3 py-2">Source</th>
              <th class="px-3 py-2">Tracker</th>
              <th class="px-3 py-2">Type</th>
              <th class="px-3 py-2">State</th>
              <th class="px-3 py-2">Relevance</th>
              <th class="px-3 py-2">Trace Preview</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="source in sources" :key="`${source.tracker_id}:${source.id}`" class="border-b border-subtle last:border-0">
              <td class="px-3 py-2">
                <div class="font-medium">{{ source.title || source.filename }}</div>
                <div class="text-xs text-ink-muted">{{ fmtDate(source.created_at) }}</div>
              </td>
              <td class="px-3 py-2">{{ source.tracker_name || source.tracker_id }}</td>
              <td class="px-3 py-2">{{ source.source_type }}</td>
              <td class="px-3 py-2">
                <span
                  class="rounded px-2 py-1 text-xs"
                  :class="source.extraction_status === 'missing' ? 'bg-danger-soft text-danger-ink' : 'bg-surface-muted text-ink-secondary'"
                >
                  {{ sourceState(source) }}
                </span>
              </td>
              <td class="px-3 py-2">{{ source.relevance }}</td>
              <td class="max-w-lg px-3 py-2 text-ink-secondary">
                <div class="line-clamp-2">
                  {{ source.missing_reason || source.chunks?.[0]?.excerpt || source.url || "No preview." }}
                </div>
              </td>
            </tr>
            <tr v-if="sources.length === 0">
              <td colspan="6" class="px-3 py-8 text-center text-sm text-ink-muted">
                No tracker-owned sources yet.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
