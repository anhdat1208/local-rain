<script setup lang="ts">
const { t } = useI18n();

const isDark = useDark({
  storageKey: "local_rain_theme",
  valueDark: "dark",
  valueLight: "light",
});

const toggleTheme = useToggle(isDark);
</script>

<template>
  <button
    type="button"
    class="pointer-events-auto flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-200/80 bg-white/95 text-slate-700 shadow-soft backdrop-blur transition hover:-translate-y-0.5 dark:border-slate-700 dark:bg-slate-900/90 dark:text-slate-100"
    :aria-label="t('a11y.theme')"
    @click="toggleTheme()"
  >
    <svg
      v-if="isDark"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
      class="h-4 w-4"
      aria-hidden="true"
    >
      <path d="M12 18a6 6 0 110-12 6 6 0 010 12zm0 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zm0-22a1 1 0 011-1v1a1 1 0 11-2 0V0a1 1 0 011-1zm12 12a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM2 12a1 1 0 01-1 1H0a1 1 0 110-2h1a1 1 0 011 1zm17.66 8.66a1 1 0 01-1.42 0l-.7-.7a1 1 0 111.41-1.42l.71.71a1 1 0 010 1.41zM6.05 5.05a1 1 0 01-1.41 0l-.71-.71A1 1 0 115.34 2.93l.71.71a1 1 0 010 1.41zm13.61-2.12a1 1 0 010 1.41l-.71.71a1 1 0 01-1.41-1.41l.7-.71a1 1 0 011.42 0zM6.05 18.95a1 1 0 010 1.41l-.71.7a1 1 0 11-1.41-1.41l.71-.71a1 1 0 011.41 0z" />
    </svg>
    <svg
      v-else
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
      class="h-4 w-4"
      aria-hidden="true"
    >
      <path d="M21.75 15.5A9.75 9.75 0 1111.5 2.25a.75.75 0 01.67 1.1 7.5 7.5 0 009.58 9.58.75.75 0 011.1.67z" />
    </svg>
  </button>
</template>
