import { Link } from "react-router";

import { ApiError } from "../ApiError";
import { api, type Chunk } from "../api/client";
import { useApi } from "../api/useApi";
import { DOC_TYPE_LABELS, pagesLabel, snippet } from "../format";
import { SearchField, useSearchQuery } from "../Search";

const LIMIT = 20;

/** Search results: the Chunks of every filing closest to the query in meaning. */
export function SearchPage() {
  const query = useSearchQuery().trim();
  const results = useApi(
    `search:${query}`,
    query ? () => api.GET("/api/search", { params: { query: { q: query, limit: LIMIT } } }) : null,
  );
  const count = results.state === "ready" ? results.data.length : 0;

  return (
    <section className="page" aria-labelledby="search-title">
      <div className="micro">
        SEARCH
        {query && results.state === "ready" && ` · ${count} ${count === 1 ? "RESULT" : "RESULTS"}`}
      </div>
      <h1 id="search-title" className="page-title">
        {query ? `“${query}”` : "Search the filings"}
      </h1>
      <div className="page-search">
        <SearchField id="page-search" autoFocus={!query} />
      </div>

      {!query && (
        <div className="state">
          <p>
            Ask in English or French: the text closest in meaning comes first, from every filing
            in the graph.
          </p>
        </div>
      )}

      {results.state === "error" && (
        <ApiError
          title="Search failed"
          message={results.message}
          hint="Check that the stack is running."
        />
      )}

      {query && results.state === "ready" && count === 0 && (
        <div className="state">
          <h2>Nothing is searchable yet</h2>
          <p>
            Search reads the filings' embedded chunks. Ingest a filing with{" "}
            <code>docker compose run --rm ingest</code>, or embed one with{" "}
            <code>docker compose run --rm embed</code>.
          </p>
        </div>
      )}

      {query && results.state !== "error" && count + (results.state === "loading" ? 1 : 0) > 0 && (
        <ol className="results" aria-label="Results" aria-busy={results.state === "loading"}>
          {results.state === "loading" &&
            [0, 1, 2].map((i) => <li key={i} className="skeleton result-skeleton" aria-hidden="true" />)}
          {results.state === "ready" && results.data.map((chunk) => <Result key={chunk.id} chunk={chunk} />)}
        </ol>
      )}
    </section>
  );
}

function Result({ chunk }: { chunk: Chunk }) {
  const doc = chunk.document;
  const where = `${doc.issuer.name} · ${DOC_TYPE_LABELS[doc.doc_type]} ${doc.fiscal_year}`;
  const path = chunk.section_path;
  const parent = path.length > 1 ? `${path.length > 2 ? "… › " : ""}${path[path.length - 2]} › ` : "";
  return (
    <li>
      <Link
        className="result"
        to={`/documents/${doc.id}?page=${chunk.pages[0]}&chunk=${chunk.id}`}
      >
        <span className="result-meta">
          <span>{where}</span>
          <span className="num nowrap">{pagesLabel(chunk.pages)}</span>
          <span className="result-kind">{kindLabel(chunk)}</span>
        </span>
        <span className="result-path" title={path.join(" › ")}>
          <span className="result-path-parent">{parent}</span>
          {path[path.length - 1] ?? "Before the first section"}
        </span>
        <span className="result-text">{snippet(chunk)}</span>
      </Link>
    </li>
  );
}

/** "TEXT", "TABLE", or for a part of a long table "TABLE · PART 2 OF 3". */
function kindLabel(chunk: Chunk): string {
  if (chunk.kind === "text") return "TEXT";
  const t = chunk.table;
  return t && t.parts > 1 ? `TABLE · PART ${t.part} OF ${t.parts}` : "TABLE";
}
