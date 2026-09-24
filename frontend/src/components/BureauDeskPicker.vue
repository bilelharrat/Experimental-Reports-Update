<script setup>
import { useId } from "vue";
import { Check } from "lucide-vue-next";
import { BUREAU_DESKS, BUREAU_DESK_COLORS, bureauDesk, setBureauDesk } from "../design.js";
import { useT } from "../i18n.js";

// Bureau's desk color as a group of swatches: in Settings while Bureau is on,
// and in the welcome tour's "Choose a look" step once Bureau is picked. The
// radios are native (visually hidden), so Tab lands on the chosen desk and
// the arrow keys move between them; choosing one applies it at once.

const t = useT();
// One radio group per picker, even when Settings and the tour both show one.
const group = `bureau-desk-${useId()}`;

/** Onyx & White is split white and black; the others show their day's desk. */
function swatchStyle(id) {
  const [day, night] = BUREAU_DESK_COLORS[id].desk;
  return id === "onyx"
    ? { background: `linear-gradient(135deg, ${day} 50%, ${night} 50%)` }
    : { background: day };
}
</script>

<template>
  <fieldset class="desk-picker" data-testid="bureau-desk-picker">
    <legend class="vogue-label mb-2">{{ t("settings.design_desk") }}</legend>
    <div class="desk-picker-options">
      <label
        v-for="id in BUREAU_DESKS"
        :key="id"
        class="desk-picker-option"
        :data-selected="bureauDesk === id"
        :data-testid="`bureau-desk-${id}`"
      >
        <input
          type="radio"
          class="sr-only"
          :name="group"
          :value="id"
          :checked="bureauDesk === id"
          @change="setBureauDesk(id)"
        />
        <span class="desk-picker-swatch" :style="swatchStyle(id)" aria-hidden="true">
          <span v-if="bureauDesk === id" class="desk-picker-check">
            <Check :size="10" :stroke-width="3" />
          </span>
        </span>
        <span class="desk-picker-name">{{ t(`settings.design_desk_${id}`) }}</span>
      </label>
    </div>
  </fieldset>
</template>
