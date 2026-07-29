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

const shellRef = ref<HTMLElement | null>(null);
const innerRef = ref<HTMLElement | null>(null);
const peekRef = ref<HTMLElement | null>(null);

const fullHeight = ref(320);
const peekHeight = ref(88);
const height = ref(320);
const dragging = ref(false);

const collapsed = computed(() => height.value <= peekHeight.value + 10);

let startY = 0;
let startHeight = 0;
let didDrag = false;

function measure() {
  const inner = innerRef.value;
  const peek = peekRef.value;
  if (!inner) return;

  const nextFull = Math.ceil(inner.scrollHeight);
  const nextPeek = Math.max(72, Math.ceil(peek?.offsetHeight ?? 88));
  if (nextFull <= 0) return;

  const wasCollapsed = height.value <= peekHeight.value + 10;
  fullHeight.value = nextFull;
  peekHeight.value = nextPeek;

  if (!dragging.value) {
    height.value = wasCollapsed ? nextPeek : nextFull;
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
  height.value = Math.min(fullHeight.value, Math.max(peekHeight.value, next));
}

function onPointerUp() {
  if (!dragging.value) return;
  dragging.value = false;
  if (!didDrag) return;

  const mid = (fullHeight.value + peekHeight.value) / 2;
  height.value = height.value < mid ? peekHeight.value : fullHeight.value;
}

function onHandleClick() {
  if (didDrag) {
    didDrag = false;
    return;
  }
  measure();
  height.value = collapsed.value ? fullHeight.value : peekHeight.value;
}

const shellStyle = computed(() => ({
  height: `${height.value}px`,
  transition: dragging.value
    ? "none"
    : "height 260ms cubic-bezier(0.22, 1, 0.36, 1)",
}));

const bodyStyle = computed(() => {
  const span = Math.max(1, fullHeight.value - peekHeight.value);
  const progress = Math.min(1, Math.max(0, (height.value - peekHeight.value) / span));
  return {
    opacity: progress,
    // Keep layout for height measure; fade only.
    pointerEvents: progress < 0.15 ? ("none" as const) : ("auto" as const),
  };
});

onMounted(() => {
  nextTick(() => measure());
});

useResizeObserver(innerRef, () => {
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
      <div ref="innerRef">
        <div ref="peekRef">
          <button
            type="button"
            class="flex w-full cursor-grab touch-none flex-col items-center px-4 pt-3 pb-1 active:cursor-grabbing"
            aria-label="Drag to collapse sheet"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointercancel="onPointerUp"
            @click="onHandleClick"
          >
            <span class="h-1 w-10 rounded-full bg-slate-300 dark:bg-slate-600" />
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
  </section>
</template>
