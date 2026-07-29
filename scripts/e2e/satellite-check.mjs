import { chromium } from "playwright-core";

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const APP_URL = process.env.APP_URL ?? "http://localhost:3000";
const OUT_DIR = process.env.OUT_DIR ?? ".";

const consoleErrors = [];
const pageErrors = [];
const cloudRequests = [];

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
});

const context = await browser.newContext({
  viewport: { width: 430, height: 900 },
  geolocation: { latitude: 10.7626, longitude: 106.6602 },
  permissions: ["geolocation"],
  locale: "vi-VN",
  serviceWorkers: "block",
});

const page = await context.newPage();

page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (error) => pageErrors.push(`${error.name}: ${error.message}`));
page.on("response", (response) => {
  const url = response.url();
  if (url.includes("/api/clouds")) {
    cloudRequests.push({ url, status: response.status() });
  }
});

await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForTimeout(4000);

const button = page.getByRole("button", { name: /vệ tinh|satellite/i }).first();
await button.waitFor({ state: "visible", timeout: 20_000 });
await button.click();

await page.waitForTimeout(12000);

const mapState = await page.evaluate(() => {
  const canvas = document.querySelector(".maplibregl-canvas");
  const map = window.__lrMap;
  const style = map?.getStyle?.();
  const layers = style?.layers?.map((layer) => layer.id) ?? [];
  const index = layers.indexOf("cloud-layer");
  return {
    hasCanvas: Boolean(canvas),
    canvasSize: canvas ? `${canvas.clientWidth}x${canvas.clientHeight}` : null,
    stackAroundClouds: index >= 0 ? layers.slice(Math.max(0, index - 1), index + 5) : layers.slice(-6),
    cloudPaint: map?.getLayer?.("cloud-layer")
      ? {
          opacity: map.getPaintProperty("cloud-layer", "raster-opacity"),
          contrast: map.getPaintProperty("cloud-layer", "raster-contrast"),
          saturation: map.getPaintProperty("cloud-layer", "raster-saturation"),
        }
      : null,
    zoom: map?.getZoom?.(),
  };
});

await page.screenshot({ path: `${OUT_DIR}/satellite-after-click.png`, fullPage: false });

// Regional framing, the view Zoom Earth opens with.
await page.evaluate(() => {
  window.__lrMap?.jumpTo({ center: [108.5, 14.5], zoom: 4.6 });
});
await page.waitForTimeout(9000);
await page.screenshot({ path: `${OUT_DIR}/satellite-region.png`, fullPage: false });

const cloudTileRequests = cloudRequests.filter((item) => item.url.includes("/tiles/"));

console.log("=== CLOUD METADATA REQUESTS ===");
console.log(JSON.stringify(cloudRequests.filter((i) => !i.url.includes("/tiles/")), null, 2));
console.log("=== CLOUD TILE REQUESTS ===");
console.log("count:", cloudTileRequests.length);
console.log(JSON.stringify(cloudTileRequests.slice(0, 8), null, 2));
console.log("=== CONSOLE ERRORS ===");
console.log(JSON.stringify([...new Set(consoleErrors)], null, 2));
console.log("=== PAGE ERRORS ===");
console.log(JSON.stringify([...new Set(pageErrors)], null, 2));
console.log("=== MAP STATE ===");
console.log(JSON.stringify(mapState, null, 2));

await browser.close();
