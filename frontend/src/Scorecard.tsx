import { useId } from "react";
import { Link } from "react-router";

import type { KpiInput, Scorecard as ScorecardData, ScorecardKpi } from "./api/client";
import { bandLabel, bandPlace, formatKpi, inputValue, listed } from "./kpis";

type ScoreTest = ScorecardKpi["tests"][number];
type TestState = "passed" | "failed" | "waiting" | "not_applicable";

/** A company's scorecard (#27 AC5): its quality KPIs and the F-score for a fiscal year, by
 * default its last, each computed from checked figures, or "–" with why. A KPI's inputs show on
 * hover or focus. */
export function Scorecard({
  card,
  isin,
  onYear,
}: {
  card: ScorecardData;
  isin: string;
  onYear: (year: number) => void;
}) {
  if (card.fiscal_year === null) {
    return (
      <div className="state">
        <h2>No KPI values yet</h2>
        <p>
          KPIs are computed from a filing's consolidated figures once they are extracted, and each shows
          a value once a person has checked its inputs in CHECKS.
        </p>
      </div>
    );
  }
  const year = card.fiscal_year;
  const quality = card.kpis.filter((k) => k.tests.length === 0);
  const score = card.kpis.find((k) => k.tests.length > 0);
  const shown = quality.filter((k) => k.status === "computed").length;
  const everywhere = card.kpis.filter((k) => k.applies === "all").map((k) => k.title);
  return (
    <div className="scorecard">
      <div className="scorecard-head">
        <div className="scorecard-head-line">
          <div className="scorecard-basis">
            {card.basis} · FY{year} · kpi {card.rule_version}
          </div>
          {card.years.length > 1 && (
            <div role="group" aria-label="Fiscal year" className="segmented scorecard-years">
              {card.years.map((y) => (
                <button key={y} type="button" aria-pressed={y === year} onClick={() => onYear(y)}>
                  FY{y}
                </button>
              ))}
            </div>
          )}
        </div>
        <p className="figures-note">
          A KPI shows only when every input is present and checked; otherwise “–” and the reason. No
          estimates. Hover or focus a KPI for its inputs.
        </p>
        {card.financial && (
          <p className="scorecard-bank">
            Bank or insurer: only {listed(everywhere)} apply. The other KPIs read “not meaningful”.
          </p>
        )}
        {card.sector === null && (
          <p className="scorecard-bank">
            Sector unknown: banks and insurers are recognised from the Listing. Add the ISIN to{" "}
            <code>config/listings</code>.
          </p>
        )}
      </div>
      <div className="scorecard-grid">
        <section aria-labelledby="scorecard-quality">
          <div className="scorecard-section micro">
            <h2 id="scorecard-quality">Quality · {quality.length}</h2>
            <span>
              {shown} of {quality.length} shown
            </span>
          </div>
          <ul className="kpi-rows" aria-label="Quality KPIs">
            {quality.map((kpi) => (
              <KpiRow
                key={kpi.name}
                kpi={kpi}
                year={year}
                span={card.window}
                sector={card.sector}
                version={card.rule_version}
                isin={isin}
              />
            ))}
          </ul>
        </section>
        {score && <FScore kpi={score} version={card.rule_version} />}
      </div>
    </div>
  );
}

function KpiRow({
  kpi,
  year,
  span,
  sector,
  version,
  isin,
}: {
  kpi: ScorecardKpi;
  year: number;
  span: number;
  sector: string | null;
  version: string;
  isin: string;
}) {
  const tip = useId();
  const computed = kpi.status === "computed" && kpi.value !== null;
  const place = bandPlace(kpi);
  return (
    <li
      className="kpi-row"
      data-status={kpi.status}
      onKeyDown={(event) => {
        if (event.key === "Escape") (document.activeElement as HTMLElement | null)?.blur();
      }}
    >
      <div className="kpi-line">
        <button type="button" className="kpi-name" aria-describedby={tip}>
          {kpi.title}
        </button>
        <span className="kpi-value num">{computed ? formatKpi(kpi.value!, kpi.format) : "–"}</span>
      </div>
      {computed ? (
        <div className="kpi-refs">
          <Sparkline kpi={kpi} year={year} span={span} />
          <span className="kpi-peers">
            {sector === null
              ? "sector unknown"
              : kpi.sector_median !== null
                ? `sector ${formatKpi(kpi.sector_median, kpi.format)} (n=${kpi.peers})`
                : `sector: too few peers (${kpi.peers})`}
          </span>
          {kpi.band && (
            <span className="kpi-band" data-place={place ?? undefined}>
              <span aria-hidden="true">{place === "below" ? "▼" : place === "above" ? "▲" : "●"} </span>
              <span className="visually-hidden">
                {place === "below" ? "below the usual range" : place === "above" ? "above the usual range" : "within the usual range"}
                {", "}
              </span>
              {bandLabel(kpi.band, kpi.format)}
            </span>
          )}
        </div>
      ) : (
        <div className="kpi-reason">{kpi.reason}</div>
      )}
      <div className="kpi-tip" id={tip}>
        <div className="kpi-tip-formula">
          {kpi.title} = {kpi.formula}
        </div>
        {kpi.inputs.length > 0 && (
          <ul className="kpi-tip-inputs">
            {kpi.inputs.map((input) => (
              <InputLine key={`${input.name}·${input.fiscal_year}`} input={input} isin={isin} />
            ))}
          </ul>
        )}
        <div className="kpi-tip-rule">Rule: kpi {version}</div>
      </div>
    </li>
  );
}

function InputLine({ input, isin }: { input: KpiInput; isin: string }) {
  const name = `${input.title} FY${input.fiscal_year}`;
  if (input.status === "missing" || input.status === "not_reported") {
    return (
      <li data-status={input.status}>
        <span className="kpi-tip-name">{name}</span>
        <span className="kpi-tip-status">{input.reason || "not found in the filings"}</span>
      </li>
    );
  }
  const source =
    input.document && input.fact_id ? (
      // A declared dividend is checked in the fact inspector; a figure opens on its page.
      <Link
        to={
          input.kind === "declared"
            ? `/companies/${isin}?tab=facts&fact=${input.fact_id}`
            : `/documents/${input.document.id}?fact=${input.fact_id}`
        }
      >
        {inputValue(input)} · p. {input.page}
      </Link>
    ) : (
      inputValue(input)
    );
  return (
    <li data-status={input.status}>
      <span className="kpi-tip-name">{name}</span>
      <span className="kpi-tip-source">{source}</span>
      <span className="kpi-tip-status">
        {input.status === "checked"
          ? `checked by ${input.checked_by} ✓`
          : input.status === "conflict"
            ? "two values: check one in CHECKS"
            : "waiting for check"}
      </span>
    </li>
  );
}

/** The years of the history up to the selected one, each at its place; the selected year
 * marked. */
function Sparkline({ kpi, year, span }: { kpi: ScorecardKpi; year: number; span: number }) {
  const points = kpi.history
    .filter((p) => p.status === "computed" && p.value !== null)
    .map((p) => ({ year: p.fiscal_year, value: Number(p.value) }));
  const last = points[points.length - 1];
  if (points.length < 2 || !last) {
    return <span className="kpi-spark-note">FY{last?.year ?? year} only</span>;
  }
  const values = points.map((p) => p.value);
  const [low, high] = [Math.min(...values), Math.max(...values)];
  const range = high - low || 1;
  // The span's first year at the left edge, the selected one at the right, 3px in from each.
  const x = (y: number) => 3 + ((y - (year - span + 1)) * 38) / Math.max(span - 1, 1);
  const y = (v: number) => 12 - ((v - low) / range) * 10;
  const label = `${kpi.title}: ${points.map((p) => `FY${p.year} ${formatKpi(String(p.value), kpi.format)}`).join(", ")}`;
  return (
    <svg className="kpi-spark" role="img" aria-label={label} width="44" height="14" viewBox="0 0 44 14">
      <polyline points={points.map((p) => `${x(p.year)},${y(p.value).toFixed(1)}`).join(" ")} />
      {last.year === year && <circle cx={x(last.year)} cy={y(last.value).toFixed(1)} r="2" />}
    </svg>
  );
}

function testState(test: ScoreTest): TestState {
  if (test.status === "not_meaningful") return "not_applicable";
  if (test.status !== "computed") return "waiting";
  return test.passed ? "passed" : "failed";
}

const TEST_SAYS: Record<TestState, string> = {
  passed: "passed ✓",
  failed: "failed ✕",
  waiting: "waiting",
  not_applicable: "not applicable",
};

/** The Piotroski F-score: one cell per test, in the rules' order. A test that can't apply to
 * the company, such as gross margin with no gross profit, is drawn but not counted. */
function FScore({ kpi, version }: { kpi: ScorecardKpi; version: string }) {
  const tests = kpi.tests.map((test) => ({ test, state: testState(test) }));
  const passed = tests.filter((t) => t.state === "passed").length;
  const waiting = tests.filter((t) => t.state === "waiting").length;
  const dropped = tests.filter((t) => t.state === "not_applicable").map((t) => t.test.title);
  const outOf = kpi.out_of ?? tests.length - dropped.length;
  if (kpi.status === "not_meaningful") {
    return (
      <section className="fscore" aria-labelledby="scorecard-fscore">
        <div className="scorecard-section micro">
          <h2 id="scorecard-fscore">{kpi.title}</h2>
          <span className="fscore-total num">–</span>
        </div>
        <p className="fscore-note">– · {kpi.reason}</p>
      </section>
    );
  }
  const notCounted = dropped.length
    ? `: ${listed(dropped.map((t) => t.charAt(0).toLowerCase() + t.slice(1)))} ${dropped.length > 1 ? "are" : "is"} not meaningful`
    : "";
  return (
    <section className="fscore" aria-labelledby="scorecard-fscore">
      <div className="scorecard-section micro">
        <h2 id="scorecard-fscore">{kpi.title}</h2>
        <span className="fscore-total num">
          {kpi.status === "computed" ? `${passed} / ${outOf}` : `${passed} passed · ${waiting} waiting`}
        </span>
      </div>
      <ol
        className="fscore-bar"
        aria-label={`${kpi.title}: ${passed} of ${outOf} tests passed${waiting ? `, ${waiting} waiting for check` : ""}`}
      >
        {tests.map(({ test, state }) => {
          const says = state === "waiting" || state === "not_applicable" ? `${TEST_SAYS[state]}: ${test.reason}` : TEST_SAYS[state];
          return (
            <li key={test.name} data-state={state} title={`${test.title} · ${says}`}>
              <span aria-hidden="true">{state === "passed" ? "✓" : state === "failed" ? "✕" : state === "not_applicable" ? "–" : ""}</span>
              <span className="visually-hidden">
                {test.title}: {says}
              </span>
            </li>
          );
        })}
      </ol>
      <div className="fscore-legend" aria-hidden="true">
        <span data-state="passed">passed ✓</span>
        <span data-state="failed">failed ✕</span>
        <span data-state="waiting">waiting for check</span>
        {dropped.length > 0 && <span data-state="not_applicable">not applicable</span>}
      </div>
      <p className="fscore-note">
        {kpi.status === "computed"
          ? `Score ${passed} of ${outOf}${notCounted}. Rule kpi ${version}.`
          : `${kpi.reason}.`}
      </p>
      <ul className="fscore-tests">
        {tests.map(({ test, state }) => (
          <li key={test.name} data-state={state}>
            <span className="fscore-test-title">{test.title}</span>
            <span className="fscore-test-state">{TEST_SAYS[state]}</span>
            {(state === "waiting" || state === "not_applicable") && (
              <span className="fscore-test-reason">{test.reason}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
