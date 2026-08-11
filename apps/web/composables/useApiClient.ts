export function useApiClient() {
  const config = useRuntimeConfig();
  const apiBase = computed(() => String(config.public.apiBase || "").replace(/\/$/, ""));

  function apiFetch<T>(path: string, opts?: Record<string, unknown>): Promise<T> {
    const url = path.startsWith("http") ? path : `${apiBase.value}${path}`;
    const timeout = typeof opts?.timeout === "number" ? opts.timeout : 10_000;
    return $fetch<T>(url, {
      ...opts,
      timeout,
      headers: withNgrokHeaders(url, opts?.headers as HeadersInit | undefined),
    });
  }

  return { apiBase, apiFetch };
}
