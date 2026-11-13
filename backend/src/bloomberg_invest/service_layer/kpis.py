"""KPI values (#27; #7, #19 R10, R12, R14): computed in Python from an issuer's checked
consolidated figures and declared dividends, kept in the graph, and shown on its scorecard.

A recompute writes only the values that changed, so a corrected figure supersedes only the KPI
values that read it (AC3)."""

import statistics
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.dossier import agreeing
from bloomberg_invest.domain.facts import FactKind
from bloomberg_invest.domain.figures import STANDARD, Scope
from bloomberg_invest.domain.kpis import (
    MEASURES,
    Declared,
    Input,
    InputValue,
    Kpi,
    KpiChange,
    KpiResult,
    KpiRules,
    KpiStatus,
    compute,
)
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.model import RunInfo, RunStep
from bloomberg_invest.domain.review import needs_check, value_check
from bloomberg_invest.service_layer.company import as_shown
from bloomberg_invest.views import (
    DocumentRef,
    Figure,
    KpiDefinition,
    KpiDefinitions,
    KpiInput,
    KpiPoint,
    KpiTheme,
    PartyRef,
    RejectedFigure,
    Review,
    Scorecard,
    ScorecardKpi,
    ScoreTest,
    StatedFact,
    StoredKpi,
    TestDefinition,
)

YEARS = 3  # the scorecard's sparkline: FY-2 to FY
MIN_PEERS = 3  # a sector median needs this many other companies, else "too few peers" (#7)


@dataclass(frozen=True)
class Shown:
    """Where an input's value in force is read, for the hover."""

    fact_id: str
    document: DocumentRef
    page: int
    value_as_written: str
    unit_as_written: str
    checked_by: str | None


@dataclass(frozen=True)
class Gathered:
    """An issuer's inputs: each (name, fiscal year)'s value in force, and where it is read."""

    values: dict[tuple[str, int], InputValue]
    shown: dict[tuple[str, int], Shown]


class _Stating(Protocol):
    """A figure or a dividend Fact: what states an input's value."""

    @property
    def id(self) -> str: ...
    @property
    def document(self) -> DocumentRef: ...
    @property
    def page(self) -> int: ...
    @property
    def review(self) -> Review | None: ...


def gather(
    isin: str,
    figures: Sequence[Figure | RejectedFigure],
    facts: Sequence[StatedFact],
    label_map: LabelMap,
    rules: KpiRules,
) -> Gathered:
    """Every input the rules' formulas read, by fiscal year: the value in force across the
    issuer's filings, the way the dossier shows it (#19 R8, #24 D4). Given the issuer's figures
    and its other facts, with the checks they have, or will have once a check is recorded."""
    names: dict[Input | Declared, list[str]] = defaultdict(list)
    for kpi in rules.kpis:
        for formula in kpi.formulas:
            for name in formula.names:
                source = rules.source(name)
                if source is not None and name not in names[source]:
                    names[source].append(name)

    values: dict[tuple[str, int], InputValue] = {}
    shown: dict[tuple[str, int], Shown] = {}

    def keep(names_of: list[str], year: int, found: tuple[InputValue, Shown]) -> None:
        for name in names_of:
            values[(name, year)], shown[(name, year)] = found

    stated: dict[tuple[Input, int], list[Figure]] = defaultdict(list)
    for figure in (f for f in (as_shown(f, label_map) for f in figures) if f is not None):
        source = Input(figure.line_item, figure.breakdown)
        # Only figures that need a check count: consolidated, in the filing's currency (#56).
        if source in names and needs_check(figure, rules):
            stated[(source, figure.fiscal_year)].append(figure)
    for (source, year), group in stated.items():
        groups = agreeing(group)
        found = _input_value(
            groups,
            [value_check(g) for g in groups],
            lambda f: Decimal(f.value),
            lambda f: (f.value_as_written, f.unit_as_written),
        )
        keep(names[source], year, found)

    declaring: dict[tuple[Declared, int], list[list[StatedFact]]] = defaultdict(list)
    for (by, year, source), groups in declared_values(facts, rules).items():
        if by == isin and source in names:
            declaring[(source, year)] = groups
    for (source, year), groups in declaring.items():
        found = _input_value(
            groups,
            [kept([f.review for f in g]) for g in groups],
            lambda f: Decimal(str(f.amount_value)),
            lambda f: (str(f.values.get("amount") or ""), str(f.values.get("unit") or "")),
        )
        keep(names[source], year, found)
    return Gathered(values, shown)


def _input_value[F: _Stating](
    groups: list[list[F]],
    checks: list[Review | None],
    number: Callable[[F], Decimal],
    written: Callable[[F], tuple[str, str]],
) -> tuple[InputValue, Shown]:
    """An input's value in force for one fiscal year, from the groups of figures or facts
    stating each value, and where the hover reads it: the checked one first."""
    picked, check = _in_force(groups, checks)
    first = first_stating(picked)
    value = InputValue(
        values=(number(picked[0]),) if check else tuple(number(g[0]) for g in groups),
        checked=check is not None,
        ids=tuple(sorted(f.id for f in (picked if check else [f for g in groups for f in g]))),
    )
    value_as_written, unit_as_written = written(first)
    return value, Shown(
        fact_id=first.id,
        document=first.document,
        page=first.page,
        value_as_written=value_as_written,
        unit_as_written=unit_as_written,
        checked_by=check.reviewer if check else None,
    )


def _in_force[F](
    groups: list[list[F]], checks: list[Review | None]
) -> tuple[list[F], Review | None]:
    """The value in force among the values filings state for one input and year, and its
    check: the one value; or, when they disagree, the one value a person checked, as the
    dossier shows it first (#19 R8). None for the check when no single value is checked."""
    if len(groups) == 1:
        return groups[0], checks[0]
    checked = [(g, c) for g, c in zip(groups, checks, strict=True) if c is not None]
    if len(checked) == 1:
        return checked[0]
    return groups[0], None


def first_stating[F: _Stating](group: Sequence[F]) -> F:
    """The figure or fact a value is shown from: a checked one first, then the first read."""
    return min(group, key=lambda f: (f.review is None, f.page, f.id))


def kept(reviews: list[Review | None]) -> Review | None:
    """A fact's value is checked once a person kept one of the facts stating it (D5)."""
    done = [r for r in reviews if r is not None]
    return max(done, key=lambda r: r.reviewed_at, default=None)


def declaring(fact: StatedFact) -> PartyRef | None:
    """The company a dividend Fact says declares it, once its name is linked."""
    company = next((p for p in fact.parties if p.role == "company"), None)
    if fact.kind != FactKind.dividend or company is None:
        return None
    return company.resolved


def declared_by(fact: StatedFact) -> str | None:
    """The ISIN of the company a dividend Fact says declares it, once its name is linked."""
    company = declaring(fact)
    return company.isin if company is not None else None


def dividend_feeds(fact: StatedFact, rules: KpiRules) -> list[str]:
    """The titles of the KPIs a dividend Fact feeds: those reading its measure."""
    measure = next((m for m in MEASURES if m == fact.values.get("measure")), None)
    if fact.kind != FactKind.dividend or measure is None:
        return []
    return rules.declared_feeds(measure)


# A company's dividend declared for a fiscal year, in the measure an input reads.
Declaring = tuple[str, int, Declared]


def declared_values(
    facts: Sequence[StatedFact], rules: KpiRules
) -> dict[Declaring, list[list[StatedFact]]]:
    """The dividend Facts that feed a KPI, by the company declaring, fiscal year and measure,
    then by the amount they state: two groups disagree. Only an amount in its filing's currency
    counts: a translation never does (#56), and an amount whose currency could not be read is
    no dividend to compute with."""
    stating: dict[Declaring, dict[Decimal, list[StatedFact]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for fact in facts:
        isin = declared_by(fact)
        if (
            isin is not None
            and dividend_feeds(fact, rules)
            and fact.fiscal_year is not None
            and fact.amount_value is not None
            and fact.currency == fact.document.currency
        ):
            source = Declared(fact.values["measure"])
            stating[(isin, fact.fiscal_year, source)][Decimal(str(fact.amount_value))].append(fact)
    return {key: list(amounts.values()) for key, amounts in stating.items()}


@dataclass(frozen=True)
class Computed:
    run_id: str | None  # None when nothing changed
    written: int  # KPI values written
    superseded: int  # values replaced, or no longer computed


def compute_kpis(
    isin: str,
    store: GraphStore,
    label_map: LabelMap,
    rules: KpiRules,
    now: datetime | None = None,
) -> Computed:
    """Compute every KPI of the issuer for each fiscal year it has inputs for, and keep the
    values that changed in their own compute Run; a value no longer computed is superseded.
    Raises LookupError for an unknown ISIN."""
    if store.issuer(isin) is None:
        raise LookupError(f"no issuer {isin}")
    change = kpi_change(isin, store, label_map, rules, now=now)
    if change is None:
        return Computed(None, 0, 0)
    return Computed(store.record_kpi_values(change), len(change.results), change.superseded)


def kpi_change(
    isin: str,
    store: GraphStore,
    label_map: LabelMap,
    rules: KpiRules,
    checked: Mapping[str, Review | None] | None = None,
    now: datetime | None = None,
) -> KpiChange | None:
    """The KPI values of the issuer that differ from those stored, and the stored ones no
    longer computed; None when nothing changed. `checked` gives figures and facts the check a
    person is recording (None when it reopens them), so the check and the values it changes
    are written together (#27 AC3)."""
    started_at = now or datetime.now(UTC)

    gathered = _gathered(isin, store, label_map, rules, checked or {})
    years = sorted({year for _, year in gathered.values})
    listing = store.listing(isin)
    is_financial = rules.financial(listing.sector if listing else None)
    results = [r for y in years for r in compute(rules, gathered.values, y, is_financial)]
    stored = {(k.kpi, k.fiscal_year): k for k in store.kpi_values(isin)}
    changed = [
        r for r in results if not _same(stored.get((r.kpi, r.fiscal_year)), r, rules, label_map)
    ]
    keys = {(r.kpi, r.fiscal_year) for r in results}
    gone = [key for key in stored if key not in keys]
    if not changed and not gone:
        return None
    run = RunInfo(
        step=RunStep.compute,
        tool="bloomberg-invest",
        tool_version="1",
        config={
            "kpi_rules": rules.version,
            "kpi_rules_sha256": rules.sha256,
            "label_map": label_map.version,
        },
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    replaced = sum(1 for r in changed if (r.kpi, r.fiscal_year) in stored)
    return KpiChange(
        isin=isin,
        results=tuple(changed),
        gone=tuple(gone),
        run=run,
        rule_version=rules.version,
        rule_sha256=rules.sha256,
        label_map=label_map.version,
        superseded=replaced + len(gone),
    )


def _gathered(
    isin: str,
    store: GraphStore,
    label_map: LabelMap,
    rules: KpiRules,
    checked: Mapping[str, Review | None],
) -> Gathered:
    """The issuer's inputs as the store holds them, with the checks being recorded applied."""

    def apply[F: (Figure, RejectedFigure, StatedFact)](found: F) -> F:
        if found.id not in checked:
            return found
        return found.model_copy(update={"review": checked[found.id]})

    facts, rejected = store.figures(isin)
    stated, _ = store.facts(isin)
    figures = [apply(f) for f in [*facts, *rejected]]
    return gather(isin, figures, [apply(f) for f in stated], label_map, rules)


def _same(
    stored: StoredKpi | None, result: KpiResult, rules: KpiRules, label_map: LabelMap
) -> bool:
    """Whether a stored value is what the rules compute now, from the same Facts read with the
    same label map."""
    if stored is None:
        return False
    return (
        stored.rule_sha256 == rules.sha256
        and stored.label_map == label_map.version
        and stored.status == result.status
        and (Decimal(stored.value) if stored.value is not None else None) == result.value
        and stored.reason == result.reason
        and stored.out_of == result.out_of
        and stored.sources == list(result.sources)
        and [(u.name, u.fiscal_year) for u in stored.used]
        == [(u.name, u.fiscal_year) for u in result.used]
        and [(t.name, t.status, t.passed, t.reason) for t in stored.tests]
        == [(t.name, t.status, t.passed, t.reason) for t in result.tests]
    )


def scorecard(
    isin: str,
    store: GraphStore,
    label_map: LabelMap,
    rules: KpiRules,
    fiscal_year: int | None = None,
) -> Scorecard | None:
    """The issuer's quality KPIs and F-score for a fiscal year, by default the last with a
    computed value, each with its inputs as the hover lists them. None for an unknown ISIN;
    raises LookupError for a fiscal year with no values."""
    if store.issuer(isin) is None:
        return None
    stored = {(k.kpi, k.fiscal_year): k for k in store.kpi_values(isin)}
    years = sorted({year for _, year in stored})
    if fiscal_year is not None and fiscal_year not in years:
        raise LookupError(f"no KPI values of {isin} for FY{fiscal_year}")
    # By default the last fiscal year a value is computed for; else the last with any value.
    done = {y for (_, y), k in stored.items() if k.status == KpiStatus.computed}
    year = fiscal_year or max(done or years, default=None)
    listing = store.listing(isin)
    sector = listing.sector if listing else None
    rows = []
    if year is not None:
        gathered = _gathered(isin, store, label_map, rules, {})
        peers: dict[str, list[Decimal]] = defaultdict(list)
        if sector is not None:
            for k in store.sector_kpi_values(sector, year, other_than=isin):
                # A peer's value counts once computed under the rules in force.
                if (
                    k.status == KpiStatus.computed
                    and k.value is not None
                    and k.rule_sha256 == rules.sha256
                ):
                    peers[k.kpi].append(Decimal(k.value))
        for kpi in (k for k in rules.kpis if k.computed):
            value = stored.get((kpi.name, year))
            if value is not None:
                rows.append(_row(kpi, value, stored, year, gathered, rules, peers[kpi.name]))
    return Scorecard(
        fiscal_year=year,
        years=years,
        window=YEARS,
        basis=f"Consolidated · {STANDARD[Scope.consolidated]}",
        rule_version=rules.version,
        since=rules.since,
        financial=rules.financial(sector),
        sector=sector,
        kpis=rows,
    )


def _row(
    kpi: Kpi,
    value: StoredKpi,
    stored: dict[tuple[str, int], StoredKpi],
    year: int,
    gathered: Gathered,
    rules: KpiRules,
    peers: list[Decimal],
) -> ScorecardKpi:
    history = [
        KpiPoint(fiscal_year=y, status=k.status, value=k.value)
        for y in range(year - YEARS + 1, year + 1)
        if (k := stored.get((kpi.name, y))) is not None
    ]
    titles = {t.name: t.title for t in kpi.tests}
    return ScorecardKpi(
        name=kpi.name,
        title=kpi.title,
        theme=kpi.theme,
        format=kpi.format,
        band=_band(kpi),
        applies=kpi.applies,
        formula=_formula(kpi, rules),
        status=value.status,
        value=value.value,
        reason=value.reason,
        out_of=value.out_of,
        history=history,
        peers=len(peers),
        sector_median=str(statistics.median(peers)) if len(peers) >= MIN_PEERS else None,
        inputs=[_input(u.name, u.fiscal_year, gathered, rules) for u in value.used],
        tests=[
            ScoreTest(
                name=t.name,
                title=titles.get(t.name, t.name),
                status=t.status,
                passed=t.passed,
                reason=t.reason,
            )
            for t in value.tests
        ],
        computed_at=value.computed_at,
    )


def _input(name: str, year: int, gathered: Gathered, rules: KpiRules) -> KpiInput:
    title = rules.titles.get(name, name)
    kind = "declared" if isinstance(rules.source(name), Declared) else "figure"
    if name in rules.not_reported:
        return KpiInput(
            name=name,
            title=title,
            fiscal_year=year,
            kind=kind,
            status="not_reported",
            reason=rules.not_reported[name],
        )
    found, where = gathered.values.get((name, year)), gathered.shown.get((name, year))
    if found is None or where is None:
        return KpiInput(name=name, title=title, fiscal_year=year, kind=kind, status="missing")
    status = "conflict" if len(found.values) > 1 else "checked" if found.checked else "unchecked"
    return KpiInput(
        name=name,
        title=title,
        fiscal_year=year,
        kind=kind,
        status=status,
        value_as_written=where.value_as_written,
        unit_as_written=where.unit_as_written,
        document=where.document,
        page=where.page,
        fact_id=where.fact_id,
        checked_by=where.checked_by,
    )


def _band(kpi: Kpi) -> list[str] | None:
    return [str(b) for b in kpi.band] if kpi.band else None


def _formula(kpi: Kpi, rules: KpiRules) -> str:
    if kpi.formula is not None:
        return kpi.formula.render(rules.titles)
    return f"sum of {len(kpi.tests)} pass/fail tests"


def definitions(rules: KpiRules) -> KpiDefinitions:
    """The KPIs page (#27 AC4), from the rules that compute every value."""
    return KpiDefinitions(
        version=rules.version,
        since=rules.since,
        sha256=rules.sha256,
        themes=[KpiTheme(name=name, title=title) for name, title in rules.themes.items()],
        kpis=[
            KpiDefinition(
                name=kpi.name,
                title=kpi.title,
                theme=kpi.theme,
                means=kpi.means,
                formula=_formula(kpi, rules),
                inputs=list(
                    dict.fromkeys(rules.titles.get(n, n) for f in kpi.formulas for n in f.names)
                ),
                read=kpi.read,
                applies=kpi.applies,
                format=kpi.format,
                band=_band(kpi),
                tests=[
                    TestDefinition(
                        name=t.name, title=t.title, formula=t.formula.render(rules.titles)
                    )
                    for t in kpi.tests
                ],
            )
            for kpi in rules.kpis
            if kpi.computed
        ],
    )
