# Design: Radar overlay filter + i18n (EN/VI)

## Goals

1. Map radar overlay matches nearest-rain detection (hide drizzle / weak returns).
2. Full-app language switch EN/VI (approach A), default Vietnamese.

## 1. Radar overlay filter

- Add API tile proxy: `GET /api/radar/tiles/{unix_time}/{z}/{x}/{y}.png`
- Fetch RainViewer tile (unsmoothed Universal Blue), zero-out pixels with dBZ &lt; 30 (shared with nearest-rain).
- Redis-cache filtered tiles (~2–5 min).
- `GET /api/radar` returns `tileUrlTemplate` pointing at this proxy (via `PUBLIC_API_BASE`), same pattern as clouds.
- Shared module: `radar_dbz.py` (palette, `MIN_DBZ`, `pixel_dbz`, `filter_tile`).

## 2. i18n (after overlay)

- Web: `@nuxtjs/i18n` with locales `vi` (default) + `en`, persist preference.
- UI switcher on map chrome.
- Translate all user-facing web strings.
- API advice: `GET /api/nearest-rain?lang=vi|en` (fallback `vi`); `advice_rules` bilingual.
- Direction labels / distance copy follow `lang`.

## Out of scope

- Extra languages, RTL, per-province copy.
- Changing RainViewer color scheme ID.
