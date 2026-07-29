<script setup lang="ts">
const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    loading?: boolean;
    hasRain?: boolean;
    distanceLabel?: string;
    direction?: string | null;
    motionDirection?: string | null;
    etaLabel?: string;
    speedKmh?: number;
    approaching?: boolean;
    explanation?: string;
    advice?: string;
    confidence?: number;
    rainChance?: string;
    rainChancePct?: number;
    rainIn1h?: boolean;
    rainIn2h?: boolean;
  }>(),
  {
    loading: false,
    hasRain: false,
    distanceLabel: "—",
    direction: null,
    motionDirection: null,
    etaLabel: "—",
    speedKmh: 0,
    approaching: false,
    explanation: "",
    advice: "",
    confidence: 0,
    rainChance: "none",
    rainChancePct: 0,
    rainIn1h: false,
    rainIn2h: false,
  },
);

function dirLabel(code: string | null | undefined) {
  if (!code) return "—";
  const key = `dirs.${code}`;
  const translated = t(key);
  return translated === key ? code : translated;
}

const chanceLabel = computed(() => {
  const key = `rain.chance.${props.rainChance || "none"}`;
  return t(key);
});
</script>

<template>
  <div class="rounded-2xl bg-surface-muted px-3 py-3 transition-colors dark:bg-slate-800/80">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-xs font-medium text-slate-500 dark:text-slate-300">{{ t("rain.title") }}</p>
        <div v-if="loading" class="mt-2 h-8 w-28 rounded-xl lr-skeleton" />
        <p v-else class="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
          {{ hasRain ? distanceLabel : t("rain.noneNearby") }}
        </p>
      </div>
      <div
        class="rounded-2xl px-2.5 py-1 text-xs font-semibold"
        :class="
          !hasRain
            ? 'bg-slate-200 text-slate-500'
            : approaching
              ? 'bg-warning/15 text-warning'
              : 'bg-rain/15 text-rain'
        "
      >
        <template v-if="!hasRain">{{ t("rain.clear") }}</template>
        <template v-else-if="approaching">{{ t("rain.approaching") }}</template>
        <template v-else>{{ t("rain.nearby") }}</template>
      </div>
    </div>

    <p class="mt-2 text-sm text-slate-500 dark:text-slate-300">
      <template v-if="loading"><span class="inline-flex h-4 w-56 rounded-lg lr-skeleton" /></template>
      <template v-else>{{ explanation || t("rain.noCell") }}</template>
    </p>

    <div
      v-if="!loading && advice"
      class="mt-3 rounded-2xl px-3 py-2.5 text-sm font-medium"
      :class="
        !hasRain
          ? 'bg-emerald-50 text-emerald-800'
          : approaching
            ? 'bg-amber-50 text-amber-900'
            : 'bg-sky-50 text-sky-900'
      "
    >
      <div class="flex items-center justify-between gap-2">
        <p class="text-[10px] font-semibold uppercase tracking-wide opacity-70">
          {{ t("rain.advice") }}
        </p>
        <p class="text-[10px] font-semibold tabular-nums opacity-80">
          {{ t("rain.chanceLabel") }}: {{ chanceLabel }} · {{ rainChancePct }}%
        </p>
      </div>
      <p class="mt-0.5 leading-snug">{{ advice }}</p>
      <div class="mt-2 flex items-center gap-2 text-[11px] font-semibold">
        <span class="opacity-75">{{ t("rain.forecastShort") }}</span>
        <span
          class="rounded-full px-2 py-0.5"
          :class="rainIn1h ? 'bg-white/60 text-current' : 'bg-black/10 text-current/80'"
        >
          1h: {{ rainIn1h ? t("rain.yes") : t("rain.no") }}
        </span>
        <span
          class="rounded-full px-2 py-0.5"
          :class="rainIn2h ? 'bg-white/60 text-current' : 'bg-black/10 text-current/80'"
        >
          2h: {{ rainIn2h ? t("rain.yes") : t("rain.no") }}
        </span>
      </div>
    </div>

    <div v-if="hasRain && !loading" class="mt-3 grid grid-cols-3 gap-2 text-xs">
      <div class="rounded-2xl bg-white px-2.5 py-2 dark:bg-slate-700/80">
        <p class="text-slate-500 dark:text-slate-300">{{ t("rain.direction") }}</p>
        <p class="mt-1 font-semibold text-slate-900 dark:text-slate-100">{{ dirLabel(direction) }}</p>
      </div>
      <div class="rounded-2xl bg-white px-2.5 py-2 dark:bg-slate-700/80">
        <p class="text-slate-500 dark:text-slate-300">{{ t("rain.eta") }}</p>
        <p class="mt-1 font-semibold text-slate-900 dark:text-slate-100">{{ etaLabel }}</p>
      </div>
      <div class="rounded-2xl bg-white px-2.5 py-2 dark:bg-slate-700/80">
        <p class="text-slate-500 dark:text-slate-300">{{ t("rain.motion") }}</p>
        <p class="mt-1 font-semibold text-slate-900 dark:text-slate-100">
          {{ dirLabel(motionDirection) }}
          <span v-if="speedKmh > 0" class="font-normal text-slate-500 dark:text-slate-300">
            · {{ speedKmh.toFixed(0) }} km/h
          </span>
        </p>
      </div>
    </div>

    <div
      v-if="hasRain && !loading"
      class="mt-3 flex items-center justify-between text-xs text-slate-500 dark:text-slate-300"
    >
      <span>{{ t("rain.confidence") }}</span>
      <span class="font-medium tabular-nums text-slate-700 dark:text-slate-100">{{ confidence }}%</span>
    </div>
  </div>
</template>
