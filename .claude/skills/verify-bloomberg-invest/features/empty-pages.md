# Empty pages: MAP, CHECKS, KPIs

Placeholders until their slices land: the map (#25), the review queue (#23) and the KPI reference page (#27).

## Sub-features

- A micro-label, a heading, one paragraph saying what will appear, and an OPEN THE INDEX button.
- The tab is current in the top navigation.

## How to get to it (user POV)

Click MAP, CHECKS or KPIs in the top navigation.

## Driving it with Playwright

Go to `/map`, `/checks`, `/kpis`; proof is the heading by role: "The map arrives with entities and facts", "Nothing to check yet", "KPIs follow checked figures".

## Gotchas

- When a slice replaces one of these pages, update its journey step and this file in the same change.
