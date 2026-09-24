<script setup>
import { computed, useId } from "vue";
import { Check } from "lucide-vue-next";
import {
  BUREAU_DESK_COLORS,
  DEFAULT_BUREAU_DESK,
  DEFAULT_DESIGN,
  DESIGNS,
  bureauDesk,
  design,
  setDesign,
} from "../design.js";
import { useT } from "../i18n.js";

// The three designs as cards, for the welcome tour's "Choose a look" step: a
// miniature of each one's ground and page, its name and a line about it. The
// radios are native (visually hidden), like the desk swatches, and choosing
// one applies it at once, as Settings does.

const t = useT();
const group = `design-look-${useId()}`;

const options = computed(() =>
  DESIGNS.map((id) => ({
    id,
    name: t(`settings.design_${id}`),
    body: t(`welcome.look_${id}_body`),
  })),
);

// Bureau's miniature is painted in the desk it would open on, by day and by
// night; the stylesheet picks the one that matches the appearance.
const bureauPreview = computed(() => {
  const colors = BUREAU_DESK_COLORS[bureauDesk.value] || BUREAU_DESK_COLORS[DEFAULT_BUREAU_DESK];
  return {
    "--look-desk-day": colors.desk[0],
    "--look-desk-night": colors.desk[1],
    "--look-sheet-day": colors.sheet[0],
    "--look-sheet-night": colors.sheet[1],
  };
});
</script>

<template>
  <fieldset class="look-cards" data-testid="design-look-cards">
    <legend class="sr-only">{{ t("welcome.look_title") }}</legend>
    <label
      v-for="option in options"
      :key="option.id"
      class="look-card"
      :data-selected="design === option.id"
      :data-testid="`design-look-${option.id}`"
    >
      <input
        type="radio"
        class="sr-only"
        :name="group"
        :value="option.id"
        :checked="design === option.id"
        @change="setDesign(option.id)"
      />
      <span
        class="look-card-preview"
        :data-look="option.id"
        :style="option.id === 'bureau' ? bureauPreview : undefined"
        aria-hidden="true"
      >
        <span class="look-card-page" />
      </span>
      <span class="look-card-text">
        <span class="look-card-name">
          {{ option.name }}
          <span v-if="option.id === DEFAULT_DESIGN" class="look-card-default">{{ t("welcome.look_default") }}</span>
        </span>
        <span class="look-card-body">{{ option.body }}</span>
      </span>
      <span v-if="design === option.id" class="look-card-check" aria-hidden="true">
        <Check :size="12" :stroke-width="3" />
      </span>
    </label>
  </fieldset>
</template>
