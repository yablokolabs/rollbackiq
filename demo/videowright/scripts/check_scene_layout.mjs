/**
 * Checks that every scene fits the 1920x1080 frame.
 *
 * Worth having because a render takes about half an hour, and a panel that overflows
 * the frame is only visible in the finished video. This drives the dev server instead:
 * for each segment it navigates straight to it, makes every reveal visible, and
 * measures the live DOM.
 *
 * Four checks per segment:
 *   - the scene's own content must not be taller than the scene box
 *     (`scrollHeight` vs `clientHeight`);
 *   - every element must sit inside the scene's box;
 *   - every element in a `.stage` must sit inside that stage's box, because content
 *     that leaves its row uses up the gap to the blocks above and below it;
 *   - no two elements may cover the same pixels unless one contains the other. This
 *     is the check that catches a centred grid with more content than its row: the
 *     grid stays inside the frame, and its ends lie across the headline above it and
 *     the alert below it. Two `.loop` bars in one `.stage-stack` are exempt, because
 *     they share a cell on purpose.
 *
 * Measurements are taken against the scene's own bounding box, not the viewport,
 * because in the dev player the scene sits below a header. That offset does not exist
 * in `render.html`, so only scene-relative coordinates describe the rendered frame.
 *
 *   npx videowright dev --port 5199
 *   node scripts/check_scene_layout.mjs
 *
 * Exits non-zero if any segment overflows or overlaps, so it can gate a render.
 */

import { chromium } from "playwright";

const args = process.argv.slice(2);
const readFlag = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const BASE = readFlag("url", "http://127.0.0.1:5199/video/rollbackiq-demo");
const FRAME = { width: 1920, height: 1080 };
// Keep in step with videos/rollbackiq-demo/timeline.ts.
const SEGMENTS = (readFlag("segments", "title,baseline,regression,approval,recovery,duo,evaluation,outro") ?? "").split(",");

const browser = await chromium.launch();
// The dev player scales the scene down to fit its window, so the window has to be
// bigger than the frame or every measurement comes back multiplied by the scale.
const page = await browser
  .newContext({ viewport: { width: 2200, height: 1500 }, deviceScaleFactor: 1 })
  .then((context) => context.newPage());

const failures = [];

for (const segment of SEGMENTS) {
  await page.goto(`${BASE}#/${segment}/9`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);

  // Reveal every beat so the settled layout of the whole scene is measurable at once.
  const found = await page.evaluate(() => {
    const scene = document.querySelector(".rq-scene");
    if (!scene) return false;
    for (const element of scene.querySelectorAll("[data-beat]")) {
      element.style.setProperty("opacity", "1", "important");
    }
    return true;
  });
  if (!found) {
    failures.push({ segment, element: "<no scene rendered>", past: 0, detail: "" });
    continue;
  }
  await page.waitForTimeout(250);

  const result = await page.evaluate((frame) => {
    const scene = document.querySelector(".rq-scene");
    const box = scene.getBoundingClientRect();

    const label = (element) =>
      element.tagName.toLowerCase() +
      (element.className && typeof element.className === "string"
        ? "." + element.className.trim().split(/\s+/).slice(0, 2).join(".")
        : "");

    const overflow = [];
    for (const element of scene.querySelectorAll("*")) {
      const rect = element.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) continue;
      // Relative to the scene's own box, which is what the renderer frames.
      const past = Math.max(
        rect.right - box.right,
        rect.bottom - box.bottom,
        box.left - rect.left,
        box.top - rect.top,
      );
      if (past > 1) {
        overflow.push({ element: label(element), past: Math.round(past) });
      }
    }
    for (const stage of scene.querySelectorAll(".stage")) {
      const row = stage.getBoundingClientRect();
      let past = 0;
      for (const element of stage.querySelectorAll("*")) {
        const rect = element.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) continue;
        past = Math.max(past, rect.bottom - row.bottom, row.top - rect.top);
      }
      if (past > 1) {
        overflow.push({ element: "<stage content taller than its row>", past: Math.round(past) });
      }
    }
    overflow.sort((a, b) => b.past - a.past);

    const boxes = [...scene.querySelectorAll("*")]
      .map((element) => ({ element, rect: element.getBoundingClientRect() }))
      .filter(({ rect }) => rect.width >= 2 && rect.height >= 2);
    const overlap = [];
    for (let first = 0; first < boxes.length; first++) {
      for (let second = first + 1; second < boxes.length; second++) {
        const a = boxes[first];
        const b = boxes[second];
        if (a.element.contains(b.element) || b.element.contains(a.element)) continue;
        const stack = a.element.closest(".stage-stack");
        if (stack && stack === b.element.closest(".stage-stack")) continue;
        const across = Math.min(a.rect.right, b.rect.right) - Math.max(a.rect.left, b.rect.left);
        const down = Math.min(a.rect.bottom, b.rect.bottom) - Math.max(a.rect.top, b.rect.top);
        if (across > 1 && down > 1) {
          overlap.push({
            element: `${label(a.element)} overlaps ${label(b.element)}`,
            past: Math.round(Math.min(across, down)),
          });
        }
      }
    }
    overlap.sort((a, b) => b.past - a.past);

    return {
      sceneOverflow: Math.round(scene.scrollHeight - scene.clientHeight),
      box: [Math.round(box.width), Math.round(box.height)],
      overflow: overflow.slice(0, 4),
      overlap: overlap.slice(0, 4),
      headline:
        (scene.querySelector(".headline") ?? scene.querySelector(".wordmark"))?.textContent?.trim() ??
        "(none)",
    };
  }, FRAME);

  const issues = [];
  if (result.sceneOverflow > 1) issues.push({ element: "<scene content taller than the frame>", past: result.sceneOverflow });
  issues.push(...result.overflow, ...result.overlap);

  const status = issues.length === 0 ? "ok  " : "FAIL";
  console.log(`${status} ${segment.padEnd(12)} ${result.box[0]}x${result.box[1]}  ${result.headline}`);
  for (const issue of issues) {
    console.log(`       ${String(issue.past).padStart(4)}px  ${issue.element}`);
    failures.push({ segment, ...issue });
  }
}

await browser.close();

if (failures.length === 0) {
  console.log("\nOK: every segment fits the 1920x1080 frame and nothing overlaps");
  process.exit(0);
}
console.log(`\n${failures.length} layout fault(s) across ${new Set(failures.map((f) => f.segment)).size} segment(s)`);
process.exit(1);
