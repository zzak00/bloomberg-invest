import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { ApiError } from "../ApiError";
import { api, pageImageUrl, type Chunk } from "../api/client";
import { useApi } from "../api/useApi";
import { DOC_TYPE_LABELS, formatDateTime, pagesLabel } from "../format";

/** What the outline needs from a section. */
type Section = { id: string; title: string; page: number; children?: Section[] };

/** The source viewer: one filing, page by page, with its section outline. */
export function DocumentPage() {
  const { documentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const document = useApi(`document:${documentId}`, () =>
    api.GET("/api/documents/{document_id}", { params: { path: { document_id: documentId } } }),
  );
  // The passage a search result opened, highlighted on its pages.
  const chunkId = params.get("chunk");
  const chunk = useApi(`chunk:${chunkId}`, () =>
    chunkId
      ? api.GET("/api/chunks/{chunk_id}", { params: { path: { chunk_id: chunkId } } })
      : Promise.resolve({ data: undefined, response: new Response(null, { status: 204 }) }),
  );
  const firstMark = useRef<HTMLSpanElement>(null);
  // Bring the highlight into view once it is drawn: the page's size is known before its image
  // loads, so the position is already right.
  const drawn = document.state === "ready" && chunk.state === "ready" ? `${chunkId}:${params.get("page")}` : "";
  useEffect(() => {
    if (drawn) firstMark.current?.scrollIntoView({ block: "center" });
  }, [drawn]);

  if (document.state === "loading") {
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
  const passage = chunk.state === "ready" && chunk.data.document.id === doc.id ? chunk.data : null;
  const requested = Number(params.get("page") ?? passage?.pages[0] ?? "1");
  const page = Number.isInteger(requested) ? clamp(requested, 1, doc.page_count) : 1;
  // Paging keeps the highlighted passage; picking a section leaves it.
  const goTo = (target: number) => {
    const next = String(clamp(target, 1, doc.page_count));
    setParams(chunkId ? { page: next, chunk: chunkId } : { page: next });
  };
  const pick = (section: Section) => setParams({ page: String(section.page), section: section.id });
  const size = doc.pages[page - 1];
  const marks = passage && size ? passage.boxes.filter((box) => box.page === page) : [];
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
        {passage && (
          <Passage
            passage={passage}
            onPage={marks.length > 0}
            onGo={() => goTo(passage.pages[0] ?? page)}
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

/** The highlighted passage: where it is, a way back to it, and a way to clear it. */
function Passage({
  passage,
  onPage,
  onGo,
  onClear,
}: {
  passage: Chunk;
  onPage: boolean;
  onGo: () => void;
  onClear: () => void;
}) {
  const path = passage.section_path;
  return (
    <div className="passage" role="status">
      <span className="passage-swatch" aria-hidden="true" />
      <span className="passage-where">
        <span className="paper-label">HIGHLIGHTED</span>{" "}
        <span title={path.join(" › ")}>{path[path.length - 1] ?? "Passage"}</span>{" "}
        <span className="num nowrap passage-pages">{pagesLabel(passage.pages)}</span>
      </span>
      {!onPage && (
        <button type="button" className="button" onClick={onGo}>
          GO TO {pagesLabel(passage.pages).toUpperCase()} →
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
