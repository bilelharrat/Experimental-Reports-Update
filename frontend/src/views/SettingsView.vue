<script setup>
import { Bell, Database, Languages, SlidersHorizontal } from "lucide-vue-next";
import { appLanguage, setAppLanguage } from "../state.js";
</script>

<template>
  <div class="mx-auto max-w-5xl px-8 py-10">
    <header class="mb-8">
      <div class="vogue-label">Workspace</div>
      <h1 class="mt-2 font-display text-3xl font-bold text-ink-primary">
        Settings
      </h1>
    </header>

    <div class="grid gap-4 lg:grid-cols-2">
      <section class="rounded-card border border-subtle bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Languages class="h-4 w-4 text-accent" />
          <h2 class="font-display text-lg font-bold text-ink-primary">
            Preferences
          </h2>
        </div>
        <div class="mt-4">
          <div class="vogue-label mb-2">Language</div>
          <div
            class="inline-flex overflow-hidden rounded-full border border-subtle bg-surface text-sm"
            role="group"
            aria-label="App language"
          >
            <button
              type="button"
              @click="setAppLanguage('en')"
              :class="[
                'px-4 py-2 focus-ring',
                appLanguage === 'en'
                  ? 'bg-accent text-white'
                  : 'text-ink-secondary hover:bg-surface-muted',
              ]"
            >
              EN
            </button>
            <button
              type="button"
              @click="setAppLanguage('zh')"
              :class="[
                'border-l border-subtle px-4 py-2 focus-ring',
                appLanguage === 'zh'
                  ? 'bg-accent text-white'
                  : 'text-ink-secondary hover:bg-surface-muted',
              ]"
            >
              中文
            </button>
          </div>
        </div>
      </section>

      <section class="rounded-card border border-subtle bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Bell class="h-4 w-4 text-accent" />
          <h2 class="font-display text-lg font-bold text-ink-primary">
            Alerts
          </h2>
        </div>
        <div class="mt-4 space-y-3 text-sm text-ink-secondary">
          <label class="flex items-center justify-between gap-3">
            <span>Weekly summary</span>
            <input type="checkbox" checked class="h-4 w-4 accent-[var(--tiffany)]" />
          </label>
          <label class="flex items-center justify-between gap-3">
            <span>Stock auto-refresh</span>
            <input type="checkbox" checked class="h-4 w-4 accent-[var(--tiffany)]" />
          </label>
          <label class="flex items-center justify-between gap-3">
            <span>Agent task alerts</span>
            <input type="checkbox" checked class="h-4 w-4 accent-[var(--tiffany)]" />
          </label>
        </div>
      </section>

      <section class="rounded-card border border-subtle bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Database class="h-4 w-4 text-accent" />
          <h2 class="font-display text-lg font-bold text-ink-primary">
            System Status
          </h2>
        </div>
        <div class="mt-4 grid gap-2 text-sm">
          <div class="flex justify-between rounded-row bg-surface-muted px-3 py-2">
            <span>Research engine</span>
            <span class="font-semibold text-accent-ink">Ready</span>
          </div>
          <div class="flex justify-between rounded-row bg-surface-muted px-3 py-2">
            <span>Memo generation</span>
            <span class="font-semibold text-accent-ink">Ready</span>
          </div>
          <div class="flex justify-between rounded-row bg-surface-muted px-3 py-2">
            <span>Document index</span>
            <span class="font-semibold text-accent-ink">Ready</span>
          </div>
        </div>
      </section>

      <section class="rounded-card border border-subtle bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <SlidersHorizontal class="h-4 w-4 text-accent" />
          <h2 class="font-display text-lg font-bold text-ink-primary">
            Usage
          </h2>
        </div>
        <p class="mt-4 text-sm leading-relaxed text-ink-muted">
          Usage and role-backed preferences will attach to the account adapter in
          a later slice. The route is available now from the global header and
          rail.
        </p>
      </section>
    </div>
  </div>
</template>
