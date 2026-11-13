import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export const api = createClient<paths>({ baseUrl: "" });

export type DocumentSummary = components["schemas"]["DocumentSummary"];
export type DocumentDetail = components["schemas"]["DocumentDetail"];
export type Chunk = components["schemas"]["Chunk"];
export type Figure = components["schemas"]["Figure"];
export type FigureDetail = components["schemas"]["FigureDetail"];
export type FactDetail = components["schemas"]["FactDetail"];
export type StatedFact = components["schemas"]["StatedFact"];
export type CompanyFacts = components["schemas"]["CompanyFacts"];
export type FactSection = components["schemas"]["FactSection"];
export type FactRow = components["schemas"]["FactRow"];
export type Party = components["schemas"]["Party"];
export type PartyKind = components["schemas"]["PartyKind"];
export type PartyRef = components["schemas"]["PartyRef"];
export type RejectedFact = components["schemas"]["RejectedFact"];
export type NameCheck = components["schemas"]["NameCheck"];
export type NameVerdict = components["schemas"]["NameVerdict"];
export type FigureGrid = components["schemas"]["FigureGrid"];
export type FigureRow = components["schemas"]["FigureRow"];
export type FigureValue = components["schemas"]["FigureValue"];
export type Scope = components["schemas"]["Scope"];
export type Box = components["schemas"]["Box"];
export type PageInfo = components["schemas"]["PageInfo"];
export type Passage = components["schemas"]["Passage"];
export type CheckQueue = components["schemas"]["CheckQueue"];
export type CheckGroup = components["schemas"]["CheckGroup"];
export type CheckRow = components["schemas"]["CheckRow"];
export type DividendCheck = components["schemas"]["DividendCheck"];
export type Candidate = components["schemas"]["Candidate"];
export type CheckStatus = components["schemas"]["CheckStatus"];
export type Verdict = components["schemas"]["Verdict"];
export type Listing = components["schemas"]["Listing"];
export type LastClose = components["schemas"]["LastClose"];
export type PricePoint = components["schemas"]["PricePoint"];
export type Scorecard = components["schemas"]["Scorecard"];
export type ScorecardKpi = components["schemas"]["ScorecardKpi"];
export type KpiInput = components["schemas"]["KpiInput"];
export type KpiStatus = components["schemas"]["KpiStatus"];
export type KpiDefinition = components["schemas"]["KpiDefinition"];
export type KpiDefinitions = components["schemas"]["KpiDefinitions"];

/** Why the API refused a request: its `detail`, else the HTTP status. */
export function refusal(error: unknown, response: Response): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" ? detail : `${response.status} ${response.statusText}`;
}

export function pageImageUrl(documentId: string, page: number): string {
  return `/api/documents/${encodeURIComponent(documentId)}/pages/${page}.png`;
}
