import type { CloudsResponse } from "@local-rain/shared";

import { useCloudsStore } from "~/stores/clouds";

export function useClouds() {
  const store = useCloudsStore();
  const { t } = useI18n();
  const { apiFetch } = useApiClient();
  const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  async function fetchClouds(): Promise<void> {
    store.setLoading(true);
    store.setError(null);
    let lastError: unknown = null;
    const maxAttempts = 3;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const data = await apiFetch<CloudsResponse>("/api/clouds", {
          timeout: 10_000,
        });
        store.setPayload(data);
        return;
      } catch (error) {
        lastError = error;
        if (attempt < maxAttempts) {
          await delay(350 * attempt);
        }
      }
    }

    // Keep previous usable cloud payload if it exists; only surface the error state.
    if (store.tileUrlTemplate) {
      store.setLoading(false);
    } else {
      store.setError(t("errors.clouds"));
    }
    console.error("clouds fetch failed after retries", lastError);
  }

  return {
    store,
    fetchClouds,
  };
}
