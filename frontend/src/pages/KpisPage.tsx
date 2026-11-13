import { useId, useState } from "react";

import { ApiError } from "../ApiError";
import { api, type KpiDefinition } from "../api/client";
import { useApi } from "../api/useApi";
import { APPLIES, bandLabel, sinceLabel } from "../kpis";

/** The KPIs page (#27 AC4): every KPI the app computes, generated from the same versioned rules
 * that compute it, so the documentation never drifts from the calculation. */
export function KpisPage() {
  const page = useApi("kpi-definitions", () => api.GET("/api/kpis"));
  const [theme, setTheme] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [history, setHistory] = useState(false);
  const searchId = useId();

  if (page.state === "loading") {
    return (
      <section className="page" aria-busy="true">
        <div className="micro">KPIS</div>
        <div className="skeleton figures-skeleton" aria-hidden="true" />
      </section>
    );
  }
  if (page.state === "error") {
    return <ApiError label="KPIS" title="The KPI definitions could not be loaded" message={page.message} />;
  }

  const { kpis, version, since } = page.data;
  // The themes in the rules' order, each with its title from the rules.
  const titles = new Map(page.data.themes.map((t) => [t.name, t.title]));
  const themeLabel = (name: string) => titles.get(name) ?? name;
  const themes = page.data.themes.map((t) => t.name).filter((t) => kpis.some((k) => k.theme === t));
  const words = query.trim().toLowerCase();
  const inTheme = kpis.filter((k) => theme === null || k.theme === theme);
  const shown = inTheme.filter((k) => !words || searchable(k, themeLabel(k.theme)).includes(words));

  return (
    <section className="page kpis-page" aria-labelledby="kpis-title">
      <div className="micro">
        KPIS · {kpis.length} RULES · KPI {version.toUpperCase()}
      </div>
      <div className="kpis-top">
        <div>
          <h1 id="kpis-title" className="page-title">
            KPIs
          </h1>
          <div className="kpis-locked">
            <span>
              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16">
                <path d="M3.5 7.5h9v6.5h-9Z" />
                <path d="M5.5 7.5V5a2.5 2.5 0 0 1 5 0v2.5" />
              </svg>
              Generated from the same versioned rules that compute every value in the product. Read-only.
            </span>
            <button
              type="button"
              className="kpis-history-toggle"
              aria-expanded={history}
              onClick={() => setHistory(!history)}
            >
              VERSION HISTORY
            </button>
          </div>
          {history && (
            <div className="kpis-history">
              <span className="kpis-history-current">kpi {version}</span>
              {since ? ` · ${sinceLabel(since)}` : ""} · first version
            </div>
          )}
        </div>
        <div className="search kpis-search">
          <label htmlFor={searchId} className="visually-hidden">
            Search KPIs
          </label>
          <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" className="search-glyph">
            <circle cx="7" cy="7" r="4.8" />
            <path d="M10.6 10.6L14 14" />
          </svg>
          <input
            id={searchId}
            type="search"
            autoComplete="off"
            placeholder="Search KPIs, formulas, inputs…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>

      <div role="group" aria-label="Themes" className="segmented kpis-themes">
        <button type="button" aria-pressed={theme === null} onClick={() => setTheme(null)}>
          ALL <span className="kpis-theme-count">{kpis.length}</span>
        </button>
        {themes.map((t) => (
          <button key={t} type="button" aria-pressed={theme === t} onClick={() => setTheme(t)}>
            {themeLabel(t).toUpperCase()}{" "}
            <span className="kpis-theme-count">{kpis.filter((k) => k.theme === t).length}</span>
          </button>
        ))}
      </div>

      <div className="kpis-table-box">
        <table className="kpis-table">
          <caption className="visually-hidden">KPI definitions, kpi {version}</caption>
          <thead>
            <tr>
              <th scope="col">KPI</th>
              <th scope="col">THEME</th>
              <th scope="col">WHAT IT MEANS</th>
              <th scope="col">FORMULA</th>
              <th scope="col">INPUTS</th>
              <th scope="col">HOW TO READ IT</th>
              <th scope="col">APPLIES TO</th>
              <th scope="col">RULE VERSION</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((kpi) => (
              <tr key={kpi.name}>
                <th scope="row">{kpi.title}</th>
                <td data-label="Theme">
                  <span className="kpis-theme">{themeLabel(kpi.theme)}</span>
                </td>
                <td data-label="What it means">{kpi.means}</td>
                <td data-label="Formula" className="kpis-formula">
                  {kpi.formula}
                  {kpi.tests.length > 0 && (
                    <ol className="kpis-tests">
                      {kpi.tests.map((t) => (
                        <li key={t.name}>
                          <span className="kpis-test-title">{t.title}:</span> {t.formula}
                        </li>
                      ))}
                    </ol>
                  )}
                </td>
                <td data-label="Inputs" className="kpis-inputs">{kpi.inputs.join(", ")}</td>
                <td data-label="How to read it">
                  {kpi.read}
                  {kpi.band && <span className="kpis-band"> · usual {bandLabel(kpi.band, kpi.format)}</span>}
                </td>
                <td data-label="Applies to">{APPLIES[kpi.applies]}</td>
                <td data-label="Rule version" className="kpis-version num">
                  kpi {version}
                  {since && <span className="kpis-since">since {sinceLabel(since)}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown.length === 0 && (
        <p className="kpis-empty">
          No KPI matches “{query.trim()}”{theme ? ` in ${themeLabel(theme)}` : ""}.
        </p>
      )}
      <p className="figures-note kpis-foot">
        Values are consolidated IFRS, last fiscal year. A KPI shows only when every input is present and
        checked by an analyst; otherwise it reads “–” with the reason. No estimates. Expenses enter a
        formula as positive amounts.
      </p>
    </section>
  );
}

/** What the search reads in a KPI: its name, theme, meaning, formula and inputs. */
function searchable(kpi: KpiDefinition, theme: string): string {
  return [
    kpi.title,
    theme,
    kpi.means,
    kpi.formula,
    ...kpi.tests.map((t) => `${t.title} ${t.formula}`),
    ...kpi.inputs,
  ]
    .join(" ")
    .toLowerCase();
}
