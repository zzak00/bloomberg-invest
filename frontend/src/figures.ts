import type { Figure, Scope } from "./api/client";

export const SCOPES: { scope: Scope; label: string }[] = [
  { scope: "consolidated", label: "CONSOLIDATED · IFRS" },
  { scope: "company-only", label: "COMPANY-ONLY · CGNC" },
];

const SCALES: Record<number, string> = { 1_000: " k", 1_000_000: " m", 1_000_000_000: " bn" };

/** "MAD m" for millions of dirhams as written, "%", "shares", "MAD per share". */
export function unitLabel({ unit, scale }: { unit: string; scale: number }): string {
  if (unit.endsWith("/share")) return `${unit.split("/")[0]} per share`;
  return `${unit}${SCALES[scale] ?? ""}`;
}

/** "FY2025" for a flow, "31.12.2025" for a balance. */
export function periodLabel(figure: Figure): string {
  if (!figure.as_of) return `FY${figure.fiscal_year}`;
  const [year, month, day] = figure.as_of.split("-");
  return `${day}.${month}.${year}`;
}

export function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
