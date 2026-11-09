import type { Figure } from "./api/client";

export type Scope = Figure["basis_scope"];

export const SCOPES: { scope: Scope; label: string }[] = [
  { scope: "consolidated", label: "CONSOLIDATED · IFRS" },
  { scope: "company-only", label: "COMPANY-ONLY · CGNC" },
];

/** One value a line item takes in a year, and every Fact that states it. */
export interface FigureValue {
  value: string;
  shown: Figure; // the source a click opens: the earliest page stating it
  sources: Figure[];
}

/** A line item, or one breakdown of it, with its values by fiscal year. */
export interface FigureRow {
  key: string;
  lineItem: string;
  currency: string;
  title: string;
  breakdown: string;
  unit: string;
  years: Map<number, FigureValue[]>; // two values in a year: the filing disagrees with itself
}

export interface StatementGroup {
  key: string;
  title: string;
  rows: FigureRow[];
}

/**
 * The figures of one scope, as the dossier lists them: by statement, a row per line item in the
 * label map's order (its breakdowns after it), and a column per fiscal year, newest first. A
 * figure stated in another currency (the filing's euro tables) is a row of its own, not a
 * disagreement.
 */
export function groupFigures(
  figures: Figure[],
  statements: { key: string; title: string; line_items: string[] }[],
  scope: Scope,
): { years: number[]; groups: StatementGroup[] } {
  const chosen = figures.filter((f) => f.basis_scope === scope);
  const years = [...new Set(chosen.map((f) => f.fiscal_year))].sort((a, b) => b - a);
  const position = new Map(statements.flatMap((s) => s.line_items).map((item, i) => [item, i]));

  const rows = new Map<string, { statement: string; row: FigureRow; figures: Figure[] }>();
  for (const f of chosen) {
    const currency = f.currency ?? f.unit;
    const key = `${f.line_item}\u0000${currency}\u0000${f.breakdown}`;
    const entry = rows.get(key) ?? {
      statement: f.statement,
      row: {
        key,
        lineItem: f.line_item,
        title: f.line_item_title,
        breakdown: capitalised(f.breakdown),
        currency,
        unit: unitLabel(f),
        years: new Map(),
      },
      figures: [] as Figure[],
    };
    entry.figures.push(f);
    rows.set(key, entry);
  }
  for (const { row, figures: stated } of rows.values()) {
    for (const year of years) {
      const found = agreeing(stated.filter((f) => f.fiscal_year === year), row.unit);
      if (found.length > 0) row.years.set(year, found);
    }
  }

  // The filing's own currency first: the one most of its figures are in.
  const currencies = countOf(chosen.map((f) => f.currency ?? f.unit));
  const order = (a: FigureRow, b: FigureRow) =>
    (position.get(a.lineItem) ?? Infinity) - (position.get(b.lineItem) ?? Infinity) ||
    (currencies.get(b.currency) ?? 0) - (currencies.get(a.currency) ?? 0) ||
    Number(a.breakdown !== "") - Number(b.breakdown !== "") ||
    a.breakdown.localeCompare(b.breakdown);
  const groups = statements
    .map(({ key, title }) => ({
      key,
      title,
      rows: [...rows.values()].filter((r) => r.statement === key).map((r) => r.row).sort(order),
    }))
    .filter((g) => g.rows.length > 0);
  return { years, groups };
}

const SCALES: Record<number, string> = { 1_000: " k", 1_000_000: " m", 1_000_000_000: " bn" };

/** "MAD m" for millions of dirhams as written, "%", "shares", "MAD per share". */
export function unitLabel(figure: Figure): string {
  if (figure.unit.endsWith("/share")) return `${figure.unit.split("/")[0]} per share`;
  return `${figure.unit}${SCALES[figure.scale] ?? ""}`;
}

/** "FY2025" for a flow, "31.12.2025" for a balance. */
export function periodLabel(figure: Figure): string {
  if (!figure.as_of) return `FY${figure.fiscal_year}`;
  const [year, month, day] = figure.as_of.split("-");
  return `${day}.${month}.${year}`;
}

/**
 * The distinct values a line item takes in a year. Two figures agree when the coarser one is the
 * finer one rounded as written: "36,7" billions and "36 681" millions are one value, "6 969" and
 * "6 968" millions are two. Each value opens its earliest source in the row's unit.
 */
function agreeing(stated: Figure[], rowUnit: string): FigureValue[] {
  const groups: Figure[][] = [];
  for (const f of [...stated].sort((a, b) => precision(a) - precision(b))) {
    const group = groups.find((g) => {
      const finest = g[0];
      return finest !== undefined && Math.abs(Number(finest.value) - Number(f.value)) <= precision(f) / 2;
    });
    if (group) group.push(f);
    else groups.push([f]);
  }
  return groups.flatMap((group) => {
    const sorted = [...group].sort(
      (a, b) =>
        Number(unitLabel(a) !== rowUnit) - Number(unitLabel(b) !== rowUnit) ||
        a.passage.page - b.passage.page,
    );
    const [shown] = sorted;
    return shown ? [{ value: shown.value, shown, sources: sorted }] : [];
  });
}

/** The step a value is written to: 1 000 000 for "36 681" millions, 100 000 000 for "36,7" billions. */
function precision(figure: Figure): number {
  const decimals = figure.value_as_written.match(/,(\d+)/)?.[1]?.length ?? 0;
  return figure.scale / 10 ** decimals;
}

function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function countOf<T>(items: T[]): Map<T, number> {
  const counts = new Map<T, number>();
  for (const item of items) counts.set(item, (counts.get(item) ?? 0) + 1);
  return counts;
}
