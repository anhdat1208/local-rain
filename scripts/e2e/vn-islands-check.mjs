import { chromium } from "playwright-core";

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const APP_URL = process.env.APP_URL ?? "http://localhost:3000";

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
});

const context = await browser.newContext({
  viewport: { width: 900, height: 700 },
  locale: "vi-VN",
});
const page = await context.newPage();
await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForTimeout(5000);

await page.evaluate(async () => {
  const map = window.__lrMap;
  if (!map) throw new Error("map missing");
  await new Promise((resolve) => {
    map.once("moveend", () => resolve());
    map.flyTo({ center: [113.2, 13.5], zoom: 5.2, essential: true });
  });
});
await page.waitForTimeout(3000);
await page.screenshot({ path: "vn-islands.png", fullPage: false });

const labels = await page.evaluate(() => {
  const map = window.__lrMap;
  if (!map) return [];
  const layerIds = [
    "vn-sovereignty-labels-layer",
    "label_other",
    "water_name_point_label",
    "water_name_line_label",
    "label_state",
  ].filter((id) => map.getLayer(id));
  const feats = map.queryRenderedFeatures({ layers: layerIds });
  return [
    ...new Set(
      feats
        .map((f) => f.properties?.name || f.properties?.["name:vi"] || "")
        .filter(Boolean),
    ),
  ];
});

console.log("LABELS", JSON.stringify(labels, null, 2));
const joined = labels.join(" | ");
const bad = /西沙|南沙|中沙|南海|Paracel|Spratly|Xisha|Nansha/i.test(joined);
const good = /Hoàng Sa|Trường Sa|Biển Đông/.test(joined);
console.log("hasVN", good, "hasCN", bad);
await browser.close();
process.exit(good && !bad ? 0 : 2);
