import { useCallback } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { ApiError } from "../ApiError";
import { FactInspector } from "../FactInspector";
import {
  api,
  type CompanyFacts,
  type DocumentSummary,
  type FactRow,
  type FigureGrid,
  type FigureRow,
  type FigureValue,
  type LastClose,
  type Listing,
  type PricePoint,
  type Scope,
} from "../api/client";
import { useApi } from "../api/useApi";
import { rowLabel, sentenceText, unresolved, whenLabel } from "../facts";
import { SCOPES, capitalised, unitLabel } from "../figures";
import { DOC_TYPE_LABELS, formatChange, formatDateTime, formatDay, formatPrice } from "../format";

const TABS = ["figures", "facts", "filings"] as const;
type Tab = (typeof TABS)[number];

/** A company's dossier: its figures by statement and year, its other facts by section, and its
 * filings. A fact opens in the inspector (`?fact=`). */
export function CompanyPage() {
  const { isin = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const company = useApi(`company:${isin}`, () =>
    api.GET("/api/companies/{isin}", { params: { path: { isin } } }),
  );
  const figures = useApi(`figures:${isin}`, () =>
    api.GET("/api/companies/{isin}/figures", { params: { path: { isin } } }),
  );
  const facts = useApi(`facts:${isin}`, () =>
    api.GET("/api/companies/{isin}/facts", { params: { path: { isin } } }),
  );
  const tab: Tab = TABS.find((t) => t === params.get("tab")) ?? "figures";
  const factId = params.get("fact");
  const closeFact = useCallback(() => {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.delete("fact");
      return next;
    });
  }, [setParams]);
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

  const { issuer, documents, listing, last_close } = company.data;
  const count = figures.state === "ready" ? figures.data.count : undefined;
  const factCount = facts.state === "ready" ? facts.data.count : undefined;
  const tabs: { id: Tab; label: string }[] = [
    { id: "figures", label: count === undefined ? "FIGURES" : `FIGURES · ${count}` },
    { id: "facts", label: factCount === undefined ? "FACTS" : `FACTS · ${factCount}` },
    { id: "filings", label: `FILINGS · ${documents.length}` },
  ];

  return (
    <section className="page dossier" aria-labelledby="company-title" data-inspecting={factId ? true : undefined}>
      <div className="micro">COMPANY · ISSUER</div>
      <div className="dossier-id">
        <span className="chip num">{issuer.isin}</span>
        {listing && <span className="chip num">{listing.ticker}</span>}
        <span className="dossier-id-note">{listing ? listing.sector : "AMMC filings"}</span>
      </div>
      <h1 id="company-title" className="page-title dossier-title">
        {issuer.name}
      </h1>
      {listing && <LastCloseBlock isin={isin} listing={listing} last={last_close ?? null} />}

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
        ) : tab === "facts" ? (
          facts.state === "loading" ? (
            <div className="skeleton figures-skeleton" aria-hidden="true" />
          ) : facts.state === "error" ? (
            <ApiError title="The facts could not be loaded" message={facts.message} />
          ) : (
            <Facts
              facts={facts.data}
              open={factId}
              onOpen={(id) => setParams({ tab: "facts", fact: id })}
            />
          )
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
      {factId && <FactInspector factId={factId} onClose={closeFact} onChanged={facts.reload} />}
    </section>
  );
}

/** The dossier's facts of the eight other kinds (#24 AC4): one row per value shown, by section. */
function Facts({
  facts,
  open,
  onOpen,
}: {
  facts: CompanyFacts;
  open: string | null;
  onOpen: (id: string) => void;
}) {
  if (facts.count === 0) {
    return (
      <div className="state">
        <h2>No facts extracted yet</h2>
        <p>
          Shareholders, board, auditors, dividends and the other facts appear here once a filing is read
          with <code>bloomberg facts</code>, each checked against the passage it quotes.
        </p>
      </div>
    );
  }
  return (
    <>
      <div className="figures-bar">
        <p className="figures-note">
          One row per value, the latest date first. Select a value to see its sentence, its source and any
          other value stated for that date.
        </p>
        {facts.unlinked > 0 && (
          <Link className="facts-unlinked" to="/checks?tab=names">
            {facts.unlinked} {facts.unlinked === 1 ? "fact waits" : "facts wait"} for a name to be checked ·
            CHECKS →
          </Link>
        )}
      </div>
      {facts.sections.map((section) => (
        <section key={section.key} className="statement" aria-labelledby={`facts-${section.key}`}>
          <h2 id={`facts-${section.key}`} className="micro statement-title">
            {section.title.toUpperCase()} · {section.rows.length}
          </h2>
          <table className="figures facts">
            <thead>
              <tr>
                <th scope="col">{COLUMNS[section.key] ?? "NAME"}</th>
                <th scope="col" className="facts-value">
                  VALUE
                </th>
                <th scope="col" className="facts-when">
                  DATE
                </th>
                <th scope="col" className="facts-mark">
                  REVIEW
                </th>
              </tr>
            </thead>
            <tbody>
              {section.rows.map((row) => (
                <FactLine
                  key={row.shown.id}
                  row={row}
                  section={section.key}
                  selected={[row.shown, ...row.sources, ...row.others.flat()].some((f) => f.id === open)}
                  onOpen={() => onOpen(row.shown.id)}
                />
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </>
  );
}

/** What each section's first column names. */
const COLUMNS: Record<string, string> = {
  ownership: "HOLDER",
  holdings: "COMPANY HELD",
  subsidiaries: "SUBSIDIARY",
  board: "MEMBER",
  auditors: "AUDITOR",
  dividends: "DIVIDEND",
  listings: "EXCHANGE",
  related_parties: "COUNTERPARTY",
};

function FactLine({
  row,
  section,
  selected,
  onOpen,
}: {
  row: FactRow;
  section: string;
  selected: boolean;
  onOpen: () => void;
}) {
  const fact = row.shown;
  const { name, detail } = rowLabel(fact, section);
  const kept = fact.review?.verdict === "accepted";
  const waiting = fact.parties.some(unresolved);
  const values = 1 + row.others.length;
  const disagree = row.conflict ? `, ${values} values disagree` : "";
  return (
    <tr className="facts-row" data-selected={selected || undefined} onClick={onOpen}>
      <th scope="row">
        <span className="facts-name">{name}</span>
        {detail && <span className="facts-detail">{detail}</span>}
      </th>
      <td className="facts-value">
        <button
          type="button"
          className="num"
          aria-label={`${sentenceText(row)}, ${whenLabel(fact)}${disagree}`}
          onClick={(event) => {
            event.stopPropagation();
            onOpen();
          }}
        >
          {row.sentence.value}
        </button>
        {row.sources.length > 1 && <span className="figure-sources">{row.sources.length} sources</span>}
      </td>
      <td className="facts-when num">{whenLabel(fact)}</td>
      <td className="facts-mark">
        {row.conflict ? (
          <span className="facts-flag" data-tone={kept ? "ok" : "review"}>
            {kept ? "KEPT" : "≠"} · {values} VALUES
          </span>
        ) : kept ? (
          <span className="facts-flag" data-tone="ok">
            KEPT
          </span>
        ) : waiting ? (
          <span className="facts-flag" title="A name in this fact waits in CHECKS · Names">
            NAME TO CHECK
          </span>
        ) : (
          <span className="figures-none" aria-label="Not checked">
            –
          </span>
        )}
        {row.kept_earlier && (
          <span
            className="facts-flag"
            title="A person kept a value at an earlier date; this later one replaces it"
          >
            REPLACES A KEPT VALUE
          </span>
        )}
      </td>
    </tr>
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
      {corrected && <span className="figure-sources">corrected</span>}
      {sources.length > 1 && <span className="figure-sources">{sources.length} sources</span>}
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

const SOURCES: Record<string, string> = {
  "bourse-casablanca": "Bourse de Casablanca",
  manual: "entered by hand",
};

/** The last close, its change from the session before, and three years of closes (#26). */
function LastCloseBlock({
  isin,
  listing,
  last,
}: {
  isin: string;
  listing: Listing;
  last: LastClose | null;
}) {
  const series = useApi(`prices:${isin}`, () =>
    api.GET("/api/companies/{isin}/prices", { params: { path: { isin } } }),
  );
  if (!last) {
    return (
      <div className="price" role="group" aria-label="Last close">
        <div className="price-text">
          <div className="price-meta">
            No closes yet for {listing.ticker}: run <code>bloomberg prices backfill</code>
          </div>
        </div>
      </div>
    );
  }
  const closes = series.state === "ready" ? series.data.closes : [];
  return (
    <div className="price" role="group" aria-label="Last close">
      <div className="price-text">
        <div className="price-line">
          <span className="micro">CLOSE</span>
          <span className="num price-close">
            {formatPrice(last.close)} {last.currency}
          </span>
          {last.change && <span className="num price-change">{formatChange(last.change)}</span>}
        </div>
        <div className="price-meta">
          <span className="keep">
            {formatDay(last.session)} · {SOURCES[last.source] ?? last.source} ·
          </span>{" "}
          <span className="keep">raw close, not adjusted for dividends</span>
        </div>
        <div className="price-note">History from {formatDay(last.history_start)}</div>
      </div>
      {closes.length > 1 && <PriceLine closes={closes} currency={last.currency} />}
    </div>
  );
}

const LINE = { width: 98, height: 24, pad: 2 };

/** Three years of closes as one line, scaled between the lowest and the highest. */
function PriceLine({ closes, currency }: { closes: PricePoint[]; currency: string }) {
  const values = closes.map((c) => Number(c.close));
  const [low, high] = [Math.min(...values), Math.max(...values)];
  const range = high - low || 1;
  const step = (LINE.width - 2 * LINE.pad) / (values.length - 1);
  const points = values
    .map((v, i) => {
      const x = LINE.pad + i * step;
      const y = LINE.height - LINE.pad - ((v - low) / range) * (LINE.height - 2 * LINE.pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const [first, last] = [closes[0], closes[closes.length - 1]];
  if (!first || !last) return null;
  const label =
    `Closes from ${formatDay(first.session)} to ${formatDay(last.session)}: ` +
    `${formatPrice(first.close)} to ${formatPrice(last.close)} ${currency}, ` +
    `low ${formatPrice(String(low))}, high ${formatPrice(String(high))}`;
  return (
    <svg
      className="price-chart"
      role="img"
      aria-label={label}
      width={LINE.width}
      height={LINE.height}
      viewBox={`0 0 ${LINE.width} ${LINE.height}`}
      preserveAspectRatio="none"
    >
      <polyline points={points} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
