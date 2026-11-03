#!/usr/bin/env node
// Drive the running app like a user and save screenshots at 1440, 1024 and 390.
//
//   node .claude/skills/verify-bloomberg-invest/scripts/journey.mjs [--base http://localhost:8080]
//
// Needs at least one ingested filing. Writes verify-evidence/<timestamp>/ with one PNG per step
// and viewport, plus journey.json listing every check. Exits 1 if any check fails.

import { mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const { chromium } = createRequire(join(root, "frontend/package.json"))("playwright");

const base = process.argv.includes("--base")
  ? process.argv[process.argv.indexOf("--base") + 1]
  : "http://localhost:8080";
const VIEWPORTS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "1024", width: 1024, height: 768 },
  { name: "390", width: 390, height: 844 },
];
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const out = join(root, "verify-evidence", stamp);
mkdirSync(out, { recursive: true });

const checks = [];
function check(viewport, step, ok, detail) {
  checks.push({ viewport, step, ok: Boolean(ok), detail });
  console.log(`${ok ? "PASS" : "FAIL"} [${viewport}] ${step}${detail ? ` - ${detail}` : ""}`);
}

const browser = await chromium.launch();
try {
  for (const vp of VIEWPORTS) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
    const errors = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(String(e)));
    const shot = (name) => page.screenshot({ path: join(out, `${vp.name}-${name}.png`) });

    // INDEX lists the filings.
    await page.goto(`${base}/index`);
    const rows = page.getByRole("list", { name: "Filings" }).getByRole("link");
    await rows.first().waitFor();
    check(vp.name, "index lists at least one filing", (await rows.count()) >= 1, `${await rows.count()} row(s)`);
    check(vp.name, "INDEX tab is current", (await page.getByRole("link", { name: "Index" }).getAttribute("aria-current")) === "page");
    await shot("01-index");

    // Opening a filing shows page 1 in the source viewer.
    await rows.first().click();
    await page.waitForURL(/\/documents\//);
    const image = page.getByRole("img", { name: /^Page 1 of/ });
    await image.waitFor();
    await page.waitForFunction(() => document.querySelector(".paper-sheet img")?.complete);
    check(vp.name, "page 1 image renders", (await image.evaluate((img) => img.naturalWidth)) > 0);
    check(vp.name, "INDEX tab stays marked in the viewer", (await page.getByRole("link", { name: "Index" }).getAttribute("aria-current")) === "true");
    await shot("02-viewer-page-1");

    // NEXT moves to page 2.
    await page.getByRole("button", { name: "NEXT →" }).click();
    await page.getByRole("img", { name: /^Page 2 of/ }).waitFor();
    await page.waitForFunction(() => document.querySelector(".paper-sheet img")?.complete);
    check(vp.name, "NEXT shows page 2", new URL(page.url()).searchParams.get("page") === "2");
    await shot("03-viewer-page-2");

    // A section in the outline jumps to its page (the outline is folded at 390).
    const toggle = page.getByRole("button", { name: "SHOW" });
    if (await toggle.isVisible()) await toggle.click();
    const section = page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: /^NOTE 13\./ });
    if (await section.count()) {
      await section.click();
      // The URL changes before React renders the new page: wait for page 54's own image.
      const target = page.getByRole("img", { name: /^Page 54 of/ });
      await target.waitFor();
      await target.evaluate((img) => img.complete || new Promise((done) => (img.onload = done)));
      check(
        vp.name,
        "outline jumps to NOTE 13 on page 54",
        (await page.inputValue("#page-input")) === "54" &&
          (await section.getAttribute("aria-current")) === "true",
      );
    } else {
      const first = page.getByRole("navigation", { name: "Sections" }).getByRole("button").nth(1);
      await first.click();
      check(vp.name, "outline has sections", true, "NOTE 13 not in this filing; clicked the first section");
      await page.waitForFunction(() => document.querySelector(".paper-sheet img")?.complete);
    }
    await page.mouse.move(0, vp.height - 1);
    await shot("04-viewer-section");

    // MAP, CHECKS and KPIs show their empty states.
    for (const [path, title] of [
      ["map", "The map arrives with entities and facts"],
      ["checks", "Nothing to check yet"],
      ["kpis", "KPIs follow checked figures"],
    ]) {
      await page.goto(`${base}/${path}`);
      const heading = page.getByRole("heading", { name: title });
      await heading.waitFor();
      check(vp.name, `${path.toUpperCase()} empty state`, await heading.isVisible());
      await shot(`05-empty-${path}`);
    }

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(vp.name, "no horizontal page scroll", overflow <= 0, `${overflow}px`);
    check(vp.name, "no console errors", errors.length === 0, errors.join(" | "));
    await page.close();
  }
} finally {
  await browser.close();
}

writeFileSync(join(out, "journey.json"), JSON.stringify({ base, checks }, null, 2));
const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed. Evidence: ${out}`);
process.exit(failed.length ? 1 : 0);
