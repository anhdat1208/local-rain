<script setup lang="ts">
import type { AssistantWeatherFacts } from "@local-rain/shared";

const props = defineProps<{
  facts: AssistantWeatherFacts;
}>();

const { t } = useI18n();

function formatDistance(m: number | null | undefined) {
  if (m == null || m < 0) return "—";
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(1)} km`;
}

function dirLabel(dir: string | null | undefined) {
  if (!dir) return "—";
  const key = `dirs.${dir}`;
  const translated = t(key);
  return translated === key ? dir : translated;
}

function trendLabel(trend: string | null | undefined) {
  if (!trend) return null;
  const key = `assistant.trend.${trend}`;
  const translated = t(key);
  return translated === key ? trend : translated;
}
</script>

<template>
  <div
    class="mt-2 rounded-xl border border-rain/20 bg-rain/5 px-3 py-2 text-xs dark:border-sky-500/30 dark:bg-sky-950/40"
  >
    <p class="mb-1.5 font-semibold text-rain dark:text-sky-300">{{ t("assistant.factsTitle") }}</p>
    <dl class="grid grid-cols-2 gap-x-3 gap-y-1 text-slate-700 dark:text-slate-200">
      <template v-if="props.facts.distanceM != null">
        <dt class="text-slate-500 dark:text-slate-400">{{ t("rain.direction") }}</dt>
        <dd>{{ dirLabel(props.facts.direction) }}</dd>
        <dt class="text-slate-500 dark:text-slate-400">{{ t("assistant.distance") }}</dt>
        <dd>{{ formatDistance(props.facts.distanceM) }}</dd>
      </template>
      <template v-if="props.facts.motionDirection">
        <dt class="text-slate-500 dark:text-slate-400">{{ t("rain.motion") }}</dt>
        <dd>{{ dirLabel(props.facts.motionDirection) }}</dd>
      </template>
      <template v-if="props.facts.speedKmh != null && props.facts.speedKmh > 0">
        <dt class="text-slate-500 dark:text-slate-400">{{ t("assistant.speed") }}</dt>
        <dd>{{ Math.round(props.facts.speedKmh) }} km/h</dd>
      </template>
      <template v-if="props.facts.etaMinutes != null && props.facts.etaMinutes > 0">
        <dt class="text-slate-500 dark:text-slate-400">{{ t("rain.eta") }}</dt>
        <dd>{{ t("rain.etaMinutes", { n: props.facts.etaMinutes }) }}</dd>
      </template>
      <template v-if="trendLabel(props.facts.trend)">
        <dt class="text-slate-500 dark:text-slate-400">{{ t("assistant.trend") }}</dt>
        <dd>{{ trendLabel(props.facts.trend) }}</dd>
      </template>
      <template v-if="props.facts.confidence != null">
        <dt class="text-slate-500 dark:text-slate-400">{{ t("rain.confidence") }}</dt>
        <dd>{{ props.facts.confidence }}%</dd>
      </template>
    </dl>
  </div>
</template>
