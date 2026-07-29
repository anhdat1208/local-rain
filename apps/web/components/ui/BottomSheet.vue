<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
  }>(),
  {
    title: "",
    subtitle: "",
  },
);

const { t } = useI18n();

const shellRef = ref<HTMLElement | null>(null);
const scrollRef = ref<HTMLElement | null>(null);
const measureRef = ref<HTMLElement | null>(null);
const peekRef = ref<HTMLElement | null>(null);

const contentHeight = ref(320);
const peekHeight = ref(88);
const viewportHeight = ref(800);
const height = ref(280);
const dragging = ref(false);
/** 0 = peek, 1 = mid (~42vh), 2 = max (~78vh) */
const snapIndex = ref(1);

const midHeight = computed(() => {
  const target = Math.round(viewportHeight.value * 0.42);
  return Math.min(contentHeight.value, Math.max(peekHeight.value + 120, target));
});

const maxHeight = computed(() => {
  const cap = Math.round(viewportHeight.value * 0.78);
  return Math.min(contentHeight.value, Math.max(midHeight.value, cap));
});

const snaps = computed(() => [peekHeight.value, midHeight.value, maxHeight.value]);

const collapsed = computed(() => snapIndex.value === 0);

let startY = 0;
let startHeight = 0;
let didDrag = false;

function readViewport() {
  if (!import.meta.client) return;
  viewportHeight.value = window.innerHeight || 800;
}

function applySnap(index: number) {
  const next = Math.max(0, Math.min(2, index));
  snapIndex.value = next;
  height.value = snaps.value[next] ?? peekHeight.value;
}

function nearestSnapIndex(h: number): number {
  const list = snaps.value;
  let best = 0;
  let bestDist = Number.POSITIVE_INFINITY;
  for (let i = 0; i < list.length; i += 1) {
    const dist = Math.abs(list[i]! - h);
    if (dist < bestDist) {
      bestDist = dist;
      best = i;
    }
  }
  return best;
}

function measure() {
  const measureEl = measureRef.value;
  const peek = peekRef.value;
  if (!measureEl) return;

  readViewport();
  const nextContent = Math.ceil(measureEl.offsetHeight);
  const nextPeek = Math.max(72, Math.ceil(peek?.offsetHeight ?? 88));
  if (nextContent <= 0) return;

  contentHeight.value = nextContent;
  peekHeight.value = nextPeek;

  if (!dragging.value) {
    applySnap(snapIndex.value);
  }
}

function onPointerDown(event: PointerEvent) {
  const target = event.currentTarget as HTMLElement;
  target.setPointerCapture(event.pointerId);
  measure();
  dragging.value = true;
  didDrag = false;
  startY = event.clientY;
  startHeight = height.value;
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) return;
  const delta = event.clientY - startY;
  if (Math.abs(delta) > 6) didDrag = true;
  const next = startHeight - delta;
  height.value = Math.min(maxHeight.value, Math.max(peekHeight.value, next));
}

function onPointerUp() {
  if (!dragging.value) return;
  dragging.value = false;
  if (!didDrag) return;
  applySnap(nearestSnapIndex(height.value));
}

function onHandleClick() {
  if (didDrag) {
    didDrag = false;
    return;
  }
  measure();
  applySnap((snapIndex.value + 1) % 3);
}

const shellStyle = computed(() => ({
  height: `${height.value}px`,
  transition: dragging.value
    ? "none"
    : "height 260ms cubic-bezier(0.22, 1, 0.36, 1)",
}));

const bodyStyle = computed(() => {
  const span = Math.max(1, midHeight.value - peekHeight.value);
  const progress = Math.min(1, Math.max(0, (height.value - peekHeight.value) / span));
  return {
    opacity: progress,
    pointerEvents: progress < 0.12 ? ("none" as const) : ("auto" as const),
  };
});

onMounted(() => {
  readViewport();
  window.addEventListener("resize", measure, { passive: true });
  nextTick(() => {
    measure();
    applySnap(1);
  });
});

onBeforeUnmount(() => {
  if (!import.meta.client) return;
  window.removeEventListener("resize", measure);
});

useResizeObserver(measureRef, () => {
  if (dragging.value) return;
  measure();
});
</script>

<template>
  <section
    class="pointer-events-auto absolute inset-x-0 bottom-0 z-20 mx-auto w-full max-w-xl px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
  >
    <div
      ref="shellRef"
      class="overflow-hidden rounded-2xl bg-white/95 shadow-soft backdrop-blur-md transition-colors duration-300 dark:bg-slate-900/90 dark:shadow-[0_12px_36px_rgba(2,6,23,0.5)]"
      :style="shellStyle"
      :aria-expanded="!collapsed"
    >
      <div ref="scrollRef" class="h-full overflow-y-auto overscroll-contain">
        <div ref="measureRef">
          <div ref="peekRef">
            <button
              type="button"
              class="flex w-full cursor-grab touch-none flex-col items-center px-4 pt-3 pb-1 active:cursor-grabbing"
              :aria-label="t('sheet.dragHandle')"
              @pointerdown="onPointerDown"
              @pointermove="onPointerMove"
              @pointerup="onPointerUp"
              @pointercancel="onPointerUp"
              @click="onHandleClick"
            >
              <span class="h-1.5 w-11 rounded-full bg-slate-300 dark:bg-slate-600" />
            </button>

            <header
              v-if="title"
              class="cursor-grab touch-none px-4 pb-3 active:cursor-grabbing"
              @pointerdown="onPointerDown"
              @pointermove="onPointerMove"
              @pointerup="onPointerUp"
              @pointercancel="onPointerUp"
              @click="onHandleClick"
            >
              <p class="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                {{ title }}
              </p>
            </header>
          </div>

          <div class="px-4 pb-4" :style="bodyStyle">
            <p v-if="subtitle" class="-mt-1 mb-3 text-sm text-slate-500 dark:text-slate-300">
              {{ subtitle }}
            </p>
            <slot />
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
