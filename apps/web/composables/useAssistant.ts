import type {
  AssistantChatMessage,
  AssistantHighlightAction,
  AssistantSSEEvent,
  AssistantSessionContext,
  AssistantWeatherFacts,
} from "@local-rain/shared";

export type { AssistantChatMessage, AssistantSessionContext, AssistantWeatherFacts };

export interface SendAssistantOptions {
  context: AssistantSessionContext;
  onStatus?: (message: string) => void;
  onDelta?: (chunk: string) => void;
  onFacts?: (facts: AssistantWeatherFacts) => void;
  onAction?: (action: AssistantHighlightAction) => void;
}

function parseSseEvents(buffer: string): { events: AssistantSSEEvent[]; rest: string } {
  const events: AssistantSSEEvent[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const part of parts) {
    const line = part
      .split("\n")
      .find((l) => l.startsWith("data: "));
    if (!line) continue;
    try {
      events.push(JSON.parse(line.slice(6)) as AssistantSSEEvent);
    } catch {
      // skip malformed chunk
    }
  }
  return { events, rest };
}

export function useAssistant() {
  const config = useRuntimeConfig();
  const apiBase = computed(() => String(config.public.apiBase || "").replace(/\/$/, ""));

  const open = useState("lr-assistant-open", () => false);
  const sending = useState("lr-assistant-sending", () => false);
  const messages = useState<AssistantChatMessage[]>("lr-assistant-messages", () => []);
  const lastError = useState<string | null>("lr-assistant-error", () => null);
  let abortController: AbortController | null = null;

  function toggle() {
    open.value = !open.value;
  }

  function clearConversation() {
    abortController?.abort();
    abortController = null;
    messages.value = [];
    lastError.value = null;
    sending.value = false;
  }

  function cancel() {
    abortController?.abort();
    abortController = null;
    sending.value = false;
  }

  async function sendMessage(text: string, options: SendAssistantOptions) {
    const trimmed = text.trim();
    if (!trimmed || sending.value) return;

    lastError.value = null;
    sending.value = true;

    const history = messages.value
      .filter((m) => m.content.trim())
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));

    const userMsg: AssistantChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
    };
    messages.value.push(userMsg);

    const assistantId = crypto.randomUUID();
    const assistantMsg = reactive<AssistantChatMessage>({
      id: assistantId,
      role: "assistant",
      content: "",
      status: undefined,
    });
    messages.value.push(assistantMsg);

    abortController = new AbortController();

    try {
      const url = `${apiBase.value}/api/assistant/chat`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({
          message: trimmed,
          history,
          context: options.context,
        }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSseEvents(buffer);
        buffer = parsed.rest;

        for (const event of parsed.events) {
          if (event.type === "status" && event.message) {
            assistantMsg.status = event.message;
            options.onStatus?.(event.message);
          } else if (event.type === "text_delta" && event.content) {
            assistantMsg.status = undefined;
            assistantMsg.content += event.content;
            options.onDelta?.(event.content);
          } else if (event.type === "weather_facts" && event.facts) {
            assistantMsg.facts = event.facts;
            options.onFacts?.(event.facts);
          } else if (event.type === "action" && event.action) {
            options.onAction?.(event.action);
          } else if (event.type === "error") {
            assistantMsg.status = undefined;
            assistantMsg.error = event.message || event.code || "error";
            lastError.value = assistantMsg.error;
          }
        }
      }

      if (!assistantMsg.content && !assistantMsg.error) {
        assistantMsg.error =
          options.context.lang === "vi"
            ? "Không nhận được phản hồi."
            : "No response received.";
        lastError.value = assistantMsg.error;
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        assistantMsg.status = undefined;
        if (!assistantMsg.content) {
          messages.value = messages.value.filter((m) => m.id !== assistantId);
        }
        return;
      }
      const msg =
        options.context.lang === "vi"
          ? "Không gửi được câu hỏi. Thử lại nhé."
          : "Could not send your question. Please retry.";
      assistantMsg.error = msg;
      lastError.value = msg;
    } finally {
      sending.value = false;
      abortController = null;
      assistantMsg.status = undefined;
    }
  }

  return {
    open,
    sending,
    messages,
    lastError,
    toggle,
    clearConversation,
    cancel,
    sendMessage,
  };
}
