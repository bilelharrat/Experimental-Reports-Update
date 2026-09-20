<script setup>
// The far end of a reset link. The token arrives in the query string, is
// checked before anything is typed, and is spent by the submit — which
// also signs the person in, so a reset never dead-ends at a login form
// they still cannot pass.
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { AlertCircle, ArrowRight, Loader2, Lock } from "lucide-vue-next";
import BrandMark from "../components/BrandMark.vue";
import { api } from "../api.js";
import { adoptSession } from "../auth.js";
import { useT } from "../i18n.js";
import { postAuthPath } from "../state.js";

const t = useT();
const route = useRoute();
const router = useRouter();

const token = computed(() => String(route.query.token || ""));
const checking = ref(true);
const tokenEmail = ref(null);
const tokenError = ref(null);

const password = ref("");
const confirmPassword = ref("");
const focusedField = ref(null);
const errorMessage = ref(null);
const submitting = ref(false);

const canSubmit = computed(
  () => !submitting.value && Boolean(password.value) && Boolean(confirmPassword.value),
);

onMounted(async () => {
  if (!token.value) {
    tokenError.value = t("auth.reset_invalid");
    checking.value = false;
    return;
  }
  try {
    const res = await api.checkResetToken(token.value);
    tokenEmail.value = res?.email || null;
  } catch {
    tokenError.value = t("auth.reset_invalid");
  } finally {
    checking.value = false;
  }
});

async function onSubmit() {
  if (!canSubmit.value) return;
  if (password.value !== confirmPassword.value) {
    errorMessage.value = t("auth.passwords_differ");
    return;
  }
  submitting.value = true;
  errorMessage.value = null;
  try {
    const session = await api.consumePasswordReset(token.value, password.value);
    adoptSession(session);
    router.replace(postAuthPath("/"));
  } catch (e) {
    errorMessage.value = e?.detail || e?.message || t("auth.unknown_error");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="canvas-wash login-stage relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-8 select-none">
    <div class="login-summit" aria-hidden="true">
      <BrandMark :size="1100" />
    </div>

    <div
      class="relative z-10 h-[560px] w-[480px] max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2rem)] overflow-hidden rounded-[20px] border border-black/[0.08] bg-white/70 px-9 py-7 shadow-2xl shadow-black/15 backdrop-blur-2xl dark:border-white/[0.12] dark:bg-[#18191d]/85 dark:shadow-black/70"
    >
      <div
        class="pointer-events-none absolute left-[-40px] top-[-40px] h-[320px] w-[320px] rounded-full bg-[#38A8E8]/[0.14] blur-[65px] dark:bg-[#38A8E8]/[0.22]"
        aria-hidden="true"
      />

      <div class="relative z-10 flex h-full flex-col justify-center gap-5">
        <header class="flex flex-col items-center gap-3 text-center">
          <div class="login-tile">
            <BrandMark :size="38" class="relative z-10 text-ink-primary drop-shadow-sm" />
          </div>
          <div class="flex flex-col gap-1">
            <h1 class="font-display text-[22px] font-bold leading-[26px] tracking-tight text-ink-primary">
              {{ t("auth.reset_title") }}
            </h1>
            <p v-if="tokenEmail" class="text-[12px] font-medium leading-[14px] text-ink-secondary">
              {{ t("auth.reset_for", { email: tokenEmail }) }}
            </p>
          </div>
        </header>

        <p v-if="checking" class="text-center text-[12px] text-ink-subtle">
          {{ t("auth.checking_link") }}
        </p>

        <div
          v-else-if="tokenError"
          class="flex items-start gap-2.5 rounded-[10px] border border-red-500/[0.22] bg-red-500/[0.08] p-3 text-[12px] leading-4 text-red-600 dark:text-red-400"
          data-testid="reset-token-error"
        >
          <AlertCircle class="mt-px h-[13px] w-[13px] shrink-0" />
          <span>{{ tokenError }}</span>
        </div>

        <form v-else class="contents" @submit.prevent="onSubmit">
          <div class="flex flex-col gap-3">
            <div
              class="login-field flex items-center rounded-xl px-3.5 py-[11px]"
              :class="focusedField === 'password' ? 'login-field--focused' : ''"
            >
              <span class="flex w-[18px] shrink-0 justify-center">
                <Lock
                  class="h-4 w-4 transition-colors"
                  :class="focusedField === 'password' ? 'text-[#38A8E8]' : 'text-ink-secondary/80'"
                />
              </span>
              <input
                v-model="password"
                type="password"
                autocomplete="new-password"
                required
                :disabled="submitting"
                :placeholder="t('auth.new_password')"
                class="ml-2.5 w-full bg-transparent text-[13px] leading-4 text-ink-primary outline-none placeholder:text-ink-subtle"
                @focus="focusedField = 'password'"
                @blur="focusedField = null"
              />
            </div>

            <div
              class="login-field flex items-center rounded-xl px-3.5 py-[11px]"
              :class="focusedField === 'confirm' ? 'login-field--focused' : ''"
            >
              <span class="flex w-[18px] shrink-0 justify-center">
                <Lock
                  class="h-4 w-4 transition-colors"
                  :class="focusedField === 'confirm' ? 'text-[#38A8E8]' : 'text-ink-secondary/80'"
                />
              </span>
              <input
                v-model="confirmPassword"
                type="password"
                autocomplete="new-password"
                required
                :disabled="submitting"
                :placeholder="t('auth.confirm_password')"
                class="ml-2.5 w-full bg-transparent text-[13px] leading-4 text-ink-primary outline-none placeholder:text-ink-subtle"
                @focus="focusedField = 'confirm'"
                @blur="focusedField = null"
              />
            </div>
          </div>

          <div
            v-if="errorMessage"
            class="flex items-start gap-2.5 rounded-[10px] border border-red-500/[0.22] bg-red-500/[0.08] p-3 text-[12px] leading-4 text-red-600 dark:text-red-400"
            data-testid="reset-error"
          >
            <AlertCircle class="mt-px h-[13px] w-[13px] shrink-0" />
            <span>{{ errorMessage }}</span>
          </div>

          <div class="flex flex-col gap-3">
            <button
              type="submit"
              :disabled="!canSubmit"
              class="login-submit relative flex h-[38px] w-full items-center justify-center gap-2 rounded-[11px] text-[13px] font-semibold text-white transition-[filter] hover:brightness-105 active:brightness-95 disabled:cursor-not-allowed"
            >
              <Loader2 v-if="submitting" class="h-4 w-4 animate-spin text-white" />
              <span>{{ submitting ? t("auth.setting_password") : t("auth.set_password") }}</span>
              <ArrowRight v-if="!submitting" class="h-3 w-3 text-white/90" />
            </button>
          </div>
        </form>

        <p class="text-center text-[11px] leading-[14px] text-ink-subtle">
          {{ t("auth.sync_footer") }}
        </p>
      </div>
    </div>
  </main>
</template>
