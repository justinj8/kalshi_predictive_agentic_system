// Capture preview screenshots of the Kalshi Pit Wall intro + HUD.
// Verifies the cinematic launch sequence flows end-to-end before pushing.
//
// Run from dashboard/frontend with playwright installed:
//   node ../scripts/capture-preview.mjs
//
// Outputs /tmp/pit-wall-preview/*.png.
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const URL = process.env.PIT_WALL_URL || "http://127.0.0.1:4173/";
const OUT = "/tmp/pit-wall-preview";

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 1,
});
const page = await ctx.newPage();

console.log("Navigating to", URL);
await page.goto(URL, { waitUntil: "domcontentloaded" });

async function shot(name, atMs, startedAt) {
  const wait = atMs - (Date.now() - startedAt);
  if (wait > 0) await page.waitForTimeout(wait);
  const file = `${OUT}/${name}.png`;
  await page.screenshot({ path: file, fullPage: false });
  console.log(`  → ${file}  (t≈${Date.now() - startedAt}ms)`);
}

// Phase timeline (ms from mount): 1=450 establishing, 2=1900 launch,
// 3=3400 title, 4=4500 vitals, 5=5500 fade, done=6100.
const t0 = Date.now();
await shot("01-establishing", 1100, t0); // wide circuit, Ferrari on the line
await shot("02-launch", 2700, t0); // Ferrari mid-launch, smoke + streaks
await shot("03-title", 3900, t0); // KALSHI · PIT WALL slams in
await shot("04-vitals", 5000, t0); // telemetry vitals row
await shot("05-hud", 7200, t0); // live HUD has taken over

console.log("DONE");
await browser.close();
