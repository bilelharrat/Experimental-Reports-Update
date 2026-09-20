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
import { isAnonDev, signIn } from "../auth.js";
import { useT } from "../i18n.js";
import { postAuthPath } from "../state.js";

const t = useT();
const route = useRoute();
const router = useRouter();

const email = ref("");
const password = ref("");
const isPasswordVisible = ref(false);
const focusedField = ref(null);
const errorMessage = ref(null);
const submitting = ref(false);

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
        <form class="contents" @submit.prevent="onSubmit">
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
              <template v-if="submitting">
                <Loader2 class="h-4 w-4 animate-spin text-white" />
                <span>{{ t("auth.authenticating") }}</span>
              </template>
              <template v-else>
                <span>{{ t("auth.sign_in_terminal") }}</span>
                <ArrowRight class="h-3 w-3 text-white/90" />
              </template>
            </button>

            <div class="flex items-center justify-between">
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

        <!-- Footer sync note -->
        <p class="text-center text-[11px] leading-[14px] text-ink-subtle">
          {{ t("auth.sync_footer") }}
        </p>
      </div>
    </div>
  </main>
</template>
