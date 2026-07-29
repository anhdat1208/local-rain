/** Free ngrok returns an interstitial HTML page for browser UAs unless skipped. */
export function needsNgrokBypass(url: string): boolean {
  return /ngrok(-free)?\.(app|dev|io)/i.test(url);
}

export function withNgrokHeaders(
  url: string,
  headers: HeadersInit | undefined = undefined,
): Record<string, string> {
  const merged: Record<string, string> = {};
  if (headers) {
    new Headers(headers).forEach((value, key) => {
      merged[key] = value;
    });
  }
  if (needsNgrokBypass(url)) {
    merged["ngrok-skip-browser-warning"] = "true";
  }
  return merged;
}
