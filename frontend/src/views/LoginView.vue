<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { AlertCircle, Loader2, LogIn } from "lucide-vue-next";
import BrandMark from "../components/BrandMark.vue";
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
  <main class="canvas-wash login-stage relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-12">
    <!-- The summit, very large and very faint, rising behind the sign-in sheet. -->
    <div class="login-summit" aria-hidden="true">
      <BrandMark :size="1100" />
    </div>

    <div class="relative z-10 flex w-full max-w-[380px] flex-col items-center">
      <span class="brand-tile login-tile">
        <BrandMark :size="38" />
      </span>
      <h1 class="mt-5 text-center font-display text-title1 text-ink-primary">
        {{ t("auth.title") }}
      </h1>
      <p class="mt-1 text-center text-callout text-ink-muted">{{ t("auth.subtitle") }}</p>

      <form
        @submit.prevent="onSubmit"
        class="glass-panel sheet-panel relative mt-7 w-full space-y-4 rounded-[22px] p-6"
      >
        <label class="block">
          <span class="text-footnote font-medium text-ink-secondary">
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
            class="field mt-1.5 block !py-2.5 text-callout"
          />
        </label>

        <label class="block">
          <span class="text-footnote font-medium text-ink-secondary">
            {{ t("auth.password") }}
          </span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            :disabled="submitting"
            class="field mt-1.5 block !py-2.5 text-callout"
          />
        </label>

        <div
          v-if="errorMessage"
          class="banner-danger flex items-start gap-2 !text-footnote"
        >
          <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
          <span>{{ errorMessage }}</span>
        </div>

        <button
          type="submit"
          :disabled="submitting || !email.trim() || !password"
          class="btn-filled focus-ring !mt-5 w-full !py-2.5 !text-callout"
        >
          <Loader2 v-if="submitting" class="h-4 w-4 animate-spin" />
          <LogIn v-else class="h-4 w-4" />
          <span>{{ submitting ? t("auth.signing_in") : t("auth.sign_in") }}</span>
        </button>
      </form>

      <p class="mt-6 text-caption1 text-ink-subtle">Berkeley Summit House</p>
    </div>
  </main>
</template>
