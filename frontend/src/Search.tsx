import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";

const ICON = (
  <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" className="search-glyph">
    <circle cx="7" cy="7" r="4.8" />
    <path d="M10.6 10.6L14 14" />
  </svg>
);

/** The query in the address bar when the results page is open. */
export function useQuery(): string {
  const { pathname, search } = useLocation();
  return pathname === "/search" ? (new URLSearchParams(search).get("q") ?? "") : "";
}

/** The search field: Enter opens the results page; "/" focuses it from anywhere. */
export function SearchField({ id, autoFocus = false }: { id: string; autoFocus?: boolean }) {
  const navigate = useNavigate();
  const query = useQuery();
  const [draft, setDraft] = useState(query);
  const [shown, setShown] = useState(query);
  // Back and forward change the query in the address bar: show it.
  if (shown !== query) {
    setShown(query);
    setDraft(query);
  }
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const q = draft.trim();
    if (q) navigate(`/search?q=${encodeURIComponent(q)}`);
  };
  return (
    <form className="search" role="search" onSubmit={submit}>
      <label htmlFor={id} className="visually-hidden">
        Search the filings
      </label>
      {ICON}
      <input
        id={id}
        type="search"
        autoComplete="off"
        enterKeyHint="search"
        placeholder="Search the filings…"
        value={draft}
        autoFocus={autoFocus}
        onChange={(event) => setDraft(event.target.value)}
      />
      <kbd className="search-key" aria-hidden="true">
        /
      </kbd>
    </form>
  );
}

/** The header's search: a field, or on a phone an icon that opens the results page. */
export function HeaderSearch() {
  const field = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      if ((event.target as HTMLElement).closest("input, textarea, select, [contenteditable]")) return;
      const input = field.current?.querySelector("input");
      if (!input || input.offsetParent === null) return;
      event.preventDefault();
      input.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <>
      <div className="header-search" ref={field}>
        <SearchField id="header-search" />
      </div>
      <Link className="search-icon" to="/search" aria-label="Search the filings">
        {ICON}
      </Link>
    </>
  );
}
