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

const DATE = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });

/** "10/11/2026": a day in the app's French date format. */
export function formatDate(iso: string): string {
  return DATE.format(new Date(iso));
}

/** "10/11/2026" for a day written "2026-11-10": read as text, so no time zone moves it. */
export function formatDay(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

const PRICE = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** "91,70" for a close written "91.7". */
export function formatPrice(decimal: string): string {
  return PRICE.format(Number(decimal));
}

const PERCENT = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});

/** "+2,1 %" for a change written as the fraction "0.0212". */
export function formatChange(fraction: string): string {
  return `${PERCENT.format(Number(fraction) * 100)} %`;
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
