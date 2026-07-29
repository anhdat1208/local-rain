<script setup lang="ts">
const { t, locale } = useI18n();

const props = withDefaults(
  defineProps<{
    playing: boolean;
    loading?: boolean;
    disabled?: boolean;
    activeIndex: number;
    frameCount: number;
    timestamp: string | null;
  }>(),
  {
    loading: false,
    disabled: false,
    timestamp: null,
  },
);

const emit = defineEmits<{
  toggle: [];
  seek: [index: number];
}>();

const label = computed(() => {
  if (props.loading) return t("radar.loading");
  if (props.frameCount === 0) return t("radar.noFrames");
  if (!props.timestamp) return t("radar.title");
  const date = new Date(props.timestamp);
  if (Number.isNaN(date.getTime())) return t("radar.title");
  return date.toLocaleTimeString(locale.value === "vi" ? "vi-VN" : "en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
});

const progress = computed(() => {
  if (props.frameCount <= 1) return 0;
  return (props.activeIndex / (props.frameCount - 1)) * 100;
});

function onSeek(event: Event) {
  const target = event.target as HTMLInputElement;
  emit("seek", Number(target.value));
}
</script>

<template>
  <div class="rounded-2xl bg-surface-muted px-3 py-3 transition-colors dark:bg-slate-800/80">
    <div class="flex items-center gap-3">
      <button
        type="button"
        class="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-white text-rain shadow-sm transition active:scale-95 disabled:opacity-50 dark:bg-slate-700 dark:text-sky-300"
        :disabled="disabled || loading || frameCount === 0"
        :aria-label="playing ? t('radar.pause') : t('radar.play')"
        @click="emit('toggle')"
      >
        <svg
          v-if="!playing"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          class="h-4 w-4"
          aria-hidden="true"
        >
          <path d="M8 5.14v13.72L19 12 8 5.14z" />
        </svg>
        <svg
          v-else
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          class="h-4 w-4"
          aria-hidden="true"
        >
          <path d="M7 5h3v14H7V5zm7 0h3v14h-3V5z" />
        </svg>
      </button>

      <div class="min-w-0 flex-1">
        <div class="mb-1 flex items-center justify-between gap-2">
          <p class="text-xs font-medium text-slate-500 dark:text-slate-300">{{ t("radar.title") }}</p>
          <div v-if="loading" class="h-4 w-16 rounded-md lr-skeleton" />
          <p v-else class="truncate text-xs font-semibold tabular-nums text-slate-800 dark:text-slate-100">{{ label }}</p>
        </div>
        <input
          class="lr-range w-full"
          type="range"
          min="0"
          :max="Math.max(frameCount - 1, 0)"
          :value="activeIndex"
          :disabled="disabled || loading || frameCount === 0"
          :style="{ '--progress': `${progress}%` }"
          @input="onSeek"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.lr-range {
  appearance: none;
  height: 0.35rem;
  border-radius: 9999px;
  background: linear-gradient(
    to right,
    #0ea5e9 var(--progress, 0%),
    #cbd5e1 var(--progress, 0%)
  );
  outline: none;
}

.lr-range::-webkit-slider-thumb {
  appearance: none;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 9999px;
  background: #0ea5e9;
  border: 2px solid #fff;
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.15);
  cursor: pointer;
}

.lr-range::-moz-range-thumb {
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 9999px;
  background: #0ea5e9;
  border: 2px solid #fff;
  cursor: pointer;
}
</style>
