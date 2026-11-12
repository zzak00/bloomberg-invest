import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import {
  api,
  type NameCheck,
  type NameVerdict,
  type PartyKind,
  type PartyRef,
  type RejectedFact,
} from "../api/client";
import { FACT_KIND_LABELS, PARTY_KIND_LABELS, sourceHref, sourceLine } from "../facts";
import { formatDate } from "../format";

/** The kinds a person can create a name as; the aggregates belong to their company. */
const NEW_KINDS = (Object.keys(PARTY_KIND_LABELS) as PartyKind[]).filter(
  (k) => k !== "free_float" && k !== "treasury_shares",
);

/** CHECKS Names (#24, S7b): each name no rule linked to exactly one Organisation or Person, with
 * the passage it was read from; a decision holds for every filing writing it. */
export function Names({
  names,
  parties,
  canCheck,
  onChecked,
}: {
  names: NameCheck[];
  parties: PartyRef[];
  canCheck: boolean;
  onChecked: () => Promise<void>;
}) {
  if (names.length === 0) {
    return (
      <div className="state">
        <h2>No names to check</h2>
        <p>Every name the facts write is linked to one Organisation or Person.</p>
      </div>
    );
  }
  return (
    <>
      <p className="checks-intro names-intro">
        Names the extractor couldn’t match to exactly one Organisation or Person. Pick the right one, create a
        new one, or mark the name as neither. The decision holds for every filing that writes it.
      </p>
      <ul className="check-rows names" aria-label="Names">
        {names.map((check) => (
          <Name key={check.alias} check={check} parties={parties} canCheck={canCheck} onChecked={onChecked} />
        ))}
      </ul>
    </>
  );
}

function Name({
  check,
  parties,
  canCheck,
  onChecked,
}: {
  check: NameCheck;
  parties: PartyRef[];
  canCheck: boolean;
  onChecked: () => Promise<void>;
}) {
  const [creating, setCreating] = useState(false);
  const [other, setOther] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const written = [...new Set(check.sources.map((s) => s.written))];
  const [first] = check.sources;
  const open = check.status === "to_check";

  const send = async (body: { verdict: NameVerdict; party_id?: string; name?: string; kind?: PartyKind }) => {
    setBusy(true);
    setError(null);
    const { error: refused, response } = await api.POST("/api/names/{key}/reviews", {
      params: { path: { key: check.alias } },
      body,
    });
    if (response.ok) {
      await onChecked();
      setCreating(false);
    } else {
      const detail = (refused as { detail?: unknown } | undefined)?.detail;
      setError(typeof detail === "string" ? detail : `${response.status} ${response.statusText}`);
    }
    setBusy(false);
  };

  const candidates = new Set(check.candidates.map((c) => c.id));
  return (
    <li
      className="name-row"
      data-tone={open ? "pending" : "ok"}
      aria-label={`${written.join(", ")}: ${STATUS[check.status]}`}
    >
      <div className="name-what">
        <div className="micro">NAME AS WRITTEN</div>
        <div className="name-written">{written.map((w) => `“${w}”`).join(", ")}</div>
        <div className="check-sub">
          Read as {check.name} · {PARTY_KIND_LABELS[check.kind]}
        </div>
        {first && (
          <>
            <Link className="name-source" to={sourceHref({ id: first.fact_id, document: first.document })}>
              {first.document.issuer.name} · {sourceLine(first)} · {FACT_KIND_LABELS[first.kind]} ↗
            </Link>
            <div className="name-passage">« {first.quote} »</div>
            {check.sources.length > 1 && (
              <div className="check-sub">
                Written in {check.sources.length} facts, on {pagesOf(check)}
              </div>
            )}
          </>
        )}
      </div>

      <div className="name-candidates">
        <div className="micro">{check.candidates.length > 0 ? "BEST CANDIDATES" : "NO CLOSE CANDIDATE"}</div>
        {check.candidates.map((candidate) => (
          <div key={candidate.id} className="name-candidate">
            <span>
              <span className="name-candidate-name">{candidate.name}</span>
              <span className="check-sub">{PARTY_KIND_LABELS[candidate.kind]}</span>
            </span>
            {open && canCheck && (
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => send({ verdict: "same_as", party_id: candidate.id })}
              >
                SAME AS
              </button>
            )}
          </div>
        ))}
        {open && canCheck && (
          <form
            className="name-other"
            onSubmit={(event: FormEvent) => {
              event.preventDefault();
              if (other) void send({ verdict: "same_as", party_id: other });
            }}
          >
            <label className="micro" htmlFor={`other-${check.alias}`}>
              ANOTHER ONE
            </label>
            <div className="name-other-row">
              <select id={`other-${check.alias}`} value={other} onChange={(e) => setOther(e.target.value)}>
                <option value="">Choose an Organisation or Person</option>
                {parties
                  .filter((p) => !candidates.has(p.id))
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {PARTY_KIND_LABELS[p.kind]}
                    </option>
                  ))}
              </select>
              <button type="submit" className="button" disabled={busy || !other}>
                SAME AS
              </button>
            </div>
          </form>
        )}
      </div>

      <div className="name-act">
        {open ? (
          canCheck &&
          (creating ? (
            <NewParty
              check={check}
              busy={busy}
              onSave={(fields) => send({ verdict: "new", ...fields })}
              onCancel={() => setCreating(false)}
            />
          ) : (
            <>
              <button type="button" className="button" disabled={busy} onClick={() => setCreating(true)}>
                NEW ORGANISATION OR PERSON
              </button>
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => send({ verdict: "not_a_party" })}
              >
                NEITHER
              </button>
            </>
          ))
        ) : (
          <div className="check-done">
            <span className="name-decision">
              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16">
                <path d="M8 1.5a6.5 6.5 0 1 1 0 13a6.5 6.5 0 1 1 0-13Z" />
                <path d="M5.2 8.3l1.9 1.9 3.8-4.2" />
              </svg>
              {decision(check)}
            </span>
            {check.review && (
              <span>
                by {check.review.reviewer} on {formatDate(check.review.reviewed_at)}
              </span>
            )}
            {canCheck && check.review && (
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => send({ verdict: "reopened" })}
              >
                UNDO
              </button>
            )}
          </div>
        )}
        {error && (
          <p className="check-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </li>
  );
}

const STATUS: Record<NameCheck["status"], string> = {
  to_check: "to check",
  resolved: "linked",
  not_a_party: "neither an Organisation nor a Person",
};

function decision(check: NameCheck): string {
  if (check.status === "not_a_party") return "Neither an Organisation nor a Person";
  if (!check.resolved) return "Linked";
  return check.review?.verdict === "new" ? `New: ${check.resolved.name}` : `Same as ${check.resolved.name}`;
}

function pagesOf(check: NameCheck): string {
  const pages = [...new Set(check.sources.map((s) => s.page))].sort((a, b) => a - b);
  return `${pages.length === 1 ? "p." : "pp."} ${pages.join(", ")}`;
}

/** A new Organisation or Person for the name: its name, as the dossier will show it, and its kind. */
function NewParty({
  check,
  busy,
  onSave,
  onCancel,
}: {
  check: NameCheck;
  busy: boolean;
  onSave: (fields: { name: string; kind: PartyKind }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(check.name);
  const [kind, setKind] = useState<PartyKind>(NEW_KINDS.find((k) => k === check.kind) ?? "company");
  return (
    <form
      className="name-new"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim()) onSave({ name: name.trim(), kind });
      }}
    >
      <label className="micro" htmlFor={`new-name-${check.alias}`}>
        NAME
      </label>
      <input id={`new-name-${check.alias}`} value={name} onChange={(e) => setName(e.target.value)} />
      <label className="micro" htmlFor={`new-kind-${check.alias}`}>
        KIND
      </label>
      <select
        id={`new-kind-${check.alias}`}
        value={kind}
        onChange={(e) => setKind(e.target.value as PartyKind)}
      >
        {NEW_KINDS.map((k) => (
          <option key={k} value={k}>
            {PARTY_KIND_LABELS[k]}
          </option>
        ))}
      </select>
      <div className="check-buttons">
        <button type="submit" className="button button-signal" disabled={busy || !name.trim()}>
          CREATE
        </button>
        <button type="button" className="button" disabled={busy} onClick={onCancel}>
          CANCEL
        </button>
      </div>
    </form>
  );
}

/** The facts the check refused (D2), with why: kept, never in the dossier. */
export function RejectedFacts({ facts }: { facts: RejectedFact[] }) {
  if (facts.length === 0) {
    return (
      <div className="state">
        <h2>No rejected facts</h2>
        <p>
          Every fact the extractor proposed quotes its passage and states only numbers the passage writes.
        </p>
      </div>
    );
  }
  return (
    <>
      <p className="checks-intro names-intro">
        Facts the extractor proposed that their own passage doesn’t bear out. They never reach the dossier; a
        re-run of <code>bloomberg facts</code> reads the page again.
      </p>
      <ul className="check-rows" aria-label="Rejected facts">
        {facts.map((fact) => (
          <li
            key={fact.id}
            className="rejected-row"
            aria-label={`${FACT_KIND_LABELS[fact.kind]}: ${fact.reason}`}
          >
            <div>
              <div className="micro">
                {fact.document.issuer.name.toUpperCase()} · {FACT_KIND_LABELS[fact.kind].toUpperCase()}
              </div>
              <div className="check-name">{fact.parties.map((p) => p.written).join(" · ") || "No name"}</div>
              <div className="check-sub num">{proposed(fact)}</div>
            </div>
            <div>
              <div className="rejected-reason">Rejected: {fact.reason}</div>
              <div className="name-passage">« {fact.quote} »</div>
            </div>
            <Link className="name-source" to={`/documents/${fact.document.id}?page=${fact.page}`}>
              {sourceLine(fact)} ↗
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

/** What the fact said, field by field: "percent 53 · as_of 2025-12-31". */
function proposed(fact: RejectedFact): string {
  return Object.entries(fact.values)
    .filter(([, value]) => value !== null && value !== "" && value !== false)
    .map(([key, value]) => `${key.replace(/_/g, " ")} ${String(value)}`)
    .join(" · ");
}
