<script setup lang="ts">
const props = defineProps<{
  buildContext: () => import("@local-rain/shared").AssistantSessionContext;
}>();

const emit = defineEmits<{
  send: [text: string];
  clear: [];
  close: [];
  highlight: [lat: number, lng: number];
}>();

const { t } = useI18n();
const { messages, sending, lastError, sendMessage: _send, clearConversation } = useAssistant();

const input = ref("");
const scrollRef = ref<HTMLElement | null>(null);

const quickQuestions = computed(() => [
  t("assistant.quick.rainComing"),
  t("assistant.quick.nearestRain"),
  t("assistant.quick.movingToward"),
  t("assistant.quick.rainSoon"),
  t("assistant.quick.explainRadar"),
]);

async function submit(text?: string) {  const value = (text ?? input.value).trim();
  if (!value) return;
  input.value = "";
  await _send(value, {
    context: props.buildContext(),
    onAction: (action) => {
      if (action.type === "highlight_rain_cell") {
        emit("highlight", action.latitude, action.longitude);
      }
    },
  });
  await nextTick();
  scrollRef.value?.scrollTo({ top: scrollRef.value.scrollHeight, behavior: "smooth" });
}

function onClear() {
  clearConversation();
  emit("clear");
}

watch(
  () => messages.value.length,
  async () => {
    await nextTick();
    scrollRef.value?.scrollTo({ top: scrollRef.value.scrollHeight, behavior: "smooth" });
  },
);
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="mb-2 flex items-center justify-between gap-2">
      <div>
        <h2 class="text-sm font-semibold text-slate-900 dark:text-white">{{ t("assistant.title") }}</h2>
        <p class="text-xs text-slate-500 dark:text-slate-400">{{ t("assistant.subtitle") }}</p>
      </div>
      <div class="flex gap-1">
        <button
          type="button"
          class="rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
          @click="onClear"
        >
          {{ t("assistant.clear") }}
        </button>
        <button
          type="button"
          class="rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
          aria-label="Close"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>
    </div>

    <div
      ref="scrollRef"
      class="min-h-0 flex-1 space-y-2 overflow-y-auto rounded-xl bg-surface-muted/60 p-2 dark:bg-slate-900/50"
    >
      <p v-if="messages.length === 0" class="px-1 py-2 text-xs text-slate-500 dark:text-slate-400">
        {{ t("assistant.empty") }}
      </p>
      <AssistantMessage v-for="msg in messages" :key="msg.id" :message="msg" />
    </div>

    <div class="mt-2 flex flex-wrap gap-1.5">
      <button
        v-for="q in quickQuestions"
        :key="q"
        type="button"
        class="rounded-full border border-rain/25 bg-white px-2.5 py-1 text-[11px] text-rain transition hover:bg-rain/5 dark:border-sky-500/30 dark:bg-slate-800 dark:text-sky-300"
        :disabled="sending"
        @click="submit(q)"
      >
        {{ q }}
      </button>
    </div>

    <form class="mt-2 flex gap-2" @submit.prevent="submit()">
      <input
        v-model="input"
        type="text"
        class="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none ring-rain/30 focus:ring-2 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
        :placeholder="t('assistant.placeholder')"
        :disabled="sending"
        autocomplete="off"
      />
      <button
        type="submit"
        class="rounded-xl bg-rain px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-sky-600"
        :disabled="sending || !input.trim()"
      >
        {{ sending ? "…" : t("assistant.send") }}
      </button>
    </form>

    <p v-if="lastError" class="mt-1 text-[11px] text-red-500">{{ lastError }}</p>
  </div>
</template>
