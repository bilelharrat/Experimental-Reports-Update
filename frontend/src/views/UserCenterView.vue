<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
onMounted(() => {
  router.replace({ name: "settings" });
});
</script>

<template>
  <div class="px-8 py-10 text-callout text-ink-muted">Settings</div>
</template>
