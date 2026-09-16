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

    <!-- Summit Glass Card (exact match with macOS 480x560pt modal) -->
    <div
      class="relative z-10 flex h-[560px] w-[480px] max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2rem)] flex-col justify-between overflow-hidden rounded-[20px] border border-black/[0.08] bg-white/70 px-9 py-7 shadow-2xl shadow-black/15 backdrop-blur-2xl dark:border-white/[0.12] dark:bg-[#18191d]/85 dark:shadow-black/70"
    >
      <!-- Card ambient lighting wash -->
      <div
        class="pointer-events-none absolute -left-20 -top-24 h-72 w-72 rounded-full bg-accent/20 blur-[65px] dark:bg-accent/25"
        aria-hidden="true"
      />
      <div
        class="pointer-events-none absolute -bottom-20 -right-20 h-72 w-72 rounded-full bg-[#7359F2]/12 blur-[60px] dark:bg-[#7359F2]/18"
        aria-hidden="true"
      />

      <!-- Rising summit watermark inside the card -->
      <div
        class="pointer-events-none absolute -bottom-8 left-1/2 -translate-x-1/2 text-ink-primary/[0.04] dark:text-white/[0.04] [mask-image:linear-gradient(to_top,black_25%,transparent_90%)]"
        aria-hidden="true"
      >
        <BrandMark :size="520" />
      </div>

      <div class="relative z-10 flex h-full flex-col justify-between">
        <!-- Header & Brand Hero -->
        <header class="flex flex-col items-center text-center">
          <!-- BSH Brand Tile (72x72 Apple dock squircle with specular rim & glow) -->
          <div class="login-tile">
            <BrandMark :size="38" class="relative z-10 text-ink-primary drop-shadow-sm" />
          </div>

          <h1 class="mt-3.5 font-display text-[22px] font-bold tracking-tight text-ink-primary">
            {{ t("auth.title") }}
          </h1>
          <p class="mt-0.5 text-[12px] font-medium text-ink-secondary">
            {{ t("auth.terminal_subtitle") }}
          </p>

          <!-- Node Scope Pill -->
          <div class="mt-3 flex items-center justify-center">
            <div
              class="inline-flex items-center gap-1.5 rounded-full border border-black/[0.08] bg-black/[0.04] px-3 py-1 font-mono text-[11px] text-ink-secondary dark:border-white/[0.12] dark:bg-white/[0.08]"
            >
              <span
                class="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.7)]"
                aria-hidden="true"
              />
              <span class="font-medium">{{ nodeHost }}</span>
              <span v-if="nodePort" class="text-ink-subtle">:{{ nodePort }}</span>
            </div>
          </div>
        </header>

        <!-- Form Inputs & Actions -->
        <form @submit.prevent="onSubmit" class="space-y-4">
          <!-- Form Inputs -->
          <div class="space-y-3">
            <!-- Institutional Email -->
            <div
              class="group relative flex h-10 items-center rounded-[10px] border bg-black/[0.035] px-3.5 transition-all dark:bg-white/[0.05]"
              :class="[
                focusedField === 'email'
                  ? 'border-accent shadow-[0_0_12px_rgba(var(--color-accent-glow),0.35)] ring-1 ring-accent'
                  : 'border-black/[0.08] dark:border-white/[0.12] hover:border-black/[0.15] dark:hover:border-white/[0.2]',
              ]"
            >
              <Mail
                class="h-4 w-4 shrink-0 transition-colors"
                :class="focusedField === 'email' ? 'text-accent' : 'text-ink-secondary/70'"
              />
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
                class="ml-2.5 w-full bg-transparent text-[13px] text-ink-primary outline-none placeholder:text-ink-subtle"
                @focus="focusedField = 'email'"
                @blur="focusedField = null"
                @keydown.enter.prevent="passwordInputRef?.focus()"
              />
              <button
                v-if="email"
                type="button"
                class="p-0.5 text-ink-subtle transition-colors hover:text-ink-secondary"
                tabindex="-1"
                :aria-label="t('auth.clear_email')"
                @click="clearEmail"
              >
                <X class="h-3.5 w-3.5" />
              </button>
            </div>

            <!-- Password -->
            <div
              class="group relative flex h-10 items-center rounded-[10px] border bg-black/[0.035] px-3.5 transition-all dark:bg-white/[0.05]"
              :class="[
                focusedField === 'password'
                  ? 'border-accent shadow-[0_0_12px_rgba(var(--color-accent-glow),0.35)] ring-1 ring-accent'
                  : 'border-black/[0.08] dark:border-white/[0.12] hover:border-black/[0.15] dark:hover:border-white/[0.2]',
              ]"
            >
              <Lock
                class="h-4 w-4 shrink-0 transition-colors"
                :class="focusedField === 'password' ? 'text-accent' : 'text-ink-secondary/70'"
              />
              <input
                ref="passwordInputRef"
                v-model="password"
                :type="isPasswordVisible ? 'text' : 'password'"
                autocomplete="current-password"
                required
                :disabled="submitting"
                :placeholder="t('auth.password')"
                class="ml-2.5 w-full bg-transparent text-[13px] text-ink-primary outline-none placeholder:text-ink-subtle"
                @focus="focusedField = 'password'"
                @blur="focusedField = null"
              />
              <button
                type="button"
                class="p-0.5 text-ink-subtle transition-colors hover:text-ink-secondary"
                tabindex="-1"
                :aria-label="isPasswordVisible ? t('auth.hide_password') : t('auth.show_password')"
                @click="isPasswordVisible = !isPasswordVisible"
              >
                <EyeOff v-if="isPasswordVisible" class="h-3.5 w-3.5" />
                <Eye v-else class="h-3.5 w-3.5" />
              </button>
            </div>

            <!-- Auth Error Banner -->
            <div
              v-if="errorMessage"
              class="flex items-start gap-2.5 rounded-[10px] border border-red-500/25 bg-red-500/10 p-2.5 text-[12px] text-red-600 dark:text-red-400"
            >
              <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
              <span class="leading-relaxed">{{ errorMessage }}</span>
            </div>
          </div>

          <!-- Actions & Controls -->
          <div class="space-y-3 pt-1">
            <!-- Submit Button -->
            <button
              type="submit"
              :disabled="submitting || !email.trim() || !password"
              class="relative flex h-10 w-full items-center justify-center gap-2 rounded-[10px] border-t border-white/40 bg-gradient-to-b from-[#0B87D6] to-[#0370C2] text-[13px] font-semibold text-white shadow-lg shadow-[#0B87D6]/35 transition-all hover:brightness-105 active:brightness-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            >
              <template v-if="submitting">
                <Loader2 class="h-4 w-4 animate-spin text-white" />
                <span>{{ t("auth.authenticating") }}</span>
              </template>
              <template v-else>
                <span>{{ t("auth.sign_in_terminal") }}</span>
                <ArrowRight class="h-3.5 w-3.5" />
              </template>
            </button>

            <!-- Secondary Actions (Cancel / Continue without signing in) -->
            <div class="flex items-center justify-between text-[12px]">
              <button
                v-if="canCancel"
                type="button"
                class="font-medium text-ink-secondary transition-colors hover:text-ink-primary"
                @click="onCancel"
              >
                {{ t("auth.cancel") }}
              </button>
              <div v-else />

              <button
                v-if="isAnonDevMode"
                type="button"
                class="inline-flex items-center gap-1 font-medium text-ink-secondary transition-colors hover:text-ink-primary"
                @click="onContinueWithoutSigningIn"
              >
                <span>{{ t("auth.continue_without") }}</span>
                <ChevronRight class="h-3 w-3" />
              </button>
            </div>
          </div>
        </form>

        <!-- Footer Sync Note -->
        <p class="text-center text-[11px] leading-relaxed text-ink-subtle">
          {{ t("auth.sync_footer") }}
        </p>
      </div>
    </div>
  </main>
</template>
