# Source viewer

One filing page by page, rendered from the stored PDF, with the section outline built at parse time.

## Sub-features

- Page image from `/api/documents/{id}/pages/{n}.png`.
- PREV and NEXT, a page field (type a number, press Enter), `?page=N` in the URL.
- Up and Down scroll the page wherever focus is, except in a field; they stop at the page's top and bottom (#49).
- Outline: clicking a section jumps to its page and highlights it (amber bar); paging highlights the last section starting on or before the page.
- At 390 the outline folds behind SHOW / HIDE above the page.
- The line under the page names the parser, its version and the parse time (from the Run).

## How to get to it (user POV)

INDEX, then click a filing. Deep link: `/documents/{id}?page=54`.

## Driving it with Playwright

Wait for `getByRole("img", { name: /^Page 1 of/ })` and its load before the screenshot. `getByRole("button", { name: "NEXT →" })` pages on. In `getByRole("navigation", { name: "Sections" })`, click `getByRole("button", { name: /^NOTE 13\./ })`; proof is `#page-input` = 54, `aria-current="true"` on that button and the page-54 image loaded.

## Gotchas

- Several sections can start on the same page (NOTE 13 and NOTE 14 on p. 54): the clicked one stays highlighted via `?section=`.
- The URL updates before the new page renders; waiting on the old image's `complete` gives a stale screenshot.
