<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { AlertCircle, Loader2, LogIn } from "lucide-vue-next";
import { signIn } from "../auth.js";
import { useT } from "../i18n.js";

const t = useT();
const route = useRoute();
const router = useRouter();

const email = ref("");
const password = ref("");
const errorMessage = ref(null);
const submitting = ref(false);

async function onSubmit() {
  if (submitting.value) return;
  const trimmedEmail = email.value.trim();
  if (!trimmedEmail || !password.value) return;
  submitting.value = true;
  errorMessage.value = null;
  try {
    await signIn(trimmedEmail, password.value);
    password.value = "";
    // Bounce back to wherever they were trying to go, default home.
    const next = typeof route.query.next === "string" ? route.query.next : "/";
    router.replace(next);
  } catch (e) {
    if (e && e.status === 401) {
      errorMessage.value = t("auth.invalid_credentials");
    } else {
      errorMessage.value = e?.message || t("auth.unknown_error");
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="min-h-screen flex items-center justify-center bg-surface-muted px-4">
    <form
      @submit.prevent="onSubmit"
      class="w-full max-w-sm bg-surface border border-subtle rounded-card shadow-card p-8 space-y-5"
    >
      <div class="flex items-center gap-3">
        <img src="/app-icon.png" alt="" class="h-12 w-12 rounded-lg object-cover shrink-0" />
        <div class="min-w-0">
          <h1 class="font-display text-lg font-semibold text-ink-primary leading-tight">
            {{ t("auth.title") }}
          </h1>
          <p class="text-xs text-ink-muted">{{ t("auth.subtitle") }}</p>
        </div>
      </div>

      <label class="block">
        <span class="text-xs font-medium uppercase tracking-wide text-ink-muted">
          {{ t("auth.email") }}
        </span>
        <input
          v-model="email"
          type="email"
          autocomplete="username"
          autocapitalize="none"
          spellcheck="false"
          required
          :disabled="submitting"
          class="mt-1 block w-full rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-sm text-ink-primary focus-ring"
        />
      </label>

      <label class="block">
        <span class="text-xs font-medium uppercase tracking-wide text-ink-muted">
          {{ t("auth.password") }}
        </span>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          :disabled="submitting"
          class="mt-1 block w-full rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-sm text-ink-primary focus-ring"
        />
      </label>

      <div
        v-if="errorMessage"
        class="flex items-start gap-2 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger"
      >
        <AlertCircle class="h-4 w-4 mt-0.5 shrink-0" />
        <span>{{ errorMessage }}</span>
      </div>

      <button
        type="submit"
        :disabled="submitting || !email.trim() || !password"
        class="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-accent text-white text-sm font-medium px-3 py-2.5 hover:bg-accent-hover focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Loader2 v-if="submitting" class="h-4 w-4 animate-spin" />
        <LogIn v-else class="h-4 w-4" />
        <span>{{ submitting ? t("auth.signing_in") : t("auth.sign_in") }}</span>
      </button>
    </form>
  </main>
</template>
