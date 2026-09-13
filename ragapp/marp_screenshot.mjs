/**
 * Screenshot jeder Marp-HTML-Folie (Bespoke) als PNG – WYSIWYG zum HTML-Export.
 * Usage: node marp_screenshot.mjs <htmlPath> <outDir> <chromePath>
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import puppeteer from "puppeteer-core";

const htmlPath = process.argv[2];
const outDir = process.argv[3];
const chromePath = process.argv[4];

if (!htmlPath || !outDir || !chromePath) {
  console.error("Usage: node marp_screenshot.mjs <html> <outDir> <chrome>");
  process.exit(2);
}

fs.mkdirSync(outDir, { recursive: true });
const fileUrl = pathToFileURL(path.resolve(htmlPath)).href;

const browser = await puppeteer.launch({
  executablePath: chromePath,
  headless: true,
  args: [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
  ],
});

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1 });
  await page.goto(fileUrl, { waitUntil: "networkidle0", timeout: 120000 });
  await new Promise((r) => setTimeout(r, 500));

  const count = await page.$$eval("section", (secs) => secs.length);
  if (!count) {
    throw new Error("Keine <section>-Folien im HTML gefunden");
  }

  // Bespoke-Navigationsleiste entfernen (soll nicht im Video liegen)
  await page.evaluate(() => {
    document.querySelectorAll(
      ".bespoke-marp-osc, [class*='bespoke-marp-osc'], .bespoke-marp-progress",
    ).forEach((el) => el.remove());
  });
  await page.addStyleTag({
    content: `
      .bespoke-marp-osc,
      [class*="bespoke-marp-osc"],
      .bespoke-marp-progress {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
      }
    `,
  });

  for (let i = 0; i < count; i++) {
    // Marp Bespoke: Folie per Hash ansteuern (#1 … #N)
    await page.goto(`${fileUrl}#${i + 1}`, {
      waitUntil: "networkidle0",
      timeout: 60000,
    });
    await new Promise((r) => setTimeout(r, 250));
    // Fallback: Pfeiltasten, falls Hash nicht greift
    const active = await page.evaluate(() => {
      const secs = [...document.querySelectorAll("section")];
      const vis = secs.findIndex((s) => {
        const st = getComputedStyle(s);
        return st.visibility !== "hidden" && st.display !== "none" && s.offsetParent !== null;
      });
      return vis;
    });
    if (active !== i) {
      await page.goto(fileUrl, { waitUntil: "networkidle0", timeout: 60000 });
      await new Promise((r) => setTimeout(r, 200));
      for (let k = 0; k < i; k++) {
        await page.keyboard.press("ArrowRight");
        await new Promise((r) => setTimeout(r, 120));
      }
    }
    const out = path.join(
      outDir,
      `slide.${String(i + 1).padStart(3, "0")}.png`,
    );
    await page.screenshot({
      path: out,
      type: "png",
      clip: { x: 0, y: 0, width: 1280, height: 720 },
    });
  }
  console.log(`OK ${count}`);
} finally {
  await browser.close();
}
