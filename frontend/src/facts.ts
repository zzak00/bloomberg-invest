import type { FactDetail, Party, PartyKind, StatedFact } from "./api/client";
import { DOC_TYPE_LABELS, formatDate, formatDay } from "./format";

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

/** What each kind of Organisation or Person is called in CHECKS Names. */
export const PARTY_KIND_LABELS: Record<PartyKind, string> = {
  company: "Company",
  holding: "Holding",
  state: "State body",
  pension_fund: "Pension fund",
  insurer: "Insurer",
  bank: "Bank",
  audit_firm: "Audit firm",
  person: "Person",
  free_float: "Free float",
  treasury_shares: "Treasury shares",
};

/** The fact in one line: "Société Alpha holds 53 % of Gamma". */
export function sentenceText(fact: Pick<FactDetail, "sentence">): string {
  const { before, value, after } = fact.sentence;
  return `${before}${value}${after}`;
}

/** The date a fact holds on: "31/12/2025" for an as-of date, "FY2025" for a fiscal year. */
export function whenLabel(fact: Pick<StatedFact, "as_of" | "fiscal_year">): string {
  return fact.as_of ? formatDay(fact.as_of) : `FY${fact.fiscal_year}`;
}

/** A party as the dossier names it: what it resolves to, else the name the extractor read. */
export function shownName(party: Party): string {
  return party.resolved?.name ?? party.name;
}

export function partyName(fact: StatedFact, role: string): string {
  const party = fact.parties.find((p) => p.role === role);
  return party ? shownName(party) : "";
}

/** A value a person kept (D5): its latest Review accepts it. */
export function isKept(fact: Pick<StatedFact, "review">): boolean {
  return fact.review?.verdict === "accepted";
}

/** "Consolidated" or "Company-only", for a kind with a basis. */
export function scopeLabel(fact: Pick<StatedFact, "values">): string | null {
  const scope = fact.values.basis_scope;
  if (!scope) return null;
  return scope === "consolidated" ? "Consolidated" : "Company-only";
}

/** A name no rule or person has linked yet: it waits in CHECKS Names. */
export function unresolved(party: Party): boolean {
  return party.resolved === null && !party.not_a_party;
}

const BODIES: Record<string, string> = {
  board: "Board",
  audit_committee: "Audit committee",
  other_committee: "Board committee",
  executive: "Executive team",
};

const METHODS: Record<string, string> = {
  full: "Full consolidation",
  equity: "Equity method",
  proportional: "Proportional",
};

/** A dossier row's first column: who the row is about, and what it says of them besides its value.
 * Ownership names the holder; Holdings, the company held. */
export function rowLabel(fact: StatedFact, section: string): { name: string; detail: string } {
  const text = (key: string) => {
    const value = fact.values[key];
    return value === null || value === undefined ? "" : String(value);
  };
  const scope = `${scopeLabel(fact) ?? "Company-only"} accounts`;
  switch (fact.kind) {
    case "shareholding":
      return {
        name: partyName(fact, section === "holdings" ? "held" : "holder"),
        detail: text("rights") === "voting" ? "Voting rights" : "Capital",
      };
    case "consolidation":
      return { name: partyName(fact, "subsidiary"), detail: METHODS[text("method")] ?? "" };
    case "board_seat":
      return { name: partyName(fact, "member"), detail: BODIES[text("body")] ?? "" };
    case "audit_mandate":
      return { name: partyName(fact, "auditor"), detail: scope };
    case "auditor_opinion":
      return {
        name: "Auditors' opinion",
        detail: fact.values.emphasis ? `${scope} · emphasis of matter` : scope,
      };
    case "dividend":
      return {
        name: text("measure") === "per_share" ? "Dividend per share" : "Total dividend",
        detail: text("status") === "proposed" ? "Proposed" : "Paid",
      };
    case "listing":
      return {
        name: partyName(fact, "exchange"),
        detail: [text("ticker"), text("compartment")].filter(Boolean).join(" · "),
      };
    case "related_party_agreement":
      return { name: partyName(fact, "counterparty"), detail: text("nature") };
  }
}

/** Why the dossier shows this value and not another at its date (#19 R8). */
export const WHY_LABELS: Record<NonNullable<FactDetail["why"]>, string> = {
  kept: "a person kept it",
  latest: "it is the latest",
  annual_report: "the annual report states it",
  earliest: "it was recorded first",
};

/** Where a fact is read: "Annual financial report FY2025, p. 27". */
export function sourceLine(fact: Pick<StatedFact, "document" | "page">): string {
  return `${DOC_TYPE_LABELS[fact.document.doc_type]} FY${fact.document.fiscal_year}, p. ${fact.page}`;
}

/** The evidence status line: who kept the value, that the values at its date disagree, or that
 * nobody checked it. */
export function reviewText(fact: StatedFact, disagreeing: "filings" | "passages" | null = null): string {
  if (fact.review && isKept(fact)) {
    return `Kept by ${fact.review.reviewer} on ${formatDate(fact.review.reviewed_at)}`;
  }
  if (disagreeing === "filings") return "Two filings disagree · needs review";
  if (disagreeing === "passages") return "Two passages of the filing disagree · needs review";
  return "Not checked";
}

/** The source viewer on the fact's passage. */
export function sourceHref(fact: Pick<StatedFact, "id" | "document">): string {
  return `/documents/${fact.document.id}?fact=${fact.id}`;
}
