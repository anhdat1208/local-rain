<script setup lang="ts">
const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    active?: boolean;
    disabled?: boolean;
  }>(),
  {
    active: false,
    disabled: false,
  },
);

const emit = defineEmits<{
  click: [];
}>();

function onClick() {
  if (props.disabled) return;
  emit("click");
}
</script>

<template>
  <button
    type="button"
    class="flex h-12 w-12 items-center justify-center rounded-2xl shadow-soft transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
    :class="active ? 'bg-rain text-white' : 'bg-white text-slate-800'"
    :aria-pressed="active"
    :disabled="disabled"
    :aria-label="t('a11y.pickLocation')"
    @click="onClick"
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      class="h-5 w-5"
      :class="active ? 'text-white' : 'text-rain'"
      aria-hidden="true"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M12 21s7-5.2 7-11a7 7 0 10-14 0c0 5.8 7 11 7 11z"
      />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  </button>
</template>
