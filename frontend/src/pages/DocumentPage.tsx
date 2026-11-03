import { useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { ApiError } from "../ApiError";
import { api, pageImageUrl } from "../api/client";
import { useApi } from "../api/useApi";
import { DOC_TYPE_LABELS, formatDateTime } from "../format";

/** What the outline needs from a section. */
type Section = { id: string; title: string; page: number; children?: Section[] };

/** The source viewer: one filing, page by page, with its section outline. */
export function DocumentPage() {
  const { documentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const document = useApi(`document:${documentId}`, () =>
    api.GET("/api/documents/{document_id}", { params: { path: { document_id: documentId } } }),
  );

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
  const requested = Number(params.get("page") ?? "1");
  const page = Number.isInteger(requested) ? clamp(requested, 1, doc.page_count) : 1;
  const goTo = (target: number) => setParams({ page: String(clamp(target, 1, doc.page_count)) });
  const pick = (section: Section) => setParams({ page: String(section.page), section: section.id });
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
        <div className="paper-scroll">
          <div className="paper-sheet">
            <img
              key={page}
              src={pageImageUrl(doc.id, page)}
              alt={`Page ${page} of ${title}`}
              width={doc.pages[page - 1]?.width}
              height={doc.pages[page - 1]?.height}
            />
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
