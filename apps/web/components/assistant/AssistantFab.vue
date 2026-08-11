<script setup lang="ts">
const emit = defineEmits<{ click: [] }>();
const { t } = useI18n();

defineProps<{ active?: boolean }>();
</script>

<template>
  <button
    type="button"
    class="pointer-events-auto flex items-center gap-2 rounded-full bg-rain px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-rain/90 dark:bg-sky-600 dark:hover:bg-sky-500"
    :class="active ? 'ring-2 ring-white/80' : ''"
    :aria-label="t('assistant.open')"
    @click="emit('click')"
  >
    <span aria-hidden="true">✦</span>
    <span>{{ t("assistant.fab") }}</span>
  </button>
</template>
