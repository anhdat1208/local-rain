import type { RainVectorItem, RainVectorsResponse } from "@local-rain/shared";

export function useRainVectors() {
  const { apiFetch } = useApiClient();
  const vectors = ref<RainVectorItem[]>([]);
  const loading = ref(false);

  async function fetchRainVectors(latitude: number, longitude: number): Promise<void> {
    loading.value = true;
    try {
      const data = await apiFetch<RainVectorsResponse>("/api/rain-vectors", {
        query: { lat: latitude, lng: longitude, radius_km: 100, limit: 10 },
        timeout: 14_000,
      });
      vectors.value = data.vectors ?? [];
    } catch {
      vectors.value = [];
    } finally {
      loading.value = false;
    }
  }

  return {
    vectors,
    loading,
    fetchRainVectors,
  };
}
