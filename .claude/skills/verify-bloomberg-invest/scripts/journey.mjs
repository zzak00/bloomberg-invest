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

    // Search: "/" and the header field, or on a phone the search icon and the page's field.
    const QUERY = "dividende proposé";
    const icon = page.getByRole("link", { name: "Search the filings" });
    if (await icon.isVisible()) {
      await icon.click();
      await page.getByRole("searchbox", { name: "Search the filings" }).fill(QUERY);
    } else {
      await page.keyboard.press("/");
      const focused = await page.evaluate(() => document.activeElement?.id);
      check(vp.name, '"/" focuses the header search', focused === "header-search", focused);
      await page.keyboard.type(QUERY);
    }
    await page.keyboard.press("Enter");
    const results = page.getByRole("list", { name: "Passages" }).getByRole("link");
    await results.first().waitFor();
    const first = (await results.first().innerText()).replace(/\s+/g, " ");
    check(vp.name, "search lists passages", (await results.count()) >= 1, `${await results.count()} result(s)`);
    check(vp.name, "AC3: the p. 10 dividend comes first", /Dividende/.test(first) && /p\. 10\b/.test(first), first.slice(0, 120));
    await page.mouse.move(0, vp.height - 1);
    await shot("05-search");

    // A result opens the source viewer on its page with the passage highlighted.
    await results.first().click();
    const resultPage = page.getByRole("img", { name: /^Page 10 of/ });
    await resultPage.waitFor();
    await resultPage.evaluate((img) => img.complete || new Promise((done) => (img.onload = done)));
    const mark = page.locator(".paper-sheet .mark").first();
    await mark.waitFor();
    const [sheetBox, markBox] = [await page.locator(".paper-sheet").boundingBox(), await mark.boundingBox()];
    check(
      vp.name,
      "the passage is highlighted on its page",
      markBox && sheetBox && markBox.width > 20 && markBox.x >= sheetBox.x && markBox.x + markBox.width <= sheetBox.x + sheetBox.width + 1,
      markBox && `${Math.round(markBox.width)}x${Math.round(markBox.height)} at ${Math.round(markBox.x)},${Math.round(markBox.y)}`,
    );
    check(vp.name, "the passage bar names it", /Dividende/.test(await page.getByRole("status").innerText()));
    await shot("06-search-result");

    // A link to a passage with no page waits for the passage: on a slow network the viewer must
    // not show page 1 first.
    const passageUrl = new URL(page.url());
    passageUrl.searchParams.delete("page");
    const fetched = [];
    const onRequest = (r) => {
      const n = r.url().match(/\/pages\/(\d+)\.png/);
      if (n) fetched.push(Number(n[1]));
    };
    await page.route("**/api/chunks/**", async (route) => {
      await new Promise((done) => setTimeout(done, 1500));
      await route.continue();
    });
    page.on("request", onRequest);
    await page.goto(passageUrl.href);
    await page.locator(".paper-sheet .mark").first().waitFor();
    page.off("request", onRequest);
    await page.unroute("**/api/chunks/**");
    check(vp.name, "a passage link opens on its page, never page 1 first", fetched.join() === "10", `pages fetched: ${fetched.join(", ")}`);

    // A long table is split between rows; its parts say which part they are.
    await page.goto(`${base}/search?q=${encodeURIComponent("compte de produits et charges")}`);
    const part = page.locator(".result-kind", { hasText: /^TABLE · PART \d+ OF \d+$/ }).first();
    await part.waitFor();
    await part.scrollIntoViewIfNeeded();
    check(vp.name, "a split table's result names its part", await part.isVisible(), await part.innerText());
    await shot("07-search-table-part");

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
      await shot(`07-empty-${path}`);
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
