import { Link } from "react-router";

import { ApiError } from "../ApiError";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { DOC_TYPE_LABELS, formatDateTime } from "../format";

export function IndexPage() {
  const documents = useApi("documents", () => api.GET("/api/documents"));
  const empty = documents.state === "ready" && documents.data.length === 0;
  const showTable = documents.state === "loading" || (documents.state === "ready" && !empty);

  return (
    <section className="page" aria-labelledby="index-title">
      <div className="micro">
        INDEX
        {documents.state === "ready" &&
          ` · ${documents.data.length} ${documents.data.length === 1 ? "FILING" : "FILINGS"}`}
      </div>
      <h1 id="index-title" className="page-title">
        Filings in the graph
      </h1>

      {documents.state === "error" && (
        <ApiError
          title="The filings could not be loaded"
          message={documents.message}
          hint="Check that the stack is running."
        />
      )}

      {empty && (
        <div className="state">
          <h2>No filings yet</h2>
          <p>
            Ingest an AMMC filing with <code>docker compose run --rm ingest</code> and it appears
            here.
          </p>
        </div>
      )}

      {showTable && (
        <div className="table">
          <div className="table-row table-head" aria-hidden="true">
            <div>COMPANY</div>
            <div>DOCUMENT</div>
            <div>YEAR</div>
            <div>PAGES</div>
            <div>INGESTED</div>
          </div>
          <ul className="table-body" aria-label="Filings">
            {documents.state === "loading" &&
              [0, 1].map((i) => <li key={i} className="skeleton" aria-hidden="true" />)}
            {documents.state === "ready" &&
              documents.data.map((doc) => (
                <li key={doc.id} className="table-row row-link">
                  <span>
                    <Link className="cell-name cell-link" to={`/companies/${doc.issuer.isin}`}>
                      {doc.issuer.name}
                    </Link>
                    <span className="cell-sub">{doc.issuer.isin}</span>
                  </span>
                  <span className="col-type">
                    {/* Covers the whole row: the row opens the filing, the name opens the dossier. */}
                    <Link
                      className="row-link-target"
                      to={`/documents/${doc.id}`}
                      aria-label={`${doc.issuer.name}, ${DOC_TYPE_LABELS[doc.doc_type]} FY${doc.fiscal_year}`}
                    >
                      {DOC_TYPE_LABELS[doc.doc_type]}
                    </Link>
                    <span className="cell-sub">{doc.regulator}</span>
                  </span>
                  <span className="cell-mono num">FY{doc.fiscal_year}</span>
                  <span className="cell-mono num">{doc.page_count} p.</span>
                  <span className="cell-mono num col-ingested">{formatDateTime(doc.ingested_at)}</span>
                </li>
              ))}
          </ul>
        </div>
      )}
    </section>
  );
}
