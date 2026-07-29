import { chromium } from "playwright-core";

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const APP_URL = process.env.APP_URL ?? "http://localhost:3000";

const consoleErrors = [];
const radarResponses = [];

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
});

const page = await context.newPage();
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("response", (response) => {
  const url = response.url();
  if (url.includes("/api/radar")) radarResponses.push({ url, status: response.status() });
});

await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForTimeout(6000);
await page.screenshot({ path: "radar-state.png" });

const text = await page.evaluate(() => document.body.innerText);

console.log("=== RADAR API ===");
console.log(JSON.stringify(radarResponses.filter((i) => !i.url.includes("/tiles/")), null, 2));
console.log("radar tile requests:", radarResponses.filter((i) => i.url.includes("/tiles/")).length);
console.log("=== CONSOLE ERRORS ===");
console.log(JSON.stringify([...new Set(consoleErrors)], null, 2));
console.log("=== SHEET TEXT ===");
console.log(text.slice(0, 500));

await browser.close();
