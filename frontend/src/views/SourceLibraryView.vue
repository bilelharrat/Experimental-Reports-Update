<script setup>
import { BookOpen, FileText, ShieldCheck } from "lucide-vue-next";
</script>

<template>
  <div class="mx-auto max-w-5xl px-8 py-10">
    <header class="mb-8">
      <div class="vogue-label">PRD source model</div>
      <h1 class="mt-2 font-display text-large-title text-ink-primary">
        Source Library &amp; Appendix
      </h1>
      <p class="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">
        This is the PRD destination for memo source classes, disclosures, and
        appendix fact blocks. It is intentionally separate from the Hormuz
        source library and from Serena's Background Documents folder.
      </p>
    </header>

    <div class="grid gap-4 md:grid-cols-3">
      <section class="rounded-card bg-surface p-5 shadow-card">
        <BookOpen class="h-5 w-5 text-accent" />
        <h2 class="mt-3 font-display text-title3 text-ink-primary">
          Source Classes
        </h2>
        <p class="mt-2 text-sm leading-relaxed text-ink-muted">
          Company materials, public filings, third-party market data, and BSH
          primary diligence will be grouped here with confidence and dates.
        </p>
      </section>
      <section class="rounded-card bg-surface p-5 shadow-card">
        <FileText class="h-5 w-5 text-accent" />
        <h2 class="mt-3 font-display text-title3 text-ink-primary">
          Appendix Blocks
        </h2>
        <p class="mt-2 text-sm leading-relaxed text-ink-muted">
          Memo fact blocks will stay collapsed by default and expose source
          traceability before export.
        </p>
      </section>
      <section class="rounded-card bg-surface p-5 shadow-card">
        <ShieldCheck class="h-5 w-5 text-accent" />
        <h2 class="mt-3 font-display text-title3 text-ink-primary">
          Disclosures
        </h2>
        <p class="mt-2 text-sm leading-relaxed text-ink-muted">
          Position and interest disclosures will live with memo source metadata,
          not with the Hormuz workflow.
        </p>
      </section>
    </div>
  </div>
</template>
