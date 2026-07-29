import { chromium } from "playwright-core";

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const APP_URL = process.env.APP_URL ?? "http://localhost:3000";

const consoleErrors = [];
const vectorResponses = [];
const nearestResponses = [];

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
});

const context = await browser.newContext({
  viewport: { width: 900, height: 900 },
  geolocation: { latitude: 10.7626, longitude: 106.6602 },
  permissions: ["geolocation"],
  locale: "vi-VN",
});

const page = await context.newPage();
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("response", async (response) => {
  const url = response.url();
  if (!url.includes("/api/rain-vectors") && !url.includes("/api/nearest-rain")) return;
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = "unparsed";
  }
  const target = url.includes("/api/rain-vectors") ? vectorResponses : nearestResponses;
  target.push({ status: response.status(), body });
});

await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForTimeout(14_000);

const mapInfo = await page.evaluate(() => {
  const map = window.__lrMap;
  if (!map) return { exposed: false };
  const style = map.getStyle();
  const vectorLayers = style.layers
    .filter((layer) => layer.id.includes("rain-vector"))
    .map((layer) => ({ id: layer.id, type: layer.type }));
  const rendered = map.queryRenderedFeatures({
    layers: vectorLayers.map((layer) => layer.id),
  });
  return {
    exposed: true,
    zoom: Number(map.getZoom().toFixed(2)),
    vectorLayers,
    renderedFeatures: rendered.length,
  };
});

await page.screenshot({ path: "vectors-state.png" });

// Zoom out so 100 km of vectors fit into the viewport
await page.evaluate(() => window.__lrMap?.setZoom(9));
await page.waitForTimeout(4000);
const zoomedOut = await page.evaluate(() => {
  const map = window.__lrMap;
  if (!map) return null;
  return map.queryRenderedFeatures({
    layers: ["rain-vectors-line-layer", "rain-vectors-arrow-layer"],
  }).length;
});
console.log("rendered features at zoom 9:", zoomedOut);
await page.screenshot({ path: "vectors-zoomed.png" });

console.log("=== NEAREST RAIN ===");
for (const item of nearestResponses) {
  const body = item.body ?? {};
  console.log(
    `  distance=${body.distance}m dir=${body.direction} motion=${body.motionDirection} ` +
      `speed=${body.speedKmh}km/h approaching=${body.approaching} eta=${body.eta}min ` +
      `1h=${body.rainIn1h} 2h=${body.rainIn2h}`,
  );
  console.log(`  ${body.explanation}`);
}
console.log("=== RAIN VECTOR SUMMARY ===");
for (const item of vectorResponses) {
  const list = item.body?.vectors ?? [];
  console.log(`  ${list.length} vectors`);
  for (const vector of list.slice(0, 5)) {
    console.log(`    ${vector.direction} ${vector.speedKmh}km/h dbz=${vector.dbz}`);
  }
}
console.log("=== MAP INFO ===");
console.log(JSON.stringify(mapInfo, null, 2));
console.log("=== CONSOLE ERRORS ===");
console.log(JSON.stringify([...new Set(consoleErrors)], null, 2).slice(0, 2000));

await browser.close();
