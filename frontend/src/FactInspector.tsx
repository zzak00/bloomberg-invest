import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { ApiError } from "./ApiError";
import { api, type FactDetail, type Party } from "./api/client";
import { useApi } from "./api/useApi";
import {
  FACT_KIND_LABELS,
  WHY_LABELS,
  reviewText,
  sourceHref,
  sourceLine,
  unresolved,
  whenLabel,
} from "./facts";
import { formatDate, formatDay } from "./format";

/** The fact inspector (#24 AC4, S3): one fact in a sentence, its details, its evidence and
 * quote; for a Conflict (S3b), every value at its date side by side, with Keep and Undo (D5). */
export function FactInspector({
  factId,
  onClose,
  onChanged,
}: {
  factId: string;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const fact = useApi(`fact:${factId}`, () =>
    api.GET("/api/facts/{fact_id}", { params: { path: { fact_id: factId } } }),
  );
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    panel.current?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [factId, onClose]);

  const kind = fact.state === "ready" && fact.data.kind !== "financial_figure" ? fact.data.kind : null;
  return (
    <aside ref={panel} className="inspector" role="dialog" aria-label="Fact inspector" tabIndex={-1}>
      <div className="inspector-head">
        <span className="micro">FACT{kind ? ` · ${FACT_KIND_LABELS[kind].toUpperCase()}` : ""}</span>
        <button
          type="button"
          className="inspector-close"
          onClick={onClose}
          aria-label="Close inspector (Escape)"
        >
          ESC
          <svg aria-hidden="true" width="10" height="10" viewBox="0 0 10 10">
            <path d="M1.5 1.5l7 7M8.5 1.5l-7 7" />
          </svg>
        </button>
      </div>
      {fact.state === "loading" && <div className="skeleton inspector-skeleton" aria-busy="true" />}
      {fact.state === "error" && <ApiError title="This fact could not be opened" message={fact.message} />}
      {fact.state === "ready" &&
        (fact.data.kind === "financial_figure" ? (
          <div className="inspector-body">
            <Link className="button" to={`/documents/${fact.data.document.id}?fact=${fact.data.id}`}>
              OPEN SOURCE →
            </Link>
          </div>
        ) : fact.data.sides.length > 1 ? (
          <Conflict
            fact={fact.data}
            onChanged={async () => {
              await Promise.all([fact.reload(), onChanged()]);
            }}
          />
        ) : (
          <Single fact={fact.data} />
        ))}
    </aside>
  );
}

function Single({ fact }: { fact: FactDetail }) {
  const kept = fact.review?.verdict === "accepted";
  return (
    <div className="inspector-body">
      <Sentence fact={fact} />
      <dl className="inspector-details">
        {details(fact).map(([key, value]) => (
          <div key={key}>
            <dt className="micro">{key}</dt>
            <dd className="num">{value}</dd>
          </div>
        ))}
      </dl>
      <Parties parties={fact.parties} />
      <div className="inspector-status" data-tone={kept ? "ok" : undefined}>
        <span className="inspector-status-line" aria-hidden="true" />
        <span>{reviewText(fact, false)}</span>
        <span className="inspector-status-source">{sourceLine(fact)}</span>
      </div>
      <blockquote className="inspector-quote">
        <span className="inspector-quote-head">
          {fact.passage.kind === "cell" ? "TABLE CELL" : "QUOTE"} · P. {fact.page}
        </span>
        « {fact.quote} »
      </blockquote>
      <div className="inspector-open">
        <span>Opens the filing page with the passage highlighted.</span>
        <Link className="button button-outline-signal" to={sourceHref(fact)}>
          OPEN SOURCE →
        </Link>
      </div>
    </div>
  );
}

const LETTERS = "ABCDEFGH";

function Conflict({ fact, onChanged }: { fact: FactDetail; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // In reading order, so a side keeps its letter when another is kept.
  const sides = [...fact.sides].sort(
    (a, b) =>
      a.fact.document.id.localeCompare(b.fact.document.id) ||
      a.fact.page - b.fact.page ||
      a.fact.id.localeCompare(b.fact.id),
  );
  const kept = sides.find((s) => s.fact.review?.verdict === "accepted");
  const shown = Math.max(
    0,
    sides.findIndex((s) => s.in_use),
  );
  const filings = new Set(sides.map((s) => s.fact.document.id)).size;

  const review = async (factId: string, verdict: "accepted" | "reopened") => {
    setBusy(true);
    setError(null);
    const { error: refused, response } = await api.POST("/api/facts/{fact_id}/reviews", {
      params: { path: { fact_id: factId } },
      body: { verdict },
    });
    if (response.ok) {
      await onChanged();
    } else {
      const detail = (refused as { detail?: unknown } | undefined)?.detail;
      setError(typeof detail === "string" ? detail : `${response.status} ${response.statusText}`);
    }
    setBusy(false);
  };

  return (
    <div className="inspector-body">
      <div className="inspector-conflict-head">
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16">
          <path d="M8 1.5a6.5 6.5 0 1 1 0 13a6.5 6.5 0 1 1 0-13Z" />
          <path d="M6.3 6.3a1.75 1.75 0 1 1 2.5 1.6c-.5.25-.8.6-.8 1.1v.5M8 11.4v.2" />
        </svg>
        {sides.length === 2 ? "TWO" : sides.length} {filings > 1 ? "FILINGS" : "PASSAGES OF ONE FILING"}{" "}
        DISAGREE
      </div>
      <p className="inspector-sentence">
        {fact.sentence.before}
        {sides.length === 2 ? (
          sides.map((side, i) => (
            <span key={side.fact.id}>
              {i > 0 && " or "}
              <span className="num inspector-value" data-side={side.in_use ? "shown" : "other"}>
                {side.sentence.value}
              </span>
            </span>
          ))
        ) : (
          <span className="num inspector-value" data-side="other">
            one of {sides.length} values
          </span>
        )}
        {fact.sentence.after}
      </p>
      <ul className="inspector-sides" aria-label="Values at this date">
        {sides.map((side, i) => {
          const tag = kept ? (side === kept ? "IN USE" : "SET ASIDE") : side.in_use ? "SHOWN" : "";
          return (
            <li key={side.fact.id} className="inspector-side" data-in-use={side.in_use || undefined}>
              <div className="inspector-side-head">
                <span>
                  {filings > 1 ? "FILING" : "PASSAGE"} {LETTERS[i]}
                </span>
                <span className="inspector-side-tag">{tag}</span>
              </div>
              <div className="num inspector-side-value">{side.sentence.value}</div>
              <div className="inspector-side-source">{sourceLine(side.fact)}</div>
              <div className="inspector-side-meta num">
                {whenLabel(side.fact)} · recorded {formatDate(side.fact.recorded_at)}
                {side.sources > 1 && ` · ${side.sources} sources`}
              </div>
              <div className="inspector-side-quote">« {side.fact.quote} »</div>
              <Link className="button" to={sourceHref(side.fact)}>
                OPEN SOURCE →
              </Link>
            </li>
          );
        })}
      </ul>
      {kept ? (
        <div className="inspector-kept" role="status">
          <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16">
            <path d="M8 1.5a6.5 6.5 0 1 1 0 13a6.5 6.5 0 1 1 0-13Z" />
            <path d="M5.2 8.3l1.9 1.9 3.8-4.2" />
          </svg>
          <span>
            Kept {LETTERS[sides.indexOf(kept)]} · {kept.sentence.value} · by {kept.fact.review?.reviewer} on{" "}
            {kept.fact.review && formatDate(kept.fact.review.reviewed_at)}
          </span>
          <button
            type="button"
            className="inspector-undo"
            disabled={busy}
            onClick={() => review(kept.fact.id, "reopened")}
          >
            UNDO
          </button>
        </div>
      ) : (
        <>
          <p className="inspector-note">
            The dossier shows {LETTERS[shown]}
            {sides[shown]?.fact.id === fact.id && fact.why ? `, because ${WHY_LABELS[fact.why]}` : ""}. Keep
            one to settle it.
          </p>
          <div className="inspector-keep">
            {sides.map((side, i) => (
              <button
                key={side.fact.id}
                type="button"
                className={i === shown ? "button button-signal" : "button"}
                disabled={busy}
                onClick={() => review(side.fact.id, "accepted")}
              >
                KEEP {LETTERS[i]} · {side.sentence.value}
              </button>
            ))}
          </div>
        </>
      )}
      {error && (
        <p className="check-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function Sentence({ fact }: { fact: FactDetail }) {
  return (
    <p className="inspector-sentence">
      {fact.sentence.before}
      <span className="num inspector-value" data-side="shown">
        {fact.sentence.value}
      </span>
      {fact.sentence.after}
    </p>
  );
}

/** Each party as the filing writes it, with what it links to, or that it waits in CHECKS. */
function Parties({ parties }: { parties: Party[] }) {
  return (
    <ul className="inspector-parties" aria-label="Names">
      {parties.map((party) => (
        <li key={`${party.role}:${party.alias}`}>
          <span className="micro">{party.role.replace(/_/g, " ").toUpperCase()}</span>
          <span>
            {party.resolved?.isin ? (
              <Link to={`/companies/${party.resolved.isin}`}>{party.resolved.name}</Link>
            ) : (
              (party.resolved?.name ?? party.name)
            )}
            {party.written !== (party.resolved?.name ?? party.name) && (
              <span className="inspector-written"> · written “{party.written}”</span>
            )}
            {unresolved(party) && (
              <Link className="inspector-unlinked" to="/checks?tab=names">
                not linked yet · CHECKS
              </Link>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** PERIOD or AS OF, BASIS where the kind has one, RECORDED and REVIEW. */
function details(fact: FactDetail): [string, string][] {
  const rows: [string, string][] = [];
  if (fact.as_of) rows.push(["AS OF", formatDay(fact.as_of)]);
  else rows.push(["PERIOD", `FY${fact.fiscal_year}`]);
  const scope = fact.values.basis_scope;
  if (scope) rows.push(["BASIS", scope === "consolidated" ? "Consolidated" : "Company-only"]);
  rows.push(["RECORDED", formatDate(fact.recorded_at)]);
  rows.push(["REVIEW", fact.review?.verdict === "accepted" ? "Kept" : "Not checked"]);
  return rows;
}
