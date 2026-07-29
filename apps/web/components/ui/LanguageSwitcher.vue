<script setup lang="ts">
const { locale, locales, setLocale, t } = useI18n();

const options = computed(() =>
  (locales.value as Array<{ code: string; name?: string }>).map((item) => item.code),
);

async function select(code: string) {
  if (code === locale.value) return;
  await setLocale(code);
}
</script>

<template>
  <div
    class="pointer-events-auto flex overflow-hidden rounded-2xl bg-white/95 text-xs font-semibold shadow-soft backdrop-blur transition-colors dark:bg-slate-900/90"
    role="group"
    :aria-label="t('a11y.language')"
  >
    <button
      v-for="code in options"
      :key="code"
      type="button"
      class="px-2.5 py-2 transition"
      :class="
        code === locale
          ? 'bg-rain text-white'
          : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'
      "
      @click="select(code)"
    >
      {{ t(`lang.${code}`) }}
    </button>
  </div>
</template>
