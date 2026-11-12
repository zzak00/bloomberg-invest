import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { ApiError } from "../ApiError";
import { api, pageImageUrl, type Box, type Chunk, type FactDetail, type FigureDetail } from "../api/client";
import { useApi } from "../api/useApi";
import { FACT_KIND_LABELS, sentenceText } from "../facts";
import { periodLabel, unitLabel } from "../figures";
import { DOC_TYPE_LABELS, formatDate, formatDateTime, formatDay, pagesLabel } from "../format";

/** What the outline needs from a section. */
type Section = { id: string; title: string; page: number; children?: Section[] };

/** The source viewer: one filing, page by page, with its section outline. */
export function DocumentPage() {
  const { documentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const document = useApi(`document:${documentId}`, () =>
    api.GET("/api/documents/{document_id}", { params: { path: { document_id: documentId } } }),
  );
  // What a link asked to highlight: a search result's chunk, or a figure's cell or quote.
  const chunkId = params.get("chunk");
  const factId = chunkId ? null : params.get("fact");
  const chunk = useApi(
    `chunk:${chunkId}`,
    chunkId
      ? () => api.GET("/api/chunks/{chunk_id}", { params: { path: { chunk_id: chunkId } } })
      : null,
  );
  const fact = useApi(
    `fact:${factId}`,
    factId ? () => api.GET("/api/facts/{fact_id}", { params: { path: { fact_id: factId } } }) : null,
  );
  const target = chunkId ? chunk : fact;
  const firstMark = useRef<HTMLSpanElement>(null);
  // Bring the highlight into view once it is drawn: the page's size is known before its image
  // loads, so the position is already right.
  const drawn =
    document.state === "ready" && target.state === "ready"
      ? `${chunkId ?? factId}:${params.get("page")}`
      : "";
  useEffect(() => {
    if (drawn) firstMark.current?.scrollIntoView({ block: "center" });
  }, [drawn]);

  // A link to a chunk or a figure with no page: its page comes with it, so wait for it rather
  // than show page 1 first.
  const pageFromTarget = target.state === "loading" && !params.has("page");
  if (document.state === "loading" || pageFromTarget) {
    return (
      <div className="state" aria-busy="true">
        <div className="micro">LOADING THE FILING…</div>
      </div>
    );
  }
  if (document.state === "error") {
    return (
      <ApiError
        label="SOURCE"
        title="This filing could not be opened"
        message={document.message}
        action={
          <Link className="button" to="/index">
            BACK TO THE INDEX
          </Link>
        }
      />
    );
  }

  const doc = document.data;
  const highlighted =
    chunk.state === "ready" && chunk.data.document.id === doc.id
      ? chunkHighlight(chunk.data)
      : fact.state === "ready" && fact.data.document.id === doc.id
        ? factHighlight(fact.data)
        : null;
  const requested = Number(params.get("page") ?? highlighted?.pages[0] ?? "1");
  const page = Number.isInteger(requested) ? clamp(requested, 1, doc.page_count) : 1;
  // Paging keeps the highlight; picking a section leaves it.
  const goTo = (target: number) => {
    const next = String(clamp(target, 1, doc.page_count));
    setParams(highlighted ? { page: next, [highlighted.param]: highlighted.id } : { page: next });
  };
  const pick = (section: Section) => setParams({ page: String(section.page), section: section.id });
  const size = doc.pages[page - 1];
  const marks = highlighted && size ? highlighted.boxes.filter((box) => box.page === page) : [];
  const current = currentSection(doc.sections, page, params.get("section"));
  const title = `${doc.issuer.name} · ${DOC_TYPE_LABELS[doc.doc_type]} ${doc.fiscal_year}`;

  return (
    <div className="viewer">
      <Outline sections={doc.sections} current={current} onPick={pick} />
      <article className="paper" aria-label={`${title}, page ${page} of ${doc.page_count}`}>
        <div className="paper-bar">
          <span className="paper-label">SOURCE · {doc.regulator}</span>
          <span className="paper-title">{title}</span>
          <Pager key={page} page={page} total={doc.page_count} onGo={goTo} />
        </div>
        {highlighted && (
          <HighlightBar
            highlighted={highlighted}
            onPage={marks.length > 0}
            onGo={() => goTo(highlighted.pages[0] ?? page)}
            onClear={() => setParams({ page: String(page) })}
          />
        )}
        <div className="paper-scroll">
          <div className="paper-sheet">
            <img
              key={page}
              src={pageImageUrl(doc.id, page)}
              alt={`Page ${page} of ${title}`}
              width={size?.width}
              height={size?.height}
            />
            {size &&
              marks.map(({ left, top, right, bottom }, i) => (
                <span
                  key={`${page}-${i}`}
                  ref={i === 0 ? firstMark : undefined}
                  className="mark"
                  aria-hidden="true"
                  style={{
                    left: `${(100 * left) / size.width}%`,
                    top: `${(100 * top) / size.height}%`,
                    width: `${(100 * (right - left)) / size.width}%`,
                    height: `${(100 * (bottom - top)) / size.height}%`,
                  }}
                />
              ))}
          </div>
          <div className="paper-meta">
            Parsed by {doc.run.tool} {doc.run.tool_version}
            {doc.run.config.table_structure && ` (${doc.run.config.table_structure})`} ·{" "}
            <span className="nowrap">{formatDateTime(doc.run.finished_at)}</span>
          </div>
        </div>
      </article>
    </div>
  );
}

/** What the viewer highlights, from a chunk or a figure, and the link parameter that names it. */
interface Highlight {
  param: "chunk" | "fact";
  id: string;
  pages: number[];
  boxes: Box[];
  tag: string; // what kind of source it is
  name: string; // what it is
  detail?: string; // its value, for a figure
  title?: string; // the full section path, on hover
  check?: { text: string; done: boolean }; // a figure's check, when it needs or has one
}

function chunkHighlight(chunk: Chunk): Highlight {
  const path = chunk.section_path;
  return {
    param: "chunk",
    id: chunk.id,
    pages: chunk.pages,
    boxes: chunk.boxes,
    tag: "HIGHLIGHTED",
    name: path[path.length - 1] ?? "Before the first section",
    title: path.join(" › "),
  };
}

function factHighlight(fact: FigureDetail | FactDetail): Highlight {
  return fact.kind === "financial_figure" ? figureHighlight(fact) : statedHighlight(fact);
}

/** A fact of another kind (#24): its kind and date, its value, and the sentence it states. */
function statedHighlight(fact: FactDetail): Highlight {
  const when = fact.as_of ? formatDay(fact.as_of) : `FY${fact.fiscal_year}`;
  const review = fact.review;
  return {
    param: "fact",
    id: fact.id,
    pages: [fact.page],
    boxes: fact.passage.boxes,
    tag: fact.passage.kind === "cell" ? "CELL" : "QUOTE",
    name: `${FACT_KIND_LABELS[fact.kind]} · ${when}`,
    detail: fact.sentence.value,
    title: sentenceText(fact),
    check: review
      ? { text: `Kept by ${review.reviewer} on ${formatDate(review.reviewed_at)}`, done: true }
      : undefined,
  };
}

function figureHighlight(figure: FigureDetail): Highlight {
  const name = figure.breakdown ? `${figure.line_item_title}, ${figure.breakdown}` : figure.line_item_title;
  return {
    param: "fact",
    id: figure.id,
    pages: [figure.page],
    // A typed correction has no cell or quote to draw: the bar names the page it was read on.
    boxes: figure.passage?.boxes ?? [],
    tag: figure.passage ? (figure.passage.kind === "cell" ? "CELL" : "QUOTE") : "PAGE",
    name: `${name} · ${periodLabel(figure)}`,
    detail: `${figure.value_as_written} ${unitLabel(figure)}`,
    title: figure.label,
    check: checkLine(figure),
  };
}

/** Who checked the figure and when, or that it still needs a check (#23 AC4). */
function checkLine(figure: FigureDetail): Highlight["check"] {
  const review = figure.review;
  if (review) {
    // A corrected figure already shows the person's value.
    const what = review.verdict === "corrected" ? "Corrected" : "Checked";
    return { text: `${what} by ${review.reviewer} on ${formatDate(review.reviewed_at)}`, done: true };
  }
  return figure.needs_review ? { text: "Not checked yet", done: false } : undefined;
}

/** The highlight: what and where it is, a way back to it, and a way to clear it. */
function HighlightBar({
  highlighted,
  onPage,
  onGo,
  onClear,
}: {
  highlighted: Highlight;
  onPage: boolean;
  onGo: () => void;
  onClear: () => void;
}) {
  return (
    <div className="highlight-bar" role="status">
      <span className="highlight-bar-swatch" aria-hidden="true" />
      <span className="highlight-bar-where">
        <span className="paper-label">{highlighted.tag}</span>{" "}
        <span title={highlighted.title}>{highlighted.name}</span>{" "}
        {highlighted.detail && <span className="num nowrap highlight-bar-value">{highlighted.detail}</span>}{" "}
        <span className="num nowrap highlight-bar-pages">{pagesLabel(highlighted.pages)}</span>
        {highlighted.check && (
          <span className="highlight-bar-check" data-done={highlighted.check.done || undefined}>
            {highlighted.check.text}
          </span>
        )}
      </span>
      {!onPage && (
        <button type="button" className="button" onClick={onGo}>
          GO TO {pagesLabel(highlighted.pages).toUpperCase()} →
        </button>
      )}
      <button type="button" className="button" onClick={onClear}>
        CLEAR
      </button>
    </div>
  );
}

function Pager({ page, total, onGo }: { page: number; total: number; onGo: (page: number) => void }) {
  const [draft, setDraft] = useState(String(page));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const target = Number(draft);
    if (Number.isInteger(target)) onGo(target);
  };
  return (
    <form className="pager" onSubmit={submit}>
      <button type="button" className="button" onClick={() => onGo(page - 1)} disabled={page <= 1}>
        ← PREV
      </button>
      <label htmlFor="page-input" className="visually-hidden">
        Page number
      </label>
      <input
        id="page-input"
        inputMode="numeric"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => setDraft(String(page))}
      />
      <span className="pager-total num">/ {total}</span>
      <button type="button" className="button" onClick={() => onGo(page + 1)} disabled={page >= total}>
        NEXT →
      </button>
    </form>
  );
}

function Outline({
  sections,
  current,
  onPick,
}: {
  sections: Section[];
  current?: string;
  onPick: (section: Section) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <nav className="outline" aria-label="Sections" data-open={open}>
      <div className="outline-title micro">
        <span>SECTIONS</span>
        <button
          type="button"
          className="button outline-toggle"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? "HIDE" : "SHOW"}
        </button>
      </div>
      <div className="outline-tree">
        {sections.length === 0 ? (
          <p className="micro outline-empty">No headings found</p>
        ) : (
          <OutlineList sections={sections} current={current} onPick={onPick} />
        )}
      </div>
    </nav>
  );
}

function OutlineList({
  sections,
  current,
  onPick,
}: {
  sections: Section[];
  current?: string;
  onPick: (section: Section) => void;
}) {
  return (
    <ul>
      {sections.map((section) => (
        <li key={section.id}>
          <button type="button" aria-current={section.id === current} onClick={() => onPick(section)}>
            <span>{section.title}</span>
            <span className="outline-page num">{section.page}</span>
          </button>
          {section.children && section.children.length > 0 && (
            <OutlineList sections={section.children} current={current} onPick={onPick} />
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * The section to highlight: the one picked in the outline while its page is shown, otherwise
 * the last section, in reading order, that starts on or before the page.
 */
function currentSection(sections: Section[], page: number, picked: string | null): string | undefined {
  let found: string | undefined;
  let pickedOnPage = false;
  const visit = (nodes: Section[]) => {
    for (const node of nodes) {
      if (node.id === picked && node.page === page) pickedOnPage = true;
      if (node.page <= page) found = node.id;
      visit(node.children ?? []);
    }
  };
  visit(sections);
  return pickedOnPage ? (picked ?? undefined) : found;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
