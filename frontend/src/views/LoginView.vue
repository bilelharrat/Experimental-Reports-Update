<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { AlertCircle, Loader2, LogIn } from "lucide-vue-next";
import brandLogoUrl from "../assets/berkeley-summit-house.svg";
import { signIn } from "../auth.js";
import { useT } from "../i18n.js";
import { postAuthPath } from "../state.js";

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
    router.replace(postAuthPath(next));
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
  <main class="flex min-h-screen items-center justify-center bg-canvas px-4">
    <form
      @submit.prevent="onSubmit"
      class="w-full max-w-[360px] space-y-6 rounded-glass bg-surface p-8 shadow-sheet"
    >
      <div>
        <img
          :src="brandLogoUrl"
          alt="Berkeley Summit House"
          class="h-auto w-[140px] max-w-full"
        />
        <div class="mt-4 min-w-0">
          <h1 class="font-display text-title2 text-ink-primary">
            {{ t("auth.title") }}
          </h1>
          <p class="mt-1 text-callout text-ink-muted">{{ t("auth.subtitle") }}</p>
        </div>
      </div>

      <label class="block">
        <span class="text-footnote font-medium text-ink-muted">
          {{ t("auth.identity") }}
        </span>
        <input
          v-model="email"
          type="text"
          autocomplete="username"
          autocapitalize="none"
          spellcheck="false"
          required
          :disabled="submitting"
          class="field mt-1.5 block py-2.5 text-callout focus-ring"
        />
      </label>

      <label class="block">
        <span class="text-footnote font-medium text-ink-muted">
          {{ t("auth.password") }}
        </span>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          :disabled="submitting"
          class="field mt-1.5 block py-2.5 text-callout focus-ring"
        />
      </label>

      <div
        v-if="errorMessage"
        class="flex items-start gap-2 rounded-subbox bg-danger-soft px-3 py-2 text-footnote text-danger-ink"
      >
        <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
        <span>{{ errorMessage }}</span>
      </div>

      <button
        type="submit"
        :disabled="submitting || !email.trim() || !password"
        class="btn-filled focus-ring w-full disabled:cursor-not-allowed"
      >
        <Loader2 v-if="submitting" class="h-4 w-4 animate-spin" />
        <LogIn v-else class="h-4 w-4" />
        <span>{{ submitting ? t("auth.signing_in") : t("auth.sign_in") }}</span>
      </button>
    </form>
  </main>
</template>
