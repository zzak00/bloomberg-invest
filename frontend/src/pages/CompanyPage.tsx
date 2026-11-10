import { Link, useParams, useSearchParams } from "react-router";

import { ApiError } from "../ApiError";
import {
  api,
  type DocumentSummary,
  type FigureGrid,
  type FigureRow,
  type FigureValue,
  type Scope,
} from "../api/client";
import { useApi } from "../api/useApi";
import { SCOPES, capitalised, unitLabel } from "../figures";
import { DOC_TYPE_LABELS, formatDateTime } from "../format";

type Tab = "figures" | "filings";

/** A company's dossier: its figures by statement and year, and its filings. */
export function CompanyPage() {
  const { isin = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const company = useApi(`company:${isin}`, () =>
    api.GET("/api/companies/{isin}", { params: { path: { isin } } }),
  );
  const figures = useApi(`figures:${isin}`, () =>
    api.GET("/api/companies/{isin}/figures", { params: { path: { isin } } }),
  );
  const tab: Tab = params.get("tab") === "filings" ? "filings" : "figures";
  const scope: Scope = params.get("basis") === "company-only" ? "company-only" : "consolidated";

  if (company.state === "loading") {
    return (
      <div className="state" aria-busy="true">
        <div className="micro">LOADING THE DOSSIER…</div>
      </div>
    );
  }
  if (company.state === "error") {
    return (
      <ApiError
        label="COMPANY"
        title="This company could not be opened"
        message={company.message}
        action={
          <Link className="button" to="/index">
            BACK TO THE INDEX
          </Link>
        }
      />
    );
  }

  const { issuer, documents } = company.data;
  const count = figures.state === "ready" ? figures.data.count : undefined;
  const tabs: { id: Tab; label: string }[] = [
    { id: "figures", label: count === undefined ? "FIGURES" : `FIGURES · ${count}` },
    { id: "filings", label: `FILINGS · ${documents.length}` },
  ];

  return (
    <section className="page dossier" aria-labelledby="company-title">
      <div className="micro">COMPANY · ISSUER</div>
      <div className="dossier-id">
        <span className="chip num">{issuer.isin}</span>
        <span className="dossier-id-note">AMMC filings</span>
      </div>
      <h1 id="company-title" className="page-title dossier-title">
        {issuer.name}
      </h1>

      <div role="tablist" aria-label="Dossier sections" className="tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setParams(t.id === "figures" ? {} : { tab: t.id })}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "filings" ? (
          <Filings documents={documents} />
        ) : figures.state === "loading" ? (
          <div className="skeleton figures-skeleton" aria-hidden="true" />
        ) : figures.state === "error" ? (
          <ApiError title="The figures could not be loaded" message={figures.message} />
        ) : figures.data.count === 0 ? (
          <div className="state">
            <h2>No figures extracted yet</h2>
            <p>
              Figures appear here once a filing is extracted with <code>bloomberg extract</code>, each
              checked against the cell it came from.
            </p>
          </div>
        ) : (
          <Figures
            grid={figures.data}
            scope={scope}
            onScope={(next) => setParams(next === "consolidated" ? {} : { basis: next })}
          />
        )}
      </div>
    </section>
  );
}

function Figures({
  grid,
  scope,
  onScope,
}: {
  grid: FigureGrid;
  scope: Scope;
  onScope: (scope: Scope) => void;
}) {
  const shown = grid.scopes.find((s) => s.scope === scope);
  const years = shown?.years ?? [];
  const groups = shown?.statements ?? [];
  return (
    <>
      <div className="figures-bar">
        <div role="group" aria-label="Basis" className="segmented">
          {SCOPES.map(({ scope: s, label }) => (
            <button key={s} type="button" aria-pressed={s === scope} onClick={() => onScope(s)}>
              {label}
            </button>
          ))}
        </div>
        <p className="figures-note">
          Values as written in the filing, each checked against its cell. Select one to see it on the
          page.
        </p>
      </div>
      {groups.length === 0 && (
        <div className="state">
          <h2>No {scope === "consolidated" ? "consolidated" : "company-only"} figures</h2>
          <p>The extracted filings state none on this basis.</p>
        </div>
      )}
      {groups.map((group) => (
        <section key={group.key} className="statement" aria-labelledby={`statement-${group.key}`}>
          <h2 id={`statement-${group.key}`} className="micro statement-title">
            {group.title}
          </h2>
          <table className="figures">
            <thead>
              <tr>
                <th scope="col">LINE ITEM</th>
                <th scope="col" className="figures-unit">
                  UNIT
                </th>
                {years.map((y) => (
                  <th key={y} scope="col" className="figures-year">
                    FY{y}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {group.rows.map((row) => (
                <Row key={`${row.line_item}·${row.currency}·${row.breakdown}`} row={row} years={years} />
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </>
  );
}

function Row({ row, years }: { row: FigureRow; years: number[] }) {
  const byYear = new Map(row.years.map((y) => [y.fiscal_year, y.values]));
  return (
    <tr data-breakdown={row.breakdown !== "" || undefined}>
      <th scope="row">{capitalised(row.breakdown) || row.title}</th>
      <td className="figures-unit">{unitLabel(row)}</td>
      {years.map((year) => {
        const values = byYear.get(year);
        return (
          <td key={year} className="figures-year" data-year={`FY${year}`}>
            {values ? (
              <span className="figure-values">
                {values.map((v, i) => (
                  <Value key={v.shown.id} value={v} row={row} year={year} conflict={i > 0} />
                ))}
              </span>
            ) : (
              <span className="figures-none" aria-label="No value">
                –
              </span>
            )}
          </td>
        );
      })}
    </tr>
  );
}

function Value({ value, row, year, conflict }: { value: FigureValue; row: FigureRow; year: number; conflict: boolean }) {
  const { shown, sources } = value;
  const unit = unitLabel(shown);
  const name = row.breakdown ? `${row.title}, ${capitalised(row.breakdown)}` : row.title;
  // A corrected value is the person's, not what was read (#19 R8).
  const corrected = shown.review?.verdict === "corrected";
  const meta = [corrected && "corrected", sources.length > 1 && `${sources.length} sources`]
    .filter(Boolean)
    .join(" · ");
  return (
    <span className="figure-value">
      {conflict && (
        <span className="figure-conflict" title="Another passage of the filing states a different value">
          ≠
        </span>
      )}
      <Link
        className="num"
        to={`/documents/${shown.document.id}?fact=${shown.id}`}
        aria-label={`${name}, FY${year}: ${shown.value_as_written} ${unit}${corrected ? ", corrected" : ""}, on page ${shown.page}`}
      >
        {shown.value_as_written}
        {unit !== unitLabel(row) && <span className="figure-unit-inline"> {unit}</span>}
      </Link>
      {meta && <span className="figure-sources">{meta}</span>}
    </span>
  );
}

function Filings({ documents }: { documents: DocumentSummary[] }) {
  return (
    <ul className="filings" aria-label="Filings">
      {documents.map((doc) => (
        <li key={doc.id}>
          <Link to={`/documents/${doc.id}`}>
            <span>
              {DOC_TYPE_LABELS[doc.doc_type]}
              <span className="cell-sub">{doc.regulator}</span>
            </span>
            <span className="cell-mono num">FY{doc.fiscal_year}</span>
            <span className="cell-mono num">{doc.page_count} p.</span>
            <span className="cell-mono num filings-ingested">{formatDateTime(doc.ingested_at)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
