<script setup lang="ts">
const { t, locale } = useI18n();

const props = withDefaults(
  defineProps<{
    mapMode?: boolean;
    dayMode?: boolean;
    loading?: boolean;
    timestamp?: string | null;
  }>(),
  {
    mapMode: false,
    dayMode: false,
    loading: false,
    timestamp: null,
  },
);

const emit = defineEmits<{
  "toggle-map-mode": [];
}>();

const timeLabel = computed(() => {
  if (!props.timestamp) return t("clouds.satellite");
  const date = new Date(props.timestamp);
  if (Number.isNaN(date.getTime())) return t("clouds.satellite");
  return date.toLocaleString(locale.value === "vi" ? "vi-VN" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
});
</script>

<template>
  <div
    class="rounded-2xl px-3 py-3 transition-all duration-300"
    :class="mapMode ? 'bg-slate-950 text-slate-100' : 'bg-surface-muted text-slate-800'"
  >
    <div class="flex items-center gap-2">
      <button
        type="button"
        class="flex h-10 shrink-0 items-center gap-2 rounded-2xl px-3 text-xs font-semibold transition active:scale-95"
        :class="
          mapMode
            ? 'bg-white text-slate-900'
            : 'bg-slate-900 text-white'
        "
        :disabled="loading"
        @click="emit('toggle-map-mode')"
      >
        {{ t("clouds.satellite") }}
      </button>
      <div v-if="loading" class="ml-auto h-4 w-20 rounded-lg lr-skeleton" />
      <p
        v-else
        class="ml-auto truncate text-xs font-semibold tabular-nums"
        :class="mapMode ? 'text-slate-300' : 'text-slate-600'"
      >
        {{ timeLabel }}
      </p>
    </div>

    <div
      v-if="mapMode"
      class="mt-3 rounded-2xl border border-white/10 bg-black/40 px-3 py-2"
    >
      <p class="text-xs font-medium text-slate-100">
        {{ dayMode ? t("clouds.dayTitle") : t("clouds.nightTitle") }}
      </p>
      <p class="mt-1 text-xs leading-relaxed text-slate-400">
        {{ dayMode ? t("clouds.dayHint") : t("clouds.nightHint") }}
      </p>
      <div class="mt-2 flex items-center gap-2">
        <span class="text-[10px] uppercase tracking-wide text-slate-500">
          {{ t("clouds.clear") }}
        </span>
        <div
          class="h-2 flex-1 rounded-full"
          :style="
            dayMode
              ? 'background: linear-gradient(to right, #0b4f78, #3f6b45, #f8fafc)'
              : 'background: linear-gradient(to right, #000000, #6b7280, #ffffff)'
          "
        />
        <span class="text-[10px] uppercase tracking-wide text-slate-500">
          {{ t("clouds.thick") }}
        </span>
      </div>
    </div>
  </div>
</template>
