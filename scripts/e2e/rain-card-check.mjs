import { chromium } from "playwright-core";

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const APP_URL = process.env.APP_URL ?? "http://localhost:3000";
const LAT = Number(process.env.LAT ?? 10.7626);
const LNG = Number(process.env.LNG ?? 106.6602);

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
});

const context = await browser.newContext({
  viewport: { width: 430, height: 900 },
  geolocation: { latitude: LAT, longitude: LNG },
  permissions: ["geolocation"],
  locale: "vi-VN",
});

const page = await context.newPage();
const errors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(msg.text());
});

await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 60_000 });
await page.waitForTimeout(7000);
await page.screenshot({ path: "rain-card.png" });

console.log("=== SHEET TEXT ===");
console.log(await page.evaluate(() => document.body.innerText));
console.log("=== CONSOLE ERRORS ===");
console.log(JSON.stringify([...new Set(errors)], null, 2));

await browser.close();
