<script setup lang="ts">
const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    loading?: boolean;
    disabled?: boolean;
  }>(),
  {
    loading: false,
    disabled: false,
  },
);

const emit = defineEmits<{
  click: [];
}>();

function onClick() {
  if (props.disabled || props.loading) return;
  emit("click");
}
</script>

<template>
  <button
    type="button"
    class="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-slate-800 shadow-soft transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
    :disabled="disabled || loading"
    :aria-label="t('a11y.locate')"
    @click="onClick"
  >
    <span v-if="loading" class="h-5 w-5 animate-spin rounded-full border-2 border-rain border-t-transparent" />
    <svg
      v-else
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      class="h-5 w-5 text-rain"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="3" />
      <path stroke-linecap="round" d="M12 2v3M12 19v3M2 12h3M19 12h3" />
      <circle cx="12" cy="12" r="8" />
    </svg>
  </button>
</template>
