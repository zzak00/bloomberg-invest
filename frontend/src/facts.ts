import type { FactDetail } from "./api/client";

/** What each kind of fact is called where the app names it. */
export const FACT_KIND_LABELS: Record<FactDetail["kind"], string> = {
  shareholding: "Shareholding",
  board_seat: "Board seat",
  audit_mandate: "Audit mandate",
  listing: "Listing",
  consolidation: "Consolidation",
  dividend: "Dividend",
  auditor_opinion: "Auditor opinion",
  related_party_agreement: "Related-party agreement",
};

/** The fact in one line: "Société Alpha holds 53 % of Gamma". */
export function sentenceText(fact: Pick<FactDetail, "sentence">): string {
  const { before, value, after } = fact.sentence;
  return `${before}${value}${after}`;
}
