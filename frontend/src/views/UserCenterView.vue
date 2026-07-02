<script setup>
import { UserRound } from "lucide-vue-next";
import { sessionEmail } from "../auth.js";
</script>

<template>
  <div class="mx-auto max-w-4xl px-8 py-10">
    <header class="mb-8">
      <div class="vogue-label">Account</div>
      <h1 class="mt-2 font-display text-3xl font-bold text-ink-primary">
        User Center
      </h1>
    </header>

    <section class="rounded-card border border-subtle bg-surface p-6 shadow-card">
      <div class="flex items-start gap-4">
        <div
          class="grid h-14 w-14 place-items-center rounded-glass bg-accent-soft text-accent-ink"
        >
          <UserRound class="h-6 w-6" />
        </div>
        <div class="min-w-0">
          <div class="text-lg font-bold text-ink-primary">Elina Sun</div>
          <div class="text-sm text-ink-muted">{{ sessionEmail || "elina.sun@bshfoundation.org" }}</div>
          <div class="mt-3 flex flex-wrap gap-2">
            <span class="rounded-full bg-surface-muted px-3 py-1 text-xs font-semibold text-ink-secondary">
              Research Center
            </span>
            <span class="rounded-full bg-accent-soft px-3 py-1 text-xs font-semibold text-accent-ink">
              Analyst
            </span>
            <span class="rounded-full bg-surface-muted px-3 py-1 text-xs font-semibold text-ink-secondary">
              Berkeley Summit House
            </span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
