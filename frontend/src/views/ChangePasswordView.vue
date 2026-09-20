<script setup>
// Change the signed-in account's password. Reached voluntarily from the
// account page, or forced: a session flagged must_reset — a seeded
// account on the bootstrap password, or one an operator marked — is sent
// here from everywhere else, and the server refuses it anything but this
// until the change lands. The server answers with a fresh session, since
// every other one for the account ends on the change.
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { AlertCircle, ArrowRight, Loader2, Lock } from "lucide-vue-next";
import BrandMark from "../components/BrandMark.vue";
import { api } from "../api.js";
import { adoptSession, mustResetPassword, sessionEmail } from "../auth.js";
import { useT } from "../i18n.js";
import { postAuthPath } from "../state.js";

const t = useT();
const router = useRouter();

const currentPassword = ref("");
const password = ref("");
const confirmPassword = ref("");
const focusedField = ref(null);
const errorMessage = ref(null);
const submitting = ref(false);

const canSubmit = computed(
  () =>
    !submitting.value &&
    Boolean(currentPassword.value) &&
    Boolean(password.value) &&
    Boolean(confirmPassword.value),
);

async function onSubmit() {
  if (!canSubmit.value) return;
  if (password.value !== confirmPassword.value) {
    errorMessage.value = t("auth.passwords_differ");
    return;
  }
  submitting.value = true;
  errorMessage.value = null;
  try {
    const session = await api.changePassword(currentPassword.value, password.value);
    await adoptSession(session);
    router.replace(postAuthPath("/"));
  } catch (e) {
    errorMessage.value = e?.detail || e?.message || t("auth.unknown_error");
  } finally {
    submitting.value = false;
  }
}

const fields = [
  { key: "current", model: currentPassword, label: "auth.current_password", autocomplete: "current-password" },
  { key: "password", model: password, label: "auth.new_password", autocomplete: "new-password" },
  { key: "confirm", model: confirmPassword, label: "auth.confirm_password", autocomplete: "new-password" },
];
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
              {{ t("auth.change_title") }}
            </h1>
            <p class="text-[12px] font-medium leading-[14px] text-ink-secondary">
              {{ sessionEmail }}
            </p>
          </div>
        </header>

        <p class="text-center text-[12px] leading-4 text-ink-subtle" data-testid="change-password-reason">
          {{ mustResetPassword ? t("auth.change_forced_body") : t("auth.change_body") }}
        </p>

        <form class="contents" @submit.prevent="onSubmit">
          <div class="flex flex-col gap-3">
            <div
              v-for="field in fields"
              :key="field.key"
              class="login-field flex items-center rounded-xl px-3.5 py-[11px]"
              :class="focusedField === field.key ? 'login-field--focused' : ''"
            >
              <span class="flex w-[18px] shrink-0 justify-center">
                <Lock
                  class="h-4 w-4 transition-colors"
                  :class="focusedField === field.key ? 'text-[#38A8E8]' : 'text-ink-secondary/80'"
                />
              </span>
              <input
                v-model="field.model.value"
                type="password"
                :autocomplete="field.autocomplete"
                required
                :disabled="submitting"
                :placeholder="t(field.label)"
                class="ml-2.5 w-full bg-transparent text-[13px] leading-4 text-ink-primary outline-none placeholder:text-ink-subtle"
                @focus="focusedField = field.key"
                @blur="focusedField = null"
              />
            </div>
          </div>

          <div
            v-if="errorMessage"
            class="flex items-start gap-2.5 rounded-[10px] border border-red-500/[0.22] bg-red-500/[0.08] p-3 text-[12px] leading-4 text-red-600 dark:text-red-400"
            data-testid="change-password-error"
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
              <span>{{ submitting ? t("auth.changing") : t("auth.change_submit") }}</span>
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
