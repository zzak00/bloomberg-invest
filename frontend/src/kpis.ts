import type { KpiDefinition, KpiInput, ScorecardKpi } from "./api/client";

type Format = KpiDefinition["format"];

const ONE_DECIMAL = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const WHOLE = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });

/** How each format shows a value: a ratio x 100, an amount in millions; its digits and unit. */
const FORMATS: Record<Format, { scale: number; digits: Intl.NumberFormat; unit: string }> = {
  percent: { scale: 100, digits: ONE_DECIMAL, unit: " %" },
  multiple: { scale: 1, digits: ONE_DECIMAL, unit: "x" },
  amount: { scale: 1 / 1_000_000, digits: WHOLE, unit: " MAD m" },
  score: { scale: 1, digits: WHOLE, unit: "" },
};

/** The number a KPI value is shown as, in its format's unit. */
function scaled(value: number, format: Format): number {
  return value * FORMATS[format].scale;
}

/** A KPI value as #7 shows it, in French format: "50,4 %", "1,0x", "9 095 MAD m", "7". */
export function formatKpi(value: string, format: Format): string {
  const { digits, unit } = FORMATS[format];
  return `${digits.format(scaled(Number(value), format))}${unit}`;
}

/** A band in the unit shown, whole numbers: "20–40 %", "< 2x". */
export function bandLabel(band: string[], format: Format): string {
  const [low = 0, high = 0] = band.map(Number);
  const { unit } = FORMATS[format];
  return low === 0
    ? `< ${WHOLE.format(high)}${unit}`
    : `${WHOLE.format(low)}–${WHOLE.format(high)}${unit}`;
}

/** Where a value sits against its band: below, within or above. */
export function bandPlace(kpi: ScorecardKpi): "below" | "within" | "above" | null {
  if (!kpi.band || kpi.value === null) return null;
  const shown = scaled(Number(kpi.value), kpi.format);
  const [low = 0, high = 0] = kpi.band.map(Number);
  return shown < low ? "below" : shown > high ? "above" : "within";
}

export const APPLIES: Record<KpiDefinition["applies"], string> = {
  all: "all companies",
  non_financial: "all except banks and insurers",
};

/** An input's value as the filing writes it: "36 681 MAD millions". */
export function inputValue(input: KpiInput): string {
  return [input.value_as_written, input.unit_as_written].filter(Boolean).join(" ");
}

/** A rule version's date as #7 writes it: "29.10.2026" for "2026-10-29". */
export function sinceLabel(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}.${month}.${year}`;
}

/** Names as a sentence lists them: "ROE, ROA and Payout ratio". */
export function listed(names: string[]): string {
  if (names.length < 2) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
