import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export const api = createClient<paths>({ baseUrl: "" });

export type DocumentSummary = components["schemas"]["DocumentSummary"];
export type DocumentDetail = components["schemas"]["DocumentDetail"];
export type Chunk = components["schemas"]["Chunk"];

export function pageImageUrl(documentId: string, page: number): string {
  return `/api/documents/${encodeURIComponent(documentId)}/pages/${page}.png`;
}
