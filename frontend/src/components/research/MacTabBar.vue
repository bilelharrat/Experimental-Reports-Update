<script setup>
defineProps({
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
</script>

<template>
  <div class="relative w-full border-b border-white/[0.08] overflow-x-auto no-scrollbar">
    <div class="flex items-center gap-6 min-w-max px-0.5">
      <button
        v-for="item in items"
        :key="item.id"
        type="button"
        class="group relative flex flex-col items-center pb-2.5 pt-1 transition-colors outline-none cursor-pointer"
        @click="emit('update:modelValue', item.id)"
      >
        <span
          class="text-[13px] leading-tight transition-colors whitespace-nowrap select-none"
          :class="
            modelValue === item.id
              ? 'font-semibold text-white'
              : 'font-normal text-neutral-400 group-hover:text-neutral-200'
          "
        >
          {{ item.label }}
        </span>
        <span
          class="absolute bottom-0 left-0 right-0 h-[2px] rounded-full transition-all duration-150"
          :class="modelValue === item.id ? 'bg-[#0a84ff] opacity-100 scale-x-100' : 'bg-transparent opacity-0 scale-x-0'"
        />
      </button>
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
