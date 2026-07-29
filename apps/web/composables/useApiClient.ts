export function useApiClient() {
  const config = useRuntimeConfig();
  const apiBase = computed(() => String(config.public.apiBase || "").replace(/\/$/, ""));

  function apiFetch<T>(path: string, opts?: Record<string, unknown>): Promise<T> {
    const url = path.startsWith("http") ? path : `${apiBase.value}${path}`;
    return $fetch<T>(url, {
      ...opts,
      headers: withNgrokHeaders(url, opts?.headers as HeadersInit | undefined),
    });
  }

  return { apiBase, apiFetch };
}
