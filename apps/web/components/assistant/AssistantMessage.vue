<script setup lang="ts">
import type { AssistantChatMessage } from "@local-rain/shared";

defineProps<{
  message: AssistantChatMessage;
}>();
</script>

<template>
  <div
    class="flex"
    :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
  >
    <div
      class="max-w-[88%] rounded-2xl px-3 py-2 text-sm leading-relaxed shadow-soft"
      :class="
        message.role === 'user'
          ? 'bg-rain text-white'
          : 'bg-white text-slate-800 dark:bg-slate-800 dark:text-slate-100'
      "
    >
      <p v-if="message.status" class="animate-pulse text-xs opacity-80">
        {{ message.status }}
      </p>
      <p v-else-if="message.error" class="text-red-600 dark:text-red-300">
        {{ message.error }}
      </p>
      <p v-else class="whitespace-pre-wrap">{{ message.content }}</p>
      <WeatherFactsCard v-if="message.facts && message.role === 'assistant'" :facts="message.facts" />
    </div>
  </div>
</template>
