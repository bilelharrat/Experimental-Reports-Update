<script setup>
// Web twin of MacTabBar (MacDesign.swift): App Store-style underline tabs.
// The 2px accent underline is one shared element that slides between tabs,
// matching the Mac's matchedGeometryEffect, instead of fading per item.
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps({
  items: {
    type: Array,
    required: true, // Array of { id: string, label: string }
  },
  modelValue: {
    type: String,
    required: true,
  },
});

const emit = defineEmits(["update:modelValue"]);

const barEl = ref(null);
const tabEls = ref(new Map());
const underline = ref({ left: 0, width: 0, ready: false });

function setTabEl(id, el) {
  if (el) tabEls.value.set(id, el);
  else tabEls.value.delete(id);
}

function placeUnderline() {
  const bar = barEl.value;
  const el = tabEls.value.get(props.modelValue);
  if (!bar || !el) {
    underline.value = { left: 0, width: 0, ready: false };
    return;
  }
  underline.value = {
    left: el.offsetLeft,
    width: el.offsetWidth,
    ready: true,
  };
}

watch(
  () => [props.modelValue, props.items.map((i) => i.label).join(" ")],
  () => nextTick(placeUnderline),
);

let resizeObserver;
onMounted(() => {
  placeUnderline();
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => placeUnderline());
    if (barEl.value) resizeObserver.observe(barEl.value);
  }
});
onBeforeUnmount(() => resizeObserver?.disconnect());
</script>

<template>
  <div ref="barEl" class="mac-tabbar">
    <div class="mac-tabbar-inner">
      <button
        v-for="item in items"
        :key="item.id"
        :ref="(el) => setTabEl(item.id, el)"
        type="button"
        class="mac-tab"
        :class="{ 'is-active': modelValue === item.id }"
        @click="emit('update:modelValue', item.id)"
      >
        {{ item.label }}
      </button>
    </div>
    <span
      v-if="underline.ready"
      class="mac-tab-underline"
      :style="{ left: `${underline.left}px`, width: `${underline.width}px` }"
    />
  </div>
</template>
