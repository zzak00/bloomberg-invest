import type { DocumentSummary } from "./api/client";

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
