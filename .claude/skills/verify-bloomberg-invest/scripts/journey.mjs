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
    const rows = page.getByRole("list", { name: "Filings" }).getByRole("listitem");
    await rows.first().waitFor();
    check(vp.name, "index lists at least one filing", (await rows.count()) >= 1, `${await rows.count()} row(s)`);
    check(vp.name, "INDEX tab is current", (await page.getByRole("link", { name: "Index" }).getAttribute("aria-current")) === "page");
    await shot("01-index");

    // Opening a filing shows page 1 in the source viewer (the company name opens its dossier).
    await rows.first().getByRole("link", { name: /financial report|Issuer page/ }).click();
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

    // Up and Down scroll the page, as in a PDF reader; the page field keeps its own keys (#49).
    // At 390 the page fits on screen, so there is nothing to scroll.
    const scrollTop = () => page.locator(".paper-scroll").evaluate((el) => el.scrollTop);
    const scrollable = await page.locator(".paper-scroll").evaluate((el) => el.scrollHeight > el.clientHeight);
    const start = await scrollTop();
    await page.keyboard.press("ArrowDown");
    const down = await scrollTop();
    await page.keyboard.press("ArrowUp");
    const up = await scrollTop();
    check(
      vp.name,
      "Down and Up scroll the page",
      (scrollable ? down > start : down === start) && up === start,
      `${start}px, Down ${down}px, Up ${up}px${scrollable ? "" : " (the page fits)"}`,
    );
    const pageField = page.getByLabel("Page number");
    await pageField.focus();
    await page.keyboard.press("ArrowDown");
    check(vp.name, "the page field keeps its arrow keys", (await scrollTop()) === up, `${await scrollTop()}px`);
    await pageField.blur();

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
    const results = page.getByRole("list", { name: "Results" }).getByRole("link");
    await results.first().waitFor();
    const first = (await results.first().innerText()).replace(/\s+/g, " ");
    check(vp.name, "search lists results", (await results.count()) >= 1, `${await results.count()} result(s)`);
    check(vp.name, "AC3: the p. 10 dividend comes first", /Dividende/.test(first) && /p\. 10\b/.test(first), first.slice(0, 120));
    await page.mouse.move(0, vp.height - 1);
    await shot("05-search");

    // A result opens the source viewer on its page with the chunk highlighted.
    await results.first().click();
    const resultPage = page.getByRole("img", { name: /^Page 10 of/ });
    await resultPage.waitFor();
    await resultPage.evaluate((img) => img.complete || new Promise((done) => (img.onload = done)));
    const mark = page.locator(".paper-sheet .mark").first();
    await mark.waitFor();
    const [sheetBox, markBox] = [await page.locator(".paper-sheet").boundingBox(), await mark.boundingBox()];
    check(
      vp.name,
      "the chunk is highlighted on its page",
      markBox && sheetBox && markBox.width > 20 && markBox.x >= sheetBox.x && markBox.x + markBox.width <= sheetBox.x + sheetBox.width + 1,
      markBox && `${Math.round(markBox.width)}x${Math.round(markBox.height)} at ${Math.round(markBox.x)},${Math.round(markBox.y)}`,
    );
    check(vp.name, "the highlight bar names it", /Dividende/.test(await page.getByRole("status").innerText()));
    await shot("06-search-result");

    // A link to a chunk with no page waits for the chunk: on a slow network the viewer must
    // not show page 1 first.
    const chunkUrl = new URL(page.url());
    chunkUrl.searchParams.delete("page");
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
    await page.goto(chunkUrl.href);
    await page.locator(".paper-sheet .mark").first().waitFor();
    page.off("request", onRequest);
    await page.unroute("**/api/chunks/**");
    check(vp.name, "a chunk link opens on its page, never page 1 first", fetched.join() === "10", `pages fetched: ${fetched.join(", ")}`);

    // A long table is split between rows; its parts say which part they are.
    await page.goto(`${base}/search?q=${encodeURIComponent("compte de produits et charges")}`);
    const part = page.locator(".result-kind", { hasText: /^TABLE · PART \d+ OF \d+$/ }).first();
    await part.waitFor();
    await part.scrollIntoViewIfNeeded();
    check(vp.name, "a split table's result names its part", await part.isVisible(), await part.innerText());
    await shot("07-search-table-part");

    // The company's dossier lists its figures by statement and year (#22 AC4).
    await page.goto(`${base}/index`);
    await rows.first().getByRole("link", { name: "Maroc Telecom", exact: true }).click();
    await page.waitForURL(/\/companies\/MA0000011488/);
    const income = page.getByRole("region", { name: "Income statement" });
    await income.waitFor();
    const tab = await page.getByRole("tab", { selected: true }).innerText();
    check(vp.name, "AC4: the dossier opens on its figures", /^FIGURES · \d+$/.test(tab), tab);
    const figureCount = Number(tab.split("·")[1]);
    const revenue = income.getByRole("link", { name: /^Revenue, FY2025: 36 681 MAD m, on page \d+$/ });
    check(vp.name, "AC4: revenue FY2025 is listed as written", await revenue.isVisible());
    // Its listing and last close sit under its name (#26 AC4).
    check(vp.name, "AC4: the dossier names the ticker", await page.locator(".dossier-id .chip", { hasText: /^IAM$/ }).isVisible());
    const price = page.getByRole("group", { name: "Last close" });
    const priceText = (await price.innerText()).replace(/\s+/g, " ");
    check(vp.name, "AC4: the last close and its change", /CLOSE [\d\u202f\u00a0 ]+,\d{2} MAD [+-−]?[\d,]+ %/.test(priceText), priceText);
    check(
      vp.name,
      "AC4: its date and source",
      /\d{2}\/\d{2}\/\d{4} · Bourse de Casablanca · raw close, not adjusted for dividends/.test(priceText),
    );
    check(vp.name, "AC4: where its history starts", /History from \d{2}\/\d{2}\/\d{4}/.test(priceText));
    const line = price.getByRole("img", { name: /^Closes from / });
    await line.waitFor();
    check(vp.name, "AC4: a three-year price line", (await line.locator("polyline").getAttribute("points")).split(" ").length > 500, await line.getAttribute("aria-label"));
    const years = await page.getByRole("columnheader", { name: /^FY\d{4}$/ }).allInnerTexts();
    check(vp.name, "years run newest first", years.length === 0 || years[0] === "FY2025", years.join(" "));
    await shot("08-dossier");
    await page.getByRole("button", { name: "COMPANY-ONLY · CGNC" }).click();
    await page.getByRole("button", { name: "COMPANY-ONLY · CGNC", pressed: true }).waitFor();
    check(vp.name, "the basis switch shows company-only figures", (await page.getByRole("table").count()) >= 1);
    await shot("09-dossier-company-only");
    await page.getByRole("button", { name: "CONSOLIDATED · IFRS" }).click();

    // A figure opens the source viewer on its page with its cell highlighted (#22 AC4).
    const cellPage = Number((await revenue.getAttribute("aria-label")).match(/page (\d+)$/)[1]);
    await revenue.click();
    await page.waitForURL(/fact=/);
    const factImage = page.getByRole("img", { name: new RegExp(`^Page ${cellPage} of`) });
    await factImage.waitFor();
    await factImage.evaluate((img) => img.complete || new Promise((done) => (img.onload = done)));
    const cell = page.locator(".paper-sheet .mark").first();
    await cell.waitFor();
    const cellBox = await cell.boundingBox();
    check(
      vp.name,
      "AC4: the cell is highlighted, not its whole table",
      cellBox && cellBox.width > 4 && cellBox.width < vp.width / 3 && cellBox.height < 40,
      cellBox && `${Math.round(cellBox.width)}x${Math.round(cellBox.height)}`,
    );
    const bar = await page.getByRole("status").innerText();
    check(vp.name, "the highlight bar names the figure", /CELL/.test(bar) && /Revenue · FY2025/.test(bar) && /36 681 MAD m/.test(bar), bar.replace(/\s+/g, " "));
    await shot("10-figure-cell");

    // The dossier's facts by section open in the inspector (#24 AC4).
    await page.goto(`${base}/companies/MA0000011488?tab=facts`);
    const factsTab = page.getByRole("tab", { name: /^FACTS · \d+$/, selected: true });
    await factsTab.waitFor();
    const ownership = page.getByRole("region", { name: /^OWNERSHIP · \d+$/ });
    await ownership.waitFor();
    const holders = ownership.getByRole("button", { name: / holds .* of / });
    check(vp.name, "AC4: the dossier lists the shareholders", (await holders.count()) >= 3, await factsTab.innerText());
    const sections = await page.getByRole("heading", { level: 2 }).allInnerTexts();
    check(vp.name, "AC4: facts by kind, in sections", sections.length >= 5, sections.join(" | "));
    await shot("10a-dossier-facts");
    await holders.first().click();
    const inspector = page.getByRole("dialog", { name: "Fact inspector" });
    await inspector.locator(".inspector-sentence").waitFor();
    const sentence = await inspector.locator(".inspector-sentence").innerText();
    const detailKeys = await inspector.locator(".inspector-details dt").allInnerTexts();
    check(vp.name, "AC4: the inspector states the fact in one sentence", / holds .* of /.test(sentence), sentence);
    check(vp.name, "AC4: with its date, recorded date and review", ["AS OF", "RECORDED", "REVIEW"].every((k) => detailKeys.includes(k)), detailKeys.join(" "));
    check(vp.name, "AC4: with its evidence status and quote", (await inspector.locator(".inspector-status").isVisible()) && (await inspector.locator(".inspector-quote").innerText()).includes("«"));
    const panel = await inspector.boundingBox();
    check(
      vp.name,
      vp.width < 640 ? "the inspector is a full-width sheet" : "the inspector is a side panel",
      vp.width < 640 ? panel.width >= vp.width - 1 : panel.width <= 402,
      `${Math.round(panel.width)}px wide`,
    );
    await shot("10b-fact-inspector");
    await inspector.getByRole("link", { name: "OPEN SOURCE →" }).click();
    await page.waitForURL(/\/documents\/.*fact=/);
    await page.locator(".paper-sheet .mark").first().waitFor();
    const factBar = (await page.getByRole("status").innerText()).replace(/\s+/g, " ");
    check(vp.name, "the source viewer highlights the fact", /SHAREHOLDING/i.test(factBar), factBar);
    await shot("10c-fact-source");

    // A kind with a basis and a fiscal year: an audit mandate.
    await page.goto(`${base}/companies/MA0000011488?tab=facts`);
    await page.getByRole("region", { name: /^AUDITORS · \d+$/ }).getByRole("button", { name: / audits / }).first().click();
    await inspector.locator(".inspector-details").waitFor();
    const mandateKeys = await inspector.locator(".inspector-details dt").allInnerTexts();
    check(vp.name, "AC4: PERIOD and BASIS for a mandate", mandateKeys.includes("PERIOD") && mandateKeys.includes("BASIS"), mandateKeys.join(" "));
    await page.keyboard.press("Escape");

    // A Conflict shows both values and both sources; Keep and Undo record a Review (S3b, D5).
    await page.goto(`${base}/companies/MA0000011488?tab=facts`);
    await page.getByRole("tab", { name: /^FACTS · \d+$/, selected: true }).waitFor();
    const disagreeing = page.getByRole("button", { name: /values disagree$/ });
    await page.getByRole("region", { name: /^OWNERSHIP · \d+$/ }).waitFor();
    if ((await disagreeing.count()) === 0) {
      check(vp.name, "S3b: a Conflict in this data", false, "no row with two values: see features/facts.md");
    } else {
      const mark = await disagreeing.first().locator("xpath=ancestor::tr").locator(".facts-flag").first().innerText();
      check(vp.name, "the dossier marks a Conflict with its count", /^≠ · \d+ VALUES$/.test(mark), mark);
      await disagreeing.first().scrollIntoViewIfNeeded();
      await disagreeing.first().click();
      const sides = inspector.getByRole("list", { name: "Values at this date" }).getByRole("listitem");
      await sides.first().waitFor();
      check(vp.name, "S3b: both values side by side", (await sides.count()) >= 2, `${await sides.count()} sides`);
      check(vp.name, "S3b: each with its source and quote", (await sides.first().locator(".inspector-side-quote").count()) === 1);
      const why = await inspector.locator(".inspector-note").innerText();
      check(vp.name, "S3b: which one is shown, and why", /^The dossier shows [A-Z], because /.test(why), why);
      await shot("10d-conflict");
      const keepB = inspector.getByRole("button", { name: /^KEEP B · / });
      if (await keepB.count()) {
        await keepB.click();
        await inspector.getByRole("status").getByText(/^Kept B · /).waitFor();
        const keptBy = await inspector.locator(".inspector-status").innerText();
        check(vp.name, "D5: keeping a value records who and when", /^Kept by .+ on \d{2}\/\d{2}\/\d{4}/.test(keptBy), keptBy);
        await shot("10e-conflict-kept");
        await inspector.getByRole("button", { name: "UNDO" }).click();
        await inspector.getByRole("button", { name: /^KEEP A · / }).waitFor();
        check(vp.name, "D5: undo puts the Conflict back", true);
      } else {
        check(vp.name, "D5: a value was already kept", (await inspector.getByRole("button", { name: "UNDO" }).count()) === 1);
      }
    }
    await page.keyboard.press("Escape");
    await inspector.waitFor({ state: "detached" });
    check(vp.name, "Escape closes the inspector", !/fact=/.test(page.url()));

    // CHECKS Names: the names no rule linked, with their passage (S7b); a decision is undone.
    await page.goto(`${base}/checks?tab=names`);
    await page.getByRole("tab", { name: /^NAMES · \d+$/, selected: true }).waitFor();
    const names = page.getByRole("list", { name: "Names" }).getByRole("listitem");
    await names.first().waitFor();
    const firstName = await names.first().getAttribute("aria-label");
    check(vp.name, "S7b: names to check come first", / to check$/.test(firstName ?? ""), firstName);
    check(vp.name, "S7b: each with the passage it was read from", (await names.first().locator(".name-passage").count()) === 1);
    await shot("10f-checks-names");
    const toDecide = names.first();
    const label = (firstName ?? "").replace(/: to check$/, "");
    await toDecide.getByRole("button", { name: "NEITHER" }).click();
    const decided = page.getByRole("listitem", { name: `${label}: neither an Organisation nor a Person`, exact: true });
    await decided.waitFor();
    check(vp.name, "S7b: a decision records who and when", /by .+ on \d{2}\/\d{2}\/\d{4}/.test(await decided.innerText()));
    await decided.getByRole("button", { name: "UNDO" }).click();
    await page.getByRole("listitem", { name: `${label}: to check`, exact: true }).waitFor();
    check(vp.name, "S7b: undo puts the name back to check", true);
    const withCandidate = page.getByRole("listitem", { name: / to check$/ }).filter({ has: page.locator(".name-candidate") }).first();
    const sameLabel = ((await withCandidate.getAttribute("aria-label")) ?? "").replace(/: to check$/, "");
    const candidate = (await withCandidate.locator(".name-candidate-name").first().innerText()).trim();
    await withCandidate.locator(".name-candidate").first().getByRole("button", { name: "SAME AS" }).click();
    const linked = page.getByRole("listitem", { name: `${sameLabel}: linked`, exact: true });
    await linked.waitFor();
    check(vp.name, "S7b: SAME AS links the name", (await linked.innerText()).includes(`Same as ${candidate}`), `${sameLabel} → ${candidate}`);
    await linked.getByRole("button", { name: "UNDO" }).click();
    await page.getByRole("listitem", { name: `${sameLabel}: to check`, exact: true }).waitFor();

    // CHECKS lists the facts the check refused, with why (D2).
    await page.getByRole("tab", { name: /^REJECTED FACTS · \d+$/ }).click();
    const refused = page.getByRole("list", { name: "Rejected facts" }).getByRole("listitem");
    await refused.first().waitFor();
    check(vp.name, "D2: a rejected fact says why", /: (its|a number|a party|it states) /.test((await refused.first().getAttribute("aria-label")) ?? ""), await refused.first().getAttribute("aria-label"));
    await shot("10g-checks-rejected-facts");

    // CHECKS lists the figures that feed a KPI, problems first; a check is recorded and undone (#23).
    await page.goto(`${base}/checks`);
    await page.getByRole("heading", { name: "Checks", exact: true }).waitFor();
    const filing = page.getByRole("region", { name: /^Maroc Telecom · Annual financial report 2025$/ });
    await filing.waitFor();
    const checkRows = filing.getByRole("listitem");
    const firstRow = await checkRows.first().getAttribute("aria-label");
    check(vp.name, "AC1: problems come first", /: Needs review$/.test(firstRow ?? ""), firstRow);
    check(
      vp.name,
      "a rejected figure can't be accepted",
      await checkRows.first().getByRole("button", { name: "ACCEPT" }).isDisabled(),
    );
    const reason = checkRows.first().locator(".check-reason");
    check(
      vp.name,
      "a rejected row's reason shows in full",
      /^ITS |^A |^NO /.test(await reason.innerText()) && (await reason.evaluate((el) => el.scrollWidth <= el.clientWidth)),
      await reason.innerText(),
    );
    const reviewer = await page.locator(".checks-reviewer").innerText();
    check(vp.name, "the reviewer is set", /Checks are recorded as/.test(reviewer), reviewer);
    const revenueRow = filing.getByRole("listitem", { name: /^Revenue, FY2025: To check$/ }).first();
    await revenueRow.scrollIntoViewIfNeeded();
    const crop = revenueRow.locator(".check-crop img");
    await crop.evaluate((img) => img.complete || new Promise((done) => (img.onload = done)));
    check(vp.name, "AC1: the source is rendered from the page", (await crop.evaluate((img) => img.naturalWidth)) > 0);
    check(vp.name, "AC1: the cell is highlighted on it", (await revenueRow.locator(".check-crop .mark").count()) >= 1);
    await shot("11-checks");

    await revenueRow.getByRole("button", { name: "CORRECT" }).click();
    const picks = revenueRow.getByRole("group", { name: "Cells in the same row" });
    await picks.waitFor();
    check(vp.name, "a correction offers the cells of the row", (await picks.getByRole("button").count()) >= 1);
    await shot("12-checks-correct");
    await revenueRow.getByRole("button", { name: "CANCEL" }).click();

    await revenueRow.getByRole("button", { name: "ACCEPT" }).click();
    const accepted = page.getByRole("listitem", { name: /^Revenue, FY2025: Accepted$/ }).first();
    await accepted.waitFor();
    const done = await accepted.locator(".check-done").innerText();
    check(vp.name, "AC1: accepting records who and when", /^Accepted by .+ on \d{2}\/\d{2}\/\d{4}/.test(done), done);
    await shot("13-checks-accepted");

    // The source viewer says the figure was checked (#23 AC4).
    await accepted.getByRole("link", { name: /^Open the cell on page \d+ in the source viewer$/ }).click();
    await page.waitForURL(/fact=/);
    const checkedBar = page.getByRole("status");
    await checkedBar.getByText(/^Checked by /).waitFor();
    check(vp.name, "AC4: the viewer shows the check", true, (await checkedBar.innerText()).replace(/\s+/g, " "));
    await shot("14-checked-figure");

    // Undo it: a reopening puts the figure back to CHECKS.
    await page.goto(`${base}/checks?status=done`);
    const reopen = page.getByRole("listitem", { name: /^Revenue, FY2025: Accepted$/ }).first();
    await reopen.getByRole("button", { name: "REOPEN" }).click();
    await page.getByRole("listitem", { name: /^Revenue, FY2025: To check$/ }).first().waitFor();
    check(vp.name, "a reopened figure is to check again", true);

    // A corrected rejected figure counts: the viewer and the dossier show the correction (#19 R8).
    // Whichever figure needs review: the analyst may have corrected the others on this data.
    await page.goto(`${base}/checks`);
    const rejectedRow = page.getByRole("listitem", { name: /, FY\d{4}: Needs review$/ }).first();
    await rejectedRow.scrollIntoViewIfNeeded();
    const rejectedName = (await rejectedRow.getAttribute("aria-label")).replace(/: Needs review$/, "");
    const asWritten = (await rejectedRow.locator(".check-number").first().innerText()).trim();
    const rowNamed = (status) =>
      page.getByRole("listitem", { name: `${rejectedName}: ${status}`, exact: true }).first();
    await rejectedRow.getByRole("button", { name: "CORRECT" }).click();
    await rejectedRow.getByRole("textbox").fill(asWritten);
    await rejectedRow.getByRole("button", { name: "SAVE" }).click();
    const corrected = rowNamed("Corrected");
    await corrected.waitFor();
    check(vp.name, "a rejected figure is corrected", /^Corrected by .+ on \d{2}\/\d{2}\/\d{4}/.test(await corrected.locator(".check-done").innerText()), rejectedName);
    await shot("15-checks-corrected");
    await corrected.getByRole("link", { name: /^Open .* in the source viewer$/ }).click();
    await page.waitForURL(/fact=/);
    const correctedBar = page.getByRole("status");
    await correctedBar.getByText(/^Corrected by /).waitFor();
    const correctedText = (await correctedBar.innerText()).replace(/\s+/g, " ");
    check(vp.name, "the viewer shows the correction on its source", /PAGE|CELL|QUOTE/.test(correctedText) && correctedText.includes(`${asWritten} MAD m`), correctedText);
    await shot("16-corrected-figure");
    await page.goto(`${base}/companies/MA0000011488`);
    const counted = await page.getByRole("tab", { name: /^FIGURES · \d+$/, selected: true }).innerText();
    check(vp.name, "the dossier counts the corrected figure", Number(counted.split("·")[1]) === figureCount + 1, counted);
    await page.getByRole("link", { name: `${rejectedName}: ${asWritten} MAD m`, exact: false }).first().scrollIntoViewIfNeeded();
    await shot("17-dossier-corrected");
    await page.goto(`${base}/checks?status=done`);
    await rowNamed("Corrected").getByRole("button", { name: "REOPEN" }).click();
    await rowNamed("Needs review").waitFor();
    check(vp.name, "a reopened correction needs review again", true);

    // MAP and KPIs show their empty states.
    for (const [path, title] of [
      ["map", "The map arrives with entities and facts"],
      ["kpis", "KPIs follow checked figures"],
    ]) {
      await page.goto(`${base}/${path}`);
      const heading = page.getByRole("heading", { name: title });
      await heading.waitFor();
      check(vp.name, `${path.toUpperCase()} empty state`, await heading.isVisible());
      await shot(`15-empty-${path}`);
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
