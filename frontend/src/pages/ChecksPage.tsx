import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { ApiError } from "../ApiError";
import {
  api,
  pageImageUrl,
  type Candidate,
  type CheckGroup,
  type CheckQueue,
  type CheckRow,
  type CheckStatus,
  type PageInfo,
  type Passage,
  type Verdict,
} from "../api/client";
import { useApi } from "../api/useApi";
import { capitalised, periodLabel } from "../figures";
import { DOC_TYPE_LABELS, formatDate } from "../format";

type Filter = "open" | "needs_review" | "done" | "all";

type Option = { id: Filter; label: string; shows: CheckStatus[] };

const OPEN: Option = {
  id: "open",
  label: "OPEN",
  shows: ["to_check", "rejected"],
};
const FILTERS: Option[] = [
  OPEN,
  { id: "needs_review", label: "NEEDS REVIEW", shows: ["rejected"] },
  { id: "done", label: "DONE", shows: ["accepted", "corrected"] },
  {
    id: "all",
    label: "ALL",
    shows: ["to_check", "rejected", "accepted", "corrected"],
  },
];

const STATUS: Record<CheckStatus, { word: string; tone: string }> = {
  to_check: { word: "To check", tone: "pending" },
  rejected: { word: "Needs review", tone: "review" },
  accepted: { word: "Accepted", tone: "ok" },
  corrected: { word: "Corrected", tone: "ok" },
};

/** CHECKS (#23): the figures that feed a KPI or screen, for a person to accept or correct. */
export function ChecksPage() {
  const [params, setParams] = useSearchParams();
  const isin = params.get("company");
  const filter = FILTERS.find((f) => f.id === params.get("status")) ?? OPEN;
  // Bumped after every check, so the queue and its counts reload.
  const [version, setVersion] = useState(0);
  // Rows checked on this visit stay where they were until the filter changes.
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const queue = useApi(`checks:${isin}:${version}`, () =>
    api.GET("/api/checks", {
      params: { query: isin ? { isin } : {} },
    }),
  );

  const choose = (next: { company?: string | null; status?: Filter }) => {
    const company = next.company === undefined ? isin : next.company;
    const status = next.status ?? filter.id;
    setTouched(new Set());
    setParams({
      ...(company ? { company } : {}),
      ...(status !== "open" ? { status } : {}),
    });
  };

  return (
    <section className="page checks" aria-labelledby="checks-title">
      <div className="checks-head">
        <div>
          <div className="micro">CHECKS · WHAT THE EXTRACTOR NEEDS AN ANALYST TO CONFIRM</div>
          <h1 id="checks-title" className="page-title">
            Checks
          </h1>
          <p className="checks-intro">
            Each figure that feeds a KPI or a Sharia screen sits next to the source it came from. Accept it,
            or correct it before it counts.
          </p>
        </div>
        {queue.state === "ready" && <Counts queue={queue.data} />}
      </div>

      {queue.state === "loading" && <div className="skeleton checks-skeleton" aria-busy="true" />}
      {queue.state === "error" && <ApiError title="The checks could not be loaded" message={queue.message} />}
      {queue.state === "ready" && (
        <>
          <Reviewer name={queue.data.reviewer} />
          <div className="figures-bar">
            <div role="group" aria-label="Company" className="segmented">
              <button type="button" aria-pressed={!isin} onClick={() => choose({ company: null })}>
                ALL COMPANIES
              </button>
              {queue.data.companies.map((c) => (
                <button
                  key={c.isin}
                  type="button"
                  aria-pressed={c.isin === isin}
                  onClick={() => choose({ company: c.isin })}
                >
                  {c.name.toUpperCase()}
                </button>
              ))}
            </div>
            <div role="group" aria-label="Status" className="segmented">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  aria-pressed={f.id === filter.id}
                  onClick={() => choose({ status: f.id })}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <Groups
            queue={queue.data}
            shows={(row) => filter.shows.includes(row.status) || touched.has(rowKey(row))}
            onChecked={(row) => {
              setTouched((previous) => new Set(previous).add(rowKey(row)));
              setVersion((v) => v + 1);
            }}
          />
        </>
      )}
    </section>
  );
}

function Counts({ queue }: { queue: CheckQueue }) {
  const counts: [number, string, string][] = [
    [queue.counts.to_check, "TO CHECK", "pending"],
    [queue.counts.rejected, "NEEDS REVIEW", "review"],
    [queue.counts.done, "DONE", "ok"],
  ];
  return (
    <dl className="checks-counts">
      {counts.map(([n, label, tone]) => (
        <div key={label} data-tone={tone}>
          <dd className="num">{n}</dd>
          <dt>{label}</dt>
        </div>
      ))}
    </dl>
  );
}

function Reviewer({ name }: { name: string | null }) {
  if (name) {
    return (
      <p className="checks-reviewer">
        Checks are recorded as <strong>{name}</strong>.
      </p>
    );
  }
  return (
    <p className="checks-reviewer" data-missing role="status">
      Checks can't be recorded yet: set <code>REVIEWER</code> in <code>.env</code> to your name, then restart
      the API.
    </p>
  );
}

function Groups({
  queue,
  shows,
  onChecked,
}: {
  queue: CheckQueue;
  shows: (row: CheckRow) => boolean;
  onChecked: (row: CheckRow) => void;
}) {
  const groups = queue.groups
    .map((group) => ({ ...group, shown: group.rows.filter(shows) }))
    .filter((group) => group.shown.length > 0);
  if (groups.length === 0) {
    const nothing = queue.groups.length === 0;
    return (
      <div className="state">
        <h2>{nothing ? "No figures to check" : "No figure matches these filters"}</h2>
        <p>
          {nothing
            ? "Figures that feed a KPI or a screen appear here once a filing is extracted."
            : "Choose another company or status to see the rest."}
        </p>
      </div>
    );
  }
  return (
    <>
      {groups.map((group) => (
        <Group
          key={group.document.id}
          group={group}
          rows={group.shown}
          canCheck={!!queue.reviewer}
          onChecked={onChecked}
        />
      ))}
    </>
  );
}

function Group({
  group,
  rows,
  canCheck,
  onChecked,
}: {
  group: CheckGroup;
  rows: CheckRow[];
  canCheck: boolean;
  onChecked: (row: CheckRow) => void;
}) {
  const { document } = group;
  const detail = useApi(`document:${document.id}`, () =>
    api.GET("/api/documents/{document_id}", {
      params: { path: { document_id: document.id } },
    }),
  );
  const pages = detail.state === "ready" ? detail.data.pages : [];
  const name = `${document.issuer.name} · ${DOC_TYPE_LABELS[document.doc_type]} ${document.fiscal_year}`;
  return (
    <section className="check-group" aria-label={name}>
      <div className="check-group-head">
        <span>{name}</span>
        <span className="num micro">
          {rows.length} SHOWN OF {group.rows.length}
        </span>
      </div>
      <ul className="check-rows">
        {rows.map((row) => (
          <Row
            key={rowKey(row)}
            row={row}
            page={pages[(row.passage?.page ?? 0) - 1]}
            canCheck={canCheck}
            onChecked={() => onChecked(row)}
          />
        ))}
      </ul>
    </section>
  );
}

function Row({
  row,
  page,
  canCheck,
  onChecked,
}: {
  row: CheckRow;
  page: PageInfo | undefined;
  canCheck: boolean;
  onChecked: () => void;
}) {
  const [fixing, setFixing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const name = row.breakdown ? `${row.title}, ${capitalised(row.breakdown)}` : row.title;
  const status = STATUS[row.status];
  // A corrected row's parsed value is the correction's.
  const parsed = (row.status === "corrected" && row.review?.correction) || row;
  const done = row.status === "accepted" || row.status === "corrected";

  const send = async (fields: {
    verdict: Verdict;
    value_as_written?: string;
    cell_id?: string;
    quote?: string;
    quote_start?: number;
  }) => {
    setBusy(true);
    setError(null);
    const { error: refused, response } = await api.POST("/api/reviews", {
      body: { figure_ids: row.figure_ids, ...fields },
    });
    setBusy(false);
    if (response.ok) {
      setFixing(false);
      onChecked();
    } else {
      const detail = (refused as { detail?: unknown } | undefined)?.detail;
      setError(typeof detail === "string" ? detail : `${response.status} ${response.statusText}`);
    }
  };

  return (
    <li
      className="check-row"
      data-tone={status.tone}
      aria-label={`${name}, ${periodLabel(row)}: ${status.word}`}
    >
      <div className="check-what">
        <div className="micro">
          {row.document.issuer.name.toUpperCase()} · {periodLabel(row)}
        </div>
        <div className="check-name">{name}</div>
        <div className="check-sub">
          {row.basis_scope === "consolidated" ? "Consolidated · IFRS" : "Basis not read"}
        </div>
        <div className="check-sub check-feeds" title={`Feeds ${row.feeds.join(", ")}`}>
          Feeds {row.feeds.join(", ")}
        </div>
        {(row.conflict || row.sources > 1) && (
          <div className="check-flags">
            {row.conflict && (
              <span className="check-flag" data-tone="review">
                ≠ STATED DIFFERENTLY ELSEWHERE
              </span>
            )}
            {row.sources > 1 && <span className="check-flag">{row.sources} SOURCES AGREE</span>}
          </div>
        )}
      </div>

      <div className="check-value">
        <div className="micro">EXTRACTED</div>
        <div className="num check-number" data-struck={row.status === "corrected" || undefined}>
          {row.value_as_written}
        </div>
        {row.status === "corrected" && row.review?.correction && (
          <div className="num check-number check-fixed">→ {row.review.correction.value_as_written}</div>
        )}
        <div className="check-unit">{row.unit_as_written}</div>
      </div>

      <Source row={row} page={page} />

      <div className="check-value check-parsed-col">
        <div className="micro">PARSED</div>
        <div className="num check-parsed">{parsed.value ? grouped(parsed.value) : "–"}</div>
        <div className="check-unit">{parsed.value ? parsedUnit(parsed) : "not parsed"}</div>
      </div>

      <div className="check-act">
        <span className="check-status" data-tone={status.tone}>
          <StatusIcon status={row.status} />
          {status.word}
        </span>
        {done && row.review ? (
          <div className="check-done">
            <span>
              {row.status === "corrected" ? "Corrected" : "Accepted"} by {row.review.reviewer} on{" "}
              {formatDate(row.review.reviewed_at)}
            </span>
            {canCheck && (
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => send({ verdict: "reopened" })}
              >
                REOPEN
              </button>
            )}
          </div>
        ) : fixing ? (
          <Correction
            row={row}
            busy={busy}
            onSave={(fields) => send({ verdict: "corrected", ...fields })}
            onCancel={() => {
              setFixing(false);
              setError(null);
            }}
          />
        ) : (
          canCheck && (
            <div className="check-buttons">
              <button
                type="button"
                className="button button-signal"
                disabled={busy || row.rejected !== null}
                title={row.rejected ? "A rejected figure can only be corrected" : undefined}
                onClick={() => send({ verdict: "accepted" })}
              >
                ACCEPT
              </button>
              <button type="button" className="button" disabled={busy} onClick={() => setFixing(true)}>
                CORRECT
              </button>
            </div>
          )
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

/** The source rendered from the page, the cell or quote highlighted; it opens the viewer. */
function Source({ row, page }: { row: CheckRow; page: PageInfo | undefined }) {
  const passage = row.passage;
  if (!passage) {
    return (
      <div className="check-source check-nosource">
        <div className="micro">NO SOURCE ON THE PAGE</div>
        <p>
          {capitalised(row.rejected ?? "")}: the model cited no cell or paragraph of{" "}
          <Link to={`/documents/${row.document.id}?page=${row.page}`}>page {row.page}</Link>.
        </p>
      </div>
    );
  }
  // A rejected figure is a figure of the dossier only once corrected; until then, its page.
  const link =
    row.rejected === null || row.status === "corrected"
      ? `/documents/${row.document.id}?fact=${firstFigure(row)}`
      : `/documents/${row.document.id}?page=${passage.page}`;
  const what = passage.kind === "cell" ? "cell" : "quote";
  return (
    <div className="check-source">
      <Link
        to={link}
        className="check-crop-link"
        aria-label={`Open the ${what} on page ${passage.page} in the source viewer`}
      >
        {page ? (
          <Crop documentId={row.document.id} passage={passage} page={page} />
        ) : (
          <div className="check-crop" />
        )}
      </Link>
      <div className="check-source-meta micro">
        P. {passage.page} · {what === "cell" ? `CELL “${oneLine(passage.text)}”` : "QUOTE"}
        {row.rejected && <span className="check-reason"> · {row.rejected.toUpperCase()}</span>}
      </div>
    </div>
  );
}

const CROP_WIDTH = 260; // points of the page shown around the source
const CROP_HEIGHT = 64;

function Crop({ documentId, passage, page }: { documentId: string; passage: Passage; page: PageInfo }) {
  const [loaded, setLoaded] = useState(false);
  const boxes = passage.boxes.filter((b) => b.page === passage.page);
  const [box] = boxes;
  if (!box) return <div className="check-crop" />;
  const width = Math.min(CROP_WIDTH, page.width);
  const middle = (box.left + box.right) / 2;
  const left = clamp(middle - width / 2, 0, page.width - width);
  const top = clamp((box.top + box.bottom) / 2 - CROP_HEIGHT / 2, 0, page.height - CROP_HEIGHT);
  const pct = (points: number, of: number) => `${(100 * points) / of}%`;
  return (
    <div
      className="check-crop"
      data-loaded={loaded || undefined}
      style={{ aspectRatio: `${width} / ${CROP_HEIGHT}` }}
    >
      <div
        className="check-crop-page"
        style={{ width: pct(page.width, width), left: pct(-left, width), top: pct(-top, CROP_HEIGHT) }}
      >
        <img
          src={pageImageUrl(documentId, passage.page)}
          alt=""
          width={page.width}
          height={page.height}
          loading="lazy"
          onLoad={() => setLoaded(true)}
        />
        {/* Drawn with the page only: a highlight on a blank crop reads as a broken source. */}
        {loaded &&
          boxes.map((b, i) => (
            <span
              key={i}
              className="mark"
              aria-hidden="true"
              style={{
                left: pct(b.left, page.width),
                top: pct(b.top, page.height),
                width: pct(b.right - b.left, page.width),
                height: pct(b.bottom - b.top, page.height),
              }}
            />
          ))}
      </div>
    </div>
  );
}

function Correction({
  row,
  busy,
  onSave,
  onCancel,
}: {
  row: CheckRow;
  busy: boolean;
  onSave: (fields: {
    value_as_written?: string;
    cell_id?: string;
    quote?: string;
    quote_start?: number;
  }) => void;
  onCancel: () => void;
}) {
  const id = firstFigure(row);
  const [typed, setTyped] = useState(row.status === "corrected" ? "" : row.value_as_written);
  const choices = useApi(`candidates:${id}`, () =>
    api.GET("/api/figures/{figure_id}/candidates", {
      params: { path: { figure_id: id } },
    }),
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSave({ value_as_written: typed });
  };
  const pick = (c: Candidate) =>
    onSave(
      c.kind === "cell"
        ? { cell_id: c.cell_id ?? undefined }
        : { quote: c.value_as_written, quote_start: c.start ?? undefined },
    );
  const options =
    choices.state === "ready" ? choices.data.filter((c) => c.value_as_written !== row.value_as_written) : [];
  return (
    <div className="check-fix">
      {options.length > 0 && (
        <div
          role="group"
          aria-label={
            row.passage?.kind === "span" ? "Numbers in the same paragraph" : "Cells in the same row"
          }
        >
          <div className="micro">
            {row.passage?.kind === "span" ? "PICK FROM THE SAME PARAGRAPH" : "PICK FROM THE SAME ROW"}
          </div>
          <div className="check-picks">
            {options.map((c, i) => (
              <button
                key={c.cell_id ?? `${i}:${c.value_as_written}`}
                type="button"
                className="check-pick"
                disabled={busy}
                onClick={() => pick(c)}
              >
                <span className="num">{c.value_as_written}</span>
                <span className="check-pick-context">{c.context}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      <form onSubmit={submit}>
        <label htmlFor={`fix-${id}`} className="micro">
          OR TYPE IT · {row.unit_as_written.toUpperCase()}
        </label>
        <div className="check-fix-row">
          <input
            id={`fix-${id}`}
            className="num"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
          />
          <button type="submit" className="button button-signal" disabled={busy || !typed.trim()}>
            SAVE
          </button>
          <button type="button" className="button" onClick={onCancel}>
            CANCEL
          </button>
        </div>
      </form>
    </div>
  );
}

function StatusIcon({ status }: { status: CheckStatus }) {
  const inner =
    status === "to_check"
      ? "M8 4.8V8l2 1.4"
      : status === "rejected"
        ? "M6.3 6.3a1.75 1.75 0 1 1 2.5 1.6c-.5.25-.8.6-.8 1.1v.5M8 11.4v.2"
        : "M5.2 8.3l1.9 1.9 3.8-4.2";
  return (
    <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16">
      <path d="M8 1.5a6.5 6.5 0 1 1 0 13a6.5 6.5 0 1 1 0-13Z" />
      <path d={inner} />
    </svg>
  );
}

/** "36 681 000 000": a base-unit value with its thousands grouped, decimals kept. */
function grouped(value: string): string {
  const [whole = "", decimals] = value.split(".");
  const sign = whole.startsWith("-") ? "−" : "";
  const digits = whole.replace("-", "").replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${sign}${digits}${decimals ? `,${decimals}` : ""}`;
}

/** "MAD · ×1 000 000", or the unit alone when it is not scaled. */
function parsedUnit(parsed: { unit?: string | null; scale?: number | null }): string {
  const unit = parsed.unit === "MAD/share" ? "MAD per share" : (parsed.unit ?? "");
  return parsed.scale && parsed.scale > 1 ? `${unit} · ×${grouped(String(parsed.scale))}` : unit;
}

/** A row's figures name it: the queue lists each figure once. */
function rowKey(row: CheckRow): string {
  return row.figure_ids.join(",");
}

/** The figure a row opens in the viewer and asks candidates for: the one it shows. */
function firstFigure(row: CheckRow): string {
  return row.figure_ids[0] ?? "";
}

function oneLine(text: string): string {
  const line = text.split(/\s+/).join(" ");
  return line.length > 28 ? `${line.slice(0, 27)}…` : line;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max));
}
