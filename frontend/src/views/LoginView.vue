<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  AlertCircle,
  ArrowRight,
  ChevronRight,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  X,
} from "lucide-vue-next";
import BrandMark from "../components/BrandMark.vue";
import { api } from "../api.js";
import { isAnonDev, signIn } from "../auth.js";
import { useT } from "../i18n.js";
import { postAuthPath } from "../state.js";

const t = useT();
const route = useRoute();
const router = useRouter();

// One card, four states: sign in, request access, ask for a reset, and the
// two "we heard you" panels that follow the last two. Keeping them in the
// same sheet means the Mac metrics are written once.
const MODE_SIGN_IN = "signin";
const MODE_SIGN_UP = "signup";
const MODE_FORGOT = "forgot";
const MODE_PENDING = "pending";
const MODE_RESET_SENT = "reset_sent";

const mode = ref(MODE_SIGN_IN);
const email = ref("");
const password = ref("");
const confirmPassword = ref("");
const isPasswordVisible = ref(false);
const focusedField = ref(null);
const errorMessage = ref(null);
const submitting = ref(false);

const isSignUp = computed(() => mode.value === MODE_SIGN_UP);
const isForgot = computed(() => mode.value === MODE_FORGOT);
const isForm = computed(() =>
  [MODE_SIGN_IN, MODE_SIGN_UP, MODE_FORGOT].includes(mode.value),
);

function switchMode(next) {
  mode.value = next;
  errorMessage.value = null;
  password.value = "";
  confirmPassword.value = "";
}

const canSubmit = computed(() => {
  if (submitting.value || !email.value.trim()) return false;
  if (isForgot.value) return true;
  if (!password.value) return false;
  if (isSignUp.value) return Boolean(confirmPassword.value);
  return true;
});

const submitLabel = computed(() => {
  if (isSignUp.value)
    return submitting.value ? t("auth.creating_account") : t("auth.create_account");
  if (isForgot.value)
    return submitting.value ? t("auth.requesting_reset") : t("auth.request_reset");
  return submitting.value ? t("auth.authenticating") : t("auth.sign_in_terminal");
});

const emailInputRef = ref(null);
const passwordInputRef = ref(null);

const nodeHost = computed(() => {
  if (typeof window === "undefined") return "127.0.0.1";
  return window.location.hostname || "127.0.0.1";
});

const nodePort = computed(() => {
  if (typeof window === "undefined") return "8010";
  return window.location.port || (window.location.protocol === "https:" ? "443" : "80");
});

const isAnonDevMode = computed(() => isAnonDev());

const canCancel = computed(() => {
  if (typeof window === "undefined") return false;
  return Boolean(route.query.next) || window.history.length > 1;
});

function clearEmail() {
  email.value = "";
  emailInputRef.value?.focus();
}

function onCancel() {
  if (window.history.length > 1) {
    router.back();
  } else {
    router.replace(postAuthPath(route.query.next || "/"));
  }
}

function onContinueWithoutSigningIn() {
  const next = typeof route.query.next === "string" ? route.query.next : "/";
  router.replace(postAuthPath(next));
}

onMounted(() => {
  if (isAnonDev() && !route.query.switch) {
    onContinueWithoutSigningIn();
  }
});

async function onSubmit() {
  if (submitting.value || !canSubmit.value) return;
  const trimmedEmail = email.value.trim();

  if (isSignUp.value) {
    if (password.value !== confirmPassword.value) {
      errorMessage.value = t("auth.passwords_differ");
      return;
    }
    submitting.value = true;
    errorMessage.value = null;
    try {
      await api.register(trimmedEmail, password.value);
      password.value = "";
      confirmPassword.value = "";
      mode.value = MODE_PENDING;
    } catch (e) {
      errorMessage.value = e?.detail || e?.message || t("auth.unknown_error");
    } finally {
      submitting.value = false;
    }
    return;
  }

  if (isForgot.value) {
    submitting.value = true;
    errorMessage.value = null;
    try {
      await api.requestPasswordReset(trimmedEmail);
      mode.value = MODE_RESET_SENT;
    } catch (e) {
      errorMessage.value = e?.detail || e?.message || t("auth.unknown_error");
    } finally {
      submitting.value = false;
    }
    return;
  }

  if (!password.value) return;
  submitting.value = true;
  errorMessage.value = null;
  try {
    const res = await signIn(trimmedEmail, password.value);
    password.value = "";
    if (res?.must_reset) {
      // The server will refuse this session anything else until the
      // password is changed, so there is nowhere else worth sending it.
      router.replace({ name: "change-password" });
      return;
    }
    // Bounce back to wherever they were trying to go, default home.
    const next = typeof route.query.next === "string" ? route.query.next : "/";
    router.replace(postAuthPath(next));
  } catch (e) {
    if (e && e.status === 401) {
      errorMessage.value = t("auth.invalid_credentials");
    } else if (!e?.status || e.status >= 500) {
      // The sign-in never reached the account check: the API is down, or
      // the proxy in front of it could not reach it (dev's Vite answers
      // that with a bare 500). "500 Internal Server Error" tells the
      // person nothing they can act on; this says what happened and that
      // their password is not the problem.
      errorMessage.value = t("auth.server_unreachable");
    } else {
      // 403 carries the reason an account cannot be used yet — awaiting
      // approval, or disabled — which is the whole point of showing it.
      errorMessage.value = e?.detail || e?.message || t("auth.unknown_error");
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="canvas-wash login-stage relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-8 select-none">
    <!-- Ambient outer lights -->
    <div
      class="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-sky-500/10 blur-[100px] dark:bg-sky-500/15"
      aria-hidden="true"
    />
    <div
      class="pointer-events-none absolute -bottom-32 -right-32 h-96 w-96 rounded-full bg-indigo-500/10 blur-[100px] dark:bg-indigo-500/15"
      aria-hidden="true"
    />

    <!-- The summit, very large and very faint, rising behind the sign-in sheet. -->
    <div class="login-summit" aria-hidden="true">
      <BrandMark :size="1100" />
    </div>

    <!-- The macOS sheet at its own metrics: 480x560 inside 36pt horizontal
         and 28pt vertical padding (MacLoginView's .frame and .padding). -->
    <div
      class="relative z-10 h-[560px] w-[480px] max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2rem)] overflow-hidden rounded-[20px] border border-black/[0.08] bg-white/70 px-9 py-7 shadow-2xl shadow-black/15 backdrop-blur-2xl dark:border-white/[0.12] dark:bg-[#18191d]/85 dark:shadow-black/70"
    >
      <!-- The two lighting circles the Mac view sets behind the glass, at its
           sizes and blurs, placed where its offsets put them relative to the
           sheet's centre. -->
      <div
        class="pointer-events-none absolute left-[-40px] top-[-40px] h-[320px] w-[320px] rounded-full bg-[#38A8E8]/[0.14] blur-[65px] dark:bg-[#38A8E8]/[0.22]"
        aria-hidden="true"
      />
      <div
        class="pointer-events-none absolute bottom-[-30px] right-[-40px] h-[300px] w-[300px] rounded-full bg-[#735AF2]/[0.10] blur-[60px] dark:bg-[#735AF2]/[0.16]"
        aria-hidden="true"
      />

      <!-- Rising summit watermark inside the sheet -->
      <div
        class="pointer-events-none absolute bottom-[-30px] left-1/2 -translate-x-1/2 text-ink-primary/[0.04] dark:text-white/[0.04] [mask-image:linear-gradient(to_top,black_25%,transparent_90%)]"
        aria-hidden="true"
      >
        <BrandMark :size="520" />
      </div>

      <!-- One stack on 20pt gaps, centred in the sheet — the Mac view's body
           is a VStack(spacing: 20) in a fixed frame, so its content sits as
           one block in the middle rather than spread to the edges. -->
      <div class="relative z-10 flex h-full flex-col justify-center gap-5">
        <!-- Header & brand hero: VStack(spacing: 12) -->
        <header class="flex flex-col items-center gap-3 text-center">
          <!-- 72pt tile, 18pt corner -->
          <div class="login-tile">
            <BrandMark :size="38" class="relative z-10 text-ink-primary drop-shadow-sm" />
          </div>

          <div class="flex flex-col gap-1">
            <h1 class="font-display text-[22px] font-bold leading-[26px] tracking-tight text-ink-primary">
              {{ t("auth.title") }}
            </h1>
            <p class="text-[12px] font-medium leading-[14px] text-ink-secondary">
              {{ t("auth.terminal_subtitle") }}
            </p>
          </div>

          <!-- Server scope pill -->
          <div
            class="login-pill inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] leading-[13px]"
          >
            <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-[#34C759]" aria-hidden="true" />
            <span class="font-medium text-ink-secondary">{{ nodeHost }}</span>
            <span v-if="nodePort" class="font-medium text-ink-subtle">:{{ nodePort }}</span>
          </div>
        </header>

        <!-- `contents` so the form's groups are items of the 20pt stack above,
             exactly as the Mac view's VStack holds them. -->
        <form v-if="isForm" class="contents" @submit.prevent="onSubmit">
          <!-- Form inputs: VStack(spacing: 12) -->
          <div class="flex flex-col gap-3">
            <!-- Institutional email -->
            <div
              class="login-field flex items-center rounded-xl px-3.5 py-[11px]"
              :class="focusedField === 'email' ? 'login-field--focused' : ''"
            >
              <span class="flex w-[18px] shrink-0 justify-center">
                <Mail
                  class="h-4 w-4 transition-colors"
                  :class="focusedField === 'email' ? 'text-[#38A8E8]' : 'text-ink-secondary/80'"
                />
              </span>
              <input
                ref="emailInputRef"
                v-model="email"
                type="text"
                autocomplete="username"
                autocapitalize="none"
                spellcheck="false"
                required
                :disabled="submitting"
                :placeholder="t('auth.email_placeholder')"
                class="ml-2.5 w-full bg-transparent text-[13px] leading-4 text-ink-primary outline-none placeholder:text-ink-subtle"
                @focus="focusedField = 'email'"
                @blur="focusedField = null"
                @keydown.enter.prevent="passwordInputRef?.focus()"
              />
              <button
                v-if="email"
                type="button"
                class="shrink-0 text-ink-subtle transition-colors hover:text-ink-secondary"
                tabindex="-1"
                :aria-label="t('auth.clear_email')"
                @click="clearEmail"
              >
                <X class="h-[11px] w-[11px]" />
              </button>
            </div>

            <!-- Password -->
            <div
              v-if="!isForgot"
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
                ref="passwordInputRef"
                v-model="password"
                :type="isPasswordVisible ? 'text' : 'password'"
                autocomplete="current-password"
                required
                :disabled="submitting"
                :placeholder="t('auth.password')"
                class="ml-2.5 w-full bg-transparent text-[13px] leading-4 text-ink-primary outline-none placeholder:text-ink-subtle"
                @focus="focusedField = 'password'"
                @blur="focusedField = null"
              />
              <button
                type="button"
                class="shrink-0 transition-colors"
                :class="isPasswordVisible ? 'text-[#38A8E8]' : 'text-ink-secondary hover:text-ink-primary'"
                tabindex="-1"
                :aria-label="isPasswordVisible ? t('auth.hide_password') : t('auth.show_password')"
                @click="isPasswordVisible = !isPasswordVisible"
              >
                <EyeOff v-if="isPasswordVisible" class="h-3 w-3" />
                <Eye v-else class="h-3 w-3" />
              </button>
            </div>
            <!-- Confirm, sign-up only -->
            <div
              v-if="isSignUp"
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
                :type="isPasswordVisible ? 'text' : 'password'"
                autocomplete="new-password"
                required
                :disabled="submitting"
                :placeholder="t('auth.confirm_password')"
                class="ml-2.5 w-full bg-transparent text-[13px] leading-4 text-ink-primary outline-none placeholder:text-ink-subtle"
                @focus="focusedField = 'confirm'"
                @blur="focusedField = null"
              />
            </div>

            <p v-if="isForgot" class="text-[12px] leading-4 text-ink-subtle">
              {{ t("auth.forgot_body") }}
            </p>
          </div>

          <!-- Auth error: its own item in the 20pt stack, as on the Mac -->
          <div
            v-if="errorMessage"
            class="flex items-start gap-2.5 rounded-[10px] border border-red-500/[0.22] bg-red-500/[0.08] p-3 text-[12px] leading-4 text-red-600 dark:text-red-400"
          >
            <AlertCircle class="mt-px h-[13px] w-[13px] shrink-0" />
            <span>{{ errorMessage }}</span>
          </div>

          <!-- Actions: VStack(spacing: 12) -->
          <div class="flex flex-col gap-3">
            <button
              type="submit"
              :disabled="submitting || !email.trim() || !password"
              class="login-submit relative flex h-[38px] w-full items-center justify-center gap-2 rounded-[11px] text-[13px] font-semibold text-white transition-[filter] hover:brightness-105 active:brightness-95 disabled:cursor-not-allowed"
            >
              <Loader2 v-if="submitting" class="h-4 w-4 animate-spin text-white" />
              <span>{{ submitLabel }}</span>
              <ArrowRight v-if="!submitting" class="h-3 w-3 text-white/90" />
            </button>

            <!-- Move between the three forms -->
            <div class="flex items-center justify-between text-[11px]">
              <button
                v-if="!isForgot"
                type="button"
                class="font-medium text-ink-secondary transition-colors hover:text-ink-primary"
                @click="switchMode(MODE_FORGOT)"
              >
                {{ t("auth.forgot") }}
              </button>
              <button
                v-else
                type="button"
                class="font-medium text-ink-secondary transition-colors hover:text-ink-primary"
                @click="switchMode(MODE_SIGN_IN)"
              >
                {{ t("auth.back_to_sign_in") }}
              </button>

              <button
                v-if="!isForgot"
                type="button"
                class="inline-flex items-center gap-1 font-medium text-ink-secondary transition-colors hover:text-ink-primary"
                @click="switchMode(isSignUp ? MODE_SIGN_IN : MODE_SIGN_UP)"
              >
                <span>{{ isSignUp ? t("auth.have_account") : t("auth.need_account") }}</span>
                <ChevronRight class="h-[9px] w-[9px]" />
              </button>
            </div>

            <!-- Cancel and the local bypass: both are situational, so the
                 row itself goes when neither applies rather than leaving a
                 band of empty space in the sheet. -->
            <div
              v-if="canCancel || isAnonDevMode"
              class="flex items-center justify-between"
            >
              <button
                v-if="canCancel"
                type="button"
                class="text-[12px] font-medium text-ink-secondary transition-colors hover:text-ink-primary"
                @click="onCancel"
              >
                {{ t("auth.cancel") }}
              </button>
              <div v-else />

              <button
                v-if="isAnonDevMode"
                type="button"
                class="inline-flex items-center gap-1 text-[11px] font-medium text-ink-secondary transition-colors hover:text-ink-primary"
                @click="onContinueWithoutSigningIn"
              >
                <span>{{ t("auth.continue_without") }}</span>
                <ChevronRight class="h-[9px] w-[9px]" />
              </button>
            </div>
          </div>
        </form>

        <!-- Request received / reset requested: the same sheet, one message
             and a way back. -->
        <div v-else class="flex flex-col gap-3 text-center" data-testid="auth-notice">
          <h2 class="font-display text-[15px] font-semibold text-ink-primary">
            {{ mode === MODE_PENDING ? t("auth.pending_title") : t("auth.reset_requested_title") }}
          </h2>
          <p class="text-[12px] leading-[17px] text-ink-secondary">
            {{ mode === MODE_PENDING ? t("auth.pending_body") : t("auth.reset_requested_body") }}
          </p>
          <button
            type="button"
            class="text-[12px] font-medium text-ink-secondary transition-colors hover:text-ink-primary"
            @click="switchMode(MODE_SIGN_IN)"
          >
            {{ t("auth.back_to_sign_in") }}
          </button>
        </div>

        <!-- Footer sync note -->
        <p class="text-center text-[11px] leading-[14px] text-ink-subtle">
          {{ t("auth.sync_footer") }}
        </p>
      </div>
    </div>
  </main>
</template>
