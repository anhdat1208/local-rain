<script setup lang="ts">
const emit = defineEmits<{ click: [] }>();
const { t } = useI18n();

defineProps<{ active?: boolean }>();
</script>

<template>
  <button
    type="button"
    class="pointer-events-auto flex max-w-[52vw] items-center gap-1.5 rounded-full bg-rain px-3 py-2 text-xs font-semibold text-white shadow-soft transition hover:bg-rain/90 sm:max-w-none sm:gap-2 sm:px-4 sm:py-2.5 sm:text-sm dark:bg-sky-600 dark:hover:bg-sky-500"
    :class="active ? 'ring-2 ring-white/80' : ''"
    :aria-label="t('assistant.open')"
    @click="emit('click')"
  >
    <span aria-hidden="true">✦</span>
    <span class="truncate sm:hidden">{{ t("assistant.fabShort") }}</span>
    <span class="hidden sm:inline">{{ t("assistant.fab") }}</span>
  </button>
</template>
