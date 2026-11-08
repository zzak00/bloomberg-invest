# Search

**Reach it:** type in the header's search field and press Enter ("/" focuses it from anywhere). On a phone the header shows a search icon instead; the results page has its own field.

**What it does:** `GET /api/search` embeds the query with the model the Chunks were embedded with (Qwen3-Embedding-0.6B) and returns the nearest current Chunks. The results page lists each with its filing, pages, section path, kind (text or table) and a snippet. A result opens the source viewer at `/documents/<id>?page=<n>&chunk=<chunk id>`: the viewer fetches the Chunk (`GET /api/chunks/<id>`) and draws its blocks' boxes on each of its pages as a marker highlight, with a bar naming the passage, GO TO its page when elsewhere, and CLEAR.

**Driven by `journey.mjs`:** "/" (or the icon at 390), "dividende proposé", Enter; the first result must be the p. 10 Dividende passage (#21 AC3); opening it must show page 10 with a highlight inside the page and the passage bar naming it.

**Proves it:** `05-search` shows the results with p. 10 Dividende first; `06-search-result` shows page 10 with the dividend paragraph marked.

**Needs:** the filing ingested with embeddings (`docker compose run --rm ingest`, or `embed <document id>` for a filing ingested before search). Without them the results page says nothing is searchable yet.
