import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export const api = createClient<paths>({ baseUrl: "" });

export type DocumentSummary = components["schemas"]["DocumentSummary"];
export type DocumentDetail = components["schemas"]["DocumentDetail"];
export type Chunk = components["schemas"]["Chunk"];
export type Figure = components["schemas"]["Figure"];
export type FigureDetail = components["schemas"]["FigureDetail"];
export type FigureGrid = components["schemas"]["FigureGrid"];
export type FigureRow = components["schemas"]["FigureRow"];
export type FigureValue = components["schemas"]["FigureValue"];
export type Scope = components["schemas"]["Scope"];
export type Box = components["schemas"]["Box"];

export function pageImageUrl(documentId: string, page: number): string {
  return `/api/documents/${encodeURIComponent(documentId)}/pages/${page}.png`;
}
