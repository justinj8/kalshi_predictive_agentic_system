// Capture preview screenshots of the Kalshi Pit Wall at each intro phase
// + final HUD. Used during development to verify the intro animation flows
// end-to-end before pushing changes.
//
// Run with:  node scripts/capture-preview.mjs
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
await page.goto(URL, { waitUntil: "networkidle" });

async function shot(name, waitMs) {
  await page.waitForTimeout(waitMs);
  const file = `${OUT}/${name}.png`;
  await page.screenshot({ path: file, fullPage: false });
  console.log("  →", file);
}

// Time-aligned with IntroSequence phase boundaries
//  phase 0: 0      ms (pre)
//  phase 1: 350    ms (red horizon line + corners)
//  phase 2: 1300   ms (ident lands)
//  phase 3: 2300   ms (vitals row)
//  phase 4: 3500   ms (fade out)
//  done:    4200   ms (HUD on screen)
//
// We sample at 600ms, 1700ms, 2700ms, then again at 5500ms (clearly
// post-intro) so we know the dashboard is taking over.

await shot("01-phase1-horizon", 600);
await shot("02-phase2-ident", 1100);
await shot("03-phase3-vitals", 1000);
await shot("04-hud-final", 2500);

console.log("DONE");

await browser.close();
