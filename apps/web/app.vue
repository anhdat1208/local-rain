<script setup lang="ts">
const isDark = useDark({
  storageKey: "local_rain_theme",
  valueDark: "dark",
  valueLight: "light",
});

const themeColor = computed(() => (isDark.value ? "#0b1220" : "#f5f5f7"));

useHead(() => ({
  htmlAttrs: {
    class: isDark.value ? "dark" : "",
  },
  meta: [{ name: "theme-color", content: themeColor.value }],
}));
</script>

<template>
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>
