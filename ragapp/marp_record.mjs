/**
 * Nimmt den suchbaren TalkPresenter als JPEG-Frames auf stdout auf (ffmpeg image2pipe).
 * Usage: node marp_record.mjs <htmlPath> <chromePath> <durationS> <fps>
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import puppeteer from "puppeteer-core";

const htmlPath = process.argv[2];
const chromePath = process.argv[3];
const durationS = Math.max(0.2, Number(process.argv[4]) || 1);
const fps = Math.max(1, Math.min(30, Number(process.argv[5]) || 30));
const width = Math.max(320, Math.round(Number(process.argv[6]) || 1280));
const height = Math.max(180, Math.round(Number(process.argv[7]) || 720));
const jpegQuality = width >= 1920 ? 90 : 82;

if (!htmlPath || !chromePath) {
  console.error("Usage: node marp_record.mjs <html> <chrome> <durationS> <fps> [width] [height]");
  process.exit(2);
}
if (!fs.existsSync(htmlPath)) {
  console.error(`HTML fehlt: ${htmlPath}`);
  process.exit(2);
}

const fileUrl = pathToFileURL(path.resolve(htmlPath)).href;
const frames = Math.max(1, Math.round(durationS * fps));

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
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  await page.goto(fileUrl, { waitUntil: "networkidle0", timeout: 120000 });
  await page.evaluate(() => {
    document.querySelectorAll(
      ".bespoke-marp-osc, [class*='bespoke-marp-osc'], .bespoke-marp-progress",
    ).forEach((el) => el.remove());
  });
  await page.waitForFunction(
    () => window.TalkPresenter && window.TalkPresenter.prepared,
    { timeout: 20000 },
  );

  for (let i = 0; i < frames; i++) {
    const t = Math.min(durationS, i / fps);
    await page.evaluate((sec) => window.TalkPresenter.seek(sec), t);
    const buf = await page.screenshot({
      type: "jpeg",
      quality: jpegQuality,
      clip: { x: 0, y: 0, width, height },
    });
    process.stdout.write(buf);
    if (i === 0 || i + 1 === frames || (i + 1) % 30 === 0) {
      console.error(`FRAME ${i + 1}/${frames}`);
    }
  }
} finally {
  await browser.close();
}
