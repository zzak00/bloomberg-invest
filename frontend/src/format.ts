import type { Chunk, DocumentSummary } from "./api/client";

const DATE_TIME = new Intl.DateTimeFormat("fr-FR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** "03/11/2026 09:42", the app's French date format. */
export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso)).replace(",", "");
}

export const DOC_TYPE_LABELS: Record<DocumentSummary["doc_type"], string> = {
  annual_report: "Annual financial report",
  half_year_report: "Half-year financial report",
  issuer_page: "Issuer page",
};

/** "p. 10", or "pp. 68-69" for a chunk over several pages. */
export function pagesLabel(pages: number[]): string {
  const [first, last] = [pages[0], pages[pages.length - 1]];
  return first === last ? `p. ${first}` : `pp. ${first}-${last}`;
}

/** A chunk's text as one plain line: its own heading dropped, table rows as "a · b". */
export function snippet(chunk: Chunk): string {
  const heading = chunk.section_path[chunk.section_path.length - 1];
  // A later part of a split table repeats the header row: start at its own rows instead.
  const header =
    (chunk.table?.part ?? 1) > 1
      ? chunk.text.split("\n").find((line) => line.startsWith("|"))
      : undefined;
  const lines = chunk.text
    .split("\n")
    .map((line) => line.trim())
    .filter(
      (line) =>
        line && line !== heading && line !== header && !/^\|?[\s:|-]+\|?$/.test(line),
    )
    .map((line) =>
      line.startsWith("|")
        ? line
            .replace(/^\||\|$/g, "")
            .split("|")
            .map((cell) => cell.trim())
            .filter(Boolean)
            .join(" · ")
        : line,
    );
  return lines.join(" ");
}
