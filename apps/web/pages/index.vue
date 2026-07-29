<script setup lang="ts">
const { t, locale } = useI18n();

const mapRef = ref<{
  recenter: () => void;
  flyToCloudView: (lat: number, lng: number) => void;
  flyToStreetView: (lat: number, lng: number, zoom?: number) => void;
  getZoom: () => number;
} | null>(null);
const followUser = ref(true);
const pickMode = ref(false);

const { store, requestLocation, setManualLocation, fallbackCoords } = useUserLocation();
const { store: radarStore, fetchRadar } = useRadar();
const { store: cloudsStore, fetchClouds } = useClouds();
const { store: nearestStore, fetchNearestRain } = useNearestRain();
const { vectors: rainVectors, fetchRainVectors } = useRainVectors();
const RADAR_REFRESH_MS = 2 * 60 * 1000;
const CLOUD_REFRESH_MS = 5 * 60 * 1000;
const NEAREST_REFRESH_MS = 75 * 1000;
const VECTOR_REFRESH_MS = 90 * 1000;
let radarTimer: ReturnType<typeof setInterval> | null = null;
let cloudTimer: ReturnType<typeof setInterval> | null = null;
let nearestTimer: ReturnType<typeof setInterval> | null = null;
let vectorTimer: ReturnType<typeof setInterval> | null = null;

const mapLatitude = computed(() => store.latitude ?? fallbackCoords.latitude);
const mapLongitude = computed(() => store.longitude ?? fallbackCoords.longitude);
const radarTileUrl = computed(() =>
  cloudsStore.mapMode ? null : radarStore.activeFrame?.tileUrlTemplate ?? null,
);
// Keep template available even before mapMode flips to avoid style race.
const cloudTileUrl = computed(() => cloudsStore.tileUrlTemplate);

const etaLabel = computed(() => {
  if (!nearestStore.hasRain || !nearestStore.approaching || nearestStore.eta <= 0) return "—";
  return t("rain.etaMinutes", { n: nearestStore.eta });
});

const sheetSubtitle = computed(() => {
  if (cloudsStore.error) return cloudsStore.error;
  if (cloudsStore.mapMode) {
    return cloudsStore.isDayMode ? t("sheet.cloudsDay") : t("sheet.cloudsNight");
  }
  if (pickMode.value) return t("sheet.tapMap");
  if (store.loading) return t("sheet.locating");
  if (nearestStore.loading) return t("sheet.findingRain");
  if (nearestStore.hasRain) return nearestStore.explanation;
  if (store.source === "manual") return t("sheet.pinned");
  if (radarStore.error) return radarStore.error;
  if (nearestStore.error) return nearestStore.error;
  if (store.error) return store.error;
  if (radarStore.loading) return t("sheet.loadingRadar");
  return t("sheet.liveRadar");
});

async function refreshNearestRain() {
  if (store.latitude == null || store.longitude == null) return;
  await fetchNearestRain(store.latitude, store.longitude);
  await fetchRainVectors(store.latitude, store.longitude);
}

async function locateAndCenter() {
  pickMode.value = false;
  if (cloudsStore.mapMode) {
    cloudsStore.exitMapMode();
  }
  followUser.value = true;
  await requestLocation();
  await refreshNearestRain();
  await nextTick();
  mapRef.value?.recenter();
}

function togglePickMode() {
  if (cloudsStore.mapMode) return;
  pickMode.value = !pickMode.value;
  if (pickMode.value) {
    followUser.value = false;
  }
}

async function onMapClick(point: { latitude: number; longitude: number }) {
  if (!pickMode.value) return;
  followUser.value = false;
  await setManualLocation(point.latitude, point.longitude);
  pickMode.value = false;
  await refreshNearestRain();
  await nextTick();
  mapRef.value?.recenter();
}

function onUserPan() {
  followUser.value = false;
}

async function ensureCloudLayerReady() {
  if (cloudsStore.tileUrlTemplate) return true;
  try {
    await fetchClouds();
  } catch {
    // fetchClouds already updates store error; keep flow stable here.
  }
  return Boolean(cloudsStore.tileUrlTemplate);
}

async function toggleCloudMapMode() {
  try {
    const zoom = mapRef.value?.getZoom() ?? 14;
    const turningOn = !cloudsStore.mapMode;
    if (turningOn) {
      const ready = await ensureCloudLayerReady();
      if (!ready) {
        cloudsStore.setError(t("errors.clouds"));
        return;
      }
    }
    cloudsStore.toggleMapMode(zoom);
    pickMode.value = false;
    followUser.value = false;

    nextTick(() => {
      if (turningOn) {
        mapRef.value?.flyToCloudView(mapLatitude.value, mapLongitude.value);
      } else {
        mapRef.value?.flyToStreetView(
          mapLatitude.value,
          mapLongitude.value,
          cloudsStore.previousStreetZoom || 14,
        );
      }
    });
  } catch {
    cloudsStore.setError(t("errors.clouds"));
  }
}

watch(locale, async () => {
  await refreshNearestRain();
});

function startRealtimeRefresh() {
  if (radarTimer) clearInterval(radarTimer);
  if (cloudTimer) clearInterval(cloudTimer);
  if (nearestTimer) clearInterval(nearestTimer);
  if (vectorTimer) clearInterval(vectorTimer);

  radarTimer = setInterval(() => {
    void fetchRadar();
  }, RADAR_REFRESH_MS);
  cloudTimer = setInterval(() => {
    void fetchClouds();
  }, CLOUD_REFRESH_MS);
  nearestTimer = setInterval(() => {
    void refreshNearestRain();
  }, NEAREST_REFRESH_MS);
  vectorTimer = setInterval(() => {
    if (store.latitude == null || store.longitude == null) return;
    void fetchRainVectors(store.latitude, store.longitude);
  }, VECTOR_REFRESH_MS);
}

onMounted(async () => {
  await requestLocation();
  await Promise.all([fetchRadar(), fetchClouds(), refreshNearestRain()]);
  startRealtimeRefresh();
});

onBeforeUnmount(() => {
  if (radarTimer) clearInterval(radarTimer);
  if (cloudTimer) clearInterval(cloudTimer);
  if (nearestTimer) clearInterval(nearestTimer);
  if (vectorTimer) clearInterval(vectorTimer);
});
</script>

<template>
  <main
    class="relative h-dvh w-full overflow-hidden bg-surface-muted transition-colors duration-300 dark:bg-slate-950"
  >
    <ClientOnly>
      <MapView
        ref="mapRef"
        class="absolute inset-0"
        :latitude="mapLatitude"
        :longitude="mapLongitude"
        :follow-user="followUser && !cloudsStore.mapMode"
        :pick-mode="pickMode"
        :location-source="store.source"
        :radar-tile-url="radarTileUrl"
        :radar-opacity="radarStore.opacity"
        :cloud-tile-url="cloudTileUrl"
        :cloud-opacity="cloudsStore.effectiveOpacity"
        :cloud-max-zoom="cloudsStore.maxZoom"
        :cloud-map-mode="cloudsStore.mapMode"
        :cloud-day-mode="cloudsStore.isDayMode"
        :rain-vectors="cloudsStore.mapMode ? [] : rainVectors"
        :rain-latitude="cloudsStore.mapMode ? null : nearestStore.rainLatitude"
        :rain-longitude="cloudsStore.mapMode ? null : nearestStore.rainLongitude"
        @userinteract="onUserPan"
        @mapclick="onMapClick"
      />
      <template #fallback>
        <div class="absolute inset-0 flex items-center justify-center bg-surface-muted">
          <div class="h-10 w-10 animate-pulse rounded-full bg-rain/40" />
        </div>
      </template>
    </ClientOnly>

    <div
      class="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 p-3 pt-[max(0.75rem,env(safe-area-inset-top))]"
    >
      <div
        class="rounded-2xl bg-white/95 px-3 py-2 shadow-soft backdrop-blur transition-colors dark:bg-slate-900/90"
      >
        <p class="text-xs font-semibold tracking-wide text-rain dark:text-sky-300">{{ t("brand") }}</p>
      </div>

      <div class="flex items-start gap-2">
        <div
          v-if="cloudsStore.mapMode"
          class="rounded-2xl bg-black/80 px-3 py-2 text-xs font-medium text-white shadow-soft backdrop-blur"
        >
          {{
            cloudsStore.isDayMode ? t("badge.satelliteDay") : t("badge.satelliteNight")
          }}
        </div>
        <div
          v-else-if="pickMode"
          class="rounded-2xl bg-rain px-3 py-2 text-xs font-medium text-white shadow-soft"
        >
          {{ t("badge.tapToPin") }}
        </div>
        <ThemeToggle />
        <LanguageSwitcher />
      </div>
    </div>

    <div
      class="pointer-events-auto absolute right-3 z-20 flex flex-col gap-2"
      style="bottom: calc(22rem + env(safe-area-inset-bottom))"
    >
      <PickLocationButton
        :active="pickMode"
        :disabled="cloudsStore.mapMode"
        @click="togglePickMode"
      />
      <CurrentLocationButton :loading="store.loading" @click="locateAndCenter" />
    </div>

    <BottomSheet :title="store.label" :subtitle="sheetSubtitle">
      <div class="space-y-3">
        <RainCard
          v-if="!cloudsStore.mapMode"
          class="lr-fade-up"
          :loading="nearestStore.loading"
          :has-rain="nearestStore.hasRain"
          :distance-label="nearestStore.distanceLabel"
          :direction="nearestStore.direction"
          :motion-direction="nearestStore.motionDirection"
          :eta-label="etaLabel"
          :speed-kmh="nearestStore.speedKmh"
          :approaching="nearestStore.approaching"
          :explanation="nearestStore.explanation"
          :advice="nearestStore.advice"
          :confidence="nearestStore.confidence"
          :rain-chance="nearestStore.rainChance"
          :rain-chance-pct="nearestStore.rainChancePct"
          :rain-in-1h="nearestStore.rainIn1h"
          :rain-in-2h="nearestStore.rainIn2h"
          :raining-here="nearestStore.rainingHere"
          :radar-timestamp="nearestStore.radarTimestamp"
          :radar-age-minutes="nearestStore.radarAgeMinutes"
        />
        <CloudLayerControls
          class="lr-fade-up"
          :map-mode="cloudsStore.mapMode"
          :day-mode="cloudsStore.isDayMode"
          :loading="cloudsStore.loading"
          :timestamp="cloudsStore.timestamp"
          @toggle-map-mode="toggleCloudMapMode"
        />
        <RadarPlayer
          v-if="!cloudsStore.mapMode"
          class="lr-fade-up"
          :playing="radarStore.playing"
          :loading="radarStore.loading"
          :disabled="Boolean(radarStore.error)"
          :active-index="radarStore.activeIndex"
          :frame-count="radarStore.frameCount"
          :timestamp="radarStore.activeTimestamp"
          @toggle="radarStore.togglePlaying()"
          @seek="radarStore.setActiveIndex($event)"
        />
      </div>
    </BottomSheet>
  </main>
</template>
