# Chunks are the search unit, found by vector

Search returns Chunks, ranked by the cosine similarity of their embedded index text (section path and pages, then the Chunk's text, tables one line per row) to the query, with `Qwen3-Embedding-0.6B` run locally. Paragraphs exist only inside the chunker, as the units it never splits; they are not stored. We measured the options on the golden questions in `backend/notebooks/pipeline.ipynb`: a paragraph alone was often too short to rank (Q2's answer is a one-line list item under its lead-in), and over Chunks vector search beat hybrid with full-text on every score (evidence@5 0.59 against 0.45), because full-text favours long Chunks, mostly big tables, that repeat the question's words.

## Considered options

- **Paragraph search, hybrid full-text and vector (#19 R2, R15 as first written):** evidence@5 0.41, and Paragraph nodes multiplied the graph about fivefold for detail nothing read.
- **Hybrid over Chunks:** worse than vector alone, and it needs a full-text index and its French-analyzer question (#21 AC6) for nothing.
- **A reranker over the best 50:** evidence@5 0.47 on Paragraphs, but about 30 seconds per query on a laptop.
- **bge-m3:** better than Qwen3-0.6B as vector alone on Paragraphs (evidence@5 0.36 against 0.27), worse in hybrid (0.38 against 0.41); not measured on Chunks.
- **French query translation for full-text:** found the cited page more often (page@5 0.73 against 0.55) but not more evidence, for an LLM call per query.

## Consequences

- A search result and a highlight cover a whole Chunk (up to `CHUNK_CAP`, 2,000 tokens). Exact spans come with Passages, which Facts cite.
- The embedder reads 2,048 tokens of a Chunk; what is past that is not embedded. So no Chunk may be longer: text Chunks stay under `CHUNK_CAP`, and a table over `TABLE_CAP` (1,500 tokens, read one line per row) is split between rows, each part repeating the column header, rather than one table Chunk of up to 9,000 tokens whose end was never embedded. Raising the window instead was measured: about 5 seconds per 1,024 tokens on the container's CPU, and out of GPU memory on the Mac for the longest tables.
- The chunk caps and how a long section is split now decide what a result is. A long section splits at its numbered points, otherwise evenly; R2's split at the largest topic shift is not built yet (#TOPIC).
- The query must be embedded with the model the Chunks were: the API loads it at startup, and the embed Run records it. Changing the model means re-embedding every filing (`bloomberg embed`).
- An embed Run embeds every current Chunk of its Document at once and links to the Document, not to each Chunk; its config names the chunk Run it embedded.
- Exact-term lookups (an ISIN, a note number) are not served by search; they belong to the graph's own queries.
