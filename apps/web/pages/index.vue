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

const { store, requestLocation, setManualLocation, seedLastKnownCoords, fallbackCoords } =
  useUserLocation();
const { store: radarStore, fetchRadar } = useRadar();
const { store: cloudsStore, fetchClouds } = useClouds();
const { store: nearestStore, fetchNearestRain } = useNearestRain();
const { vectors: rainVectors, fetchRainVectors } = useRainVectors();
const { open: assistantOpen, toggle: toggleAssistant } = useAssistant();
const assistantHighlight = ref<{ latitude: number; longitude: number } | null>(null);
const RADAR_REFRESH_MS = 2 * 60 * 1000;
const CLOUD_REFRESH_MS = 5 * 60 * 1000;
const NEAREST_REFRESH_MS = 60 * 1000;
let radarTimer: ReturnType<typeof setInterval> | null = null;
let cloudTimer: ReturnType<typeof setInterval> | null = null;
let nearestTimer: ReturnType<typeof setInterval> | null = null;
let nearestInFlight = false;
let visibilityHandler: (() => void) | null = null;

const mapLatitude = computed(() => store.latitude ?? fallbackCoords.latitude);
const mapLongitude = computed(() => store.longitude ?? fallbackCoords.longitude);
const displayRainLatitude = computed(
  () => assistantHighlight.value?.latitude ?? nearestStore.rainLatitude,
);
const displayRainLongitude = computed(
  () => assistantHighlight.value?.longitude ?? nearestStore.rainLongitude,
);
const radarTileUrl = computed(() =>
  cloudsStore.mapMode ? null : radarStore.activeFrame?.tileUrlTemplate ?? null,
);
// Street map skips cloud tiles (bandwidth); satellite mode still uses the template
const cloudTileUrl = computed(() =>
  cloudsStore.mapMode ? cloudsStore.tileUrlTemplate : null,
);

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
  // RainCard already shows explanation — keep sheet subtitle free of that copy
  if (nearestStore.hasRain) return "";
  if (store.source === "manual") return t("sheet.pinned");
  if (radarStore.error) return radarStore.error;
  if (nearestStore.error) return nearestStore.error;
  if (store.error) return store.error;
  if (radarStore.loading) return t("sheet.loadingRadar");
  return t("sheet.liveRadar");
});

async function refreshNearestRain(opts?: { includeVectors?: boolean }) {
  if (nearestInFlight) return;
  nearestInFlight = true;
  const lat = store.latitude ?? fallbackCoords.latitude;
  const lng = store.longitude ?? fallbackCoords.longitude;
  const includeVectors = opts?.includeVectors !== false;
  try {
    // Card first — vectors are decorative and share BE motion work
    await fetchNearestRain(lat, lng);
    if (includeVectors) {
      void fetchRainVectors(lat, lng);
    }
  } finally {
    nearestInFlight = false;
  }
}

async function refreshCriticalWeather() {
  await Promise.all([fetchRadar(), refreshNearestRain({ includeVectors: true })]);
}

async function locateAndCenter() {
  pickMode.value = false;
  if (cloudsStore.mapMode) {
    cloudsStore.exitMapMode();
  }
  followUser.value = true;
  const prevLat = store.latitude;
  const prevLng = store.longitude;
  seedLastKnownCoords();
  void refreshNearestRain();
  await requestLocation();
  const lat = store.latitude;
  const lng = store.longitude;
  if (
    lat != null &&
    lng != null &&
    (prevLat == null ||
      prevLng == null ||
      Math.abs(lat - prevLat) > 0.002 ||
      Math.abs(lng - prevLng) > 0.002)
  ) {
    await refreshNearestRain();
  }
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

function onAssistantHighlight(lat: number, lng: number) {
  assistantHighlight.value = { latitude: lat, longitude: lng };
  nextTick(() => {
    mapRef.value?.flyToStreetView(lat, lng, 11);
  });
}

function onAssistantClose() {
  toggleAssistant();
  assistantHighlight.value = null;
}

function buildAssistantContext() {
  const lang = locale.value === "en" ? "en" : "vi";
  const ctx: import("@local-rain/shared").AssistantSessionContext = {
    latitude: mapLatitude.value,
    longitude: mapLongitude.value,
    lang,
    radarTimestamp: nearestStore.radarTimestamp,
  };
  if (nearestStore.rainLatitude != null && nearestStore.rainLongitude != null) {
    ctx.selectedCell = {
      latitude: nearestStore.rainLatitude,
      longitude: nearestStore.rainLongitude,
    };
  }
  return ctx;
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

function clearRealtimeRefresh() {
  if (radarTimer) clearInterval(radarTimer);
  if (cloudTimer) clearInterval(cloudTimer);
  if (nearestTimer) clearInterval(nearestTimer);
  radarTimer = null;
  cloudTimer = null;
  nearestTimer = null;
}

function startRealtimeRefresh() {
  clearRealtimeRefresh();

  radarTimer = setInterval(() => {
    void fetchRadar();
  }, RADAR_REFRESH_MS);
  cloudTimer = setInterval(() => {
    void fetchClouds();
  }, CLOUD_REFRESH_MS);
  nearestTimer = setInterval(() => {
    void refreshNearestRain();
  }, NEAREST_REFRESH_MS);
}

function onVisibilityChange() {
  if (document.hidden) {
    clearRealtimeRefresh();
    return;
  }
  void refreshCriticalWeather();
  void fetchClouds();
  startRealtimeRefresh();
}

onMounted(() => {
  // Show loading immediately so the card doesn't flash "dry/clear"
  nearestStore.setLoading(true);
  // Seed coords BEFORE any weather kickoff (avoids HCMC fallback race)
  seedLastKnownCoords();

  // Critical path: radar + nearest. Clouds/metadata warm in background.
  void refreshCriticalWeather().then(() => startRealtimeRefresh());
  void fetchClouds();

  visibilityHandler = onVisibilityChange;
  document.addEventListener("visibilitychange", visibilityHandler);

  void (async () => {
    const prevLat = store.latitude;
    const prevLng = store.longitude;
    await requestLocation();
    // Refetch once if GPS moved meaningfully from the seed coords
    const lat = store.latitude;
    const lng = store.longitude;
    if (
      lat != null &&
      lng != null &&
      (prevLat == null ||
        prevLng == null ||
        Math.abs(lat - prevLat) > 0.002 ||
        Math.abs(lng - prevLng) > 0.002)
    ) {
      await refreshNearestRain();
    }
  })();
});

onBeforeUnmount(() => {
  clearRealtimeRefresh();
  if (visibilityHandler) {
    document.removeEventListener("visibilitychange", visibilityHandler);
    visibilityHandler = null;
  }
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
        :rain-latitude="cloudsStore.mapMode ? null : displayRainLatitude"
        :rain-longitude="cloudsStore.mapMode ? null : displayRainLongitude"
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
      class="pointer-events-auto absolute right-3 z-30 flex flex-col items-end gap-2"
      style="bottom: calc(min(26rem, 46vh) + env(safe-area-inset-bottom) + 1rem)"
    >
      <AssistantFab :active="assistantOpen" @click="toggleAssistant" />
      <PickLocationButton
        :active="pickMode"
        :disabled="cloudsStore.mapMode"
        @click="togglePickMode"
      />
      <CurrentLocationButton :loading="store.loading" @click="locateAndCenter" />
    </div>

    <BottomSheet :title="store.label" :subtitle="sheetSubtitle">
      <div v-if="assistantOpen" class="h-[min(52vh,420px)]">
        <AssistantChat
          :build-context="buildAssistantContext"
          @highlight="onAssistantHighlight"
          @close="onAssistantClose"
          @clear="assistantHighlight = null"
        />
      </div>
      <div v-else class="space-y-3">
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
          :sky-state="nearestStore.skyState"
          :cloud-cover-pct="nearestStore.cloudCoverPct"
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
