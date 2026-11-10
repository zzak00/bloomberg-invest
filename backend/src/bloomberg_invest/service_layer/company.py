"""An issuer's dossier: its filings, and its figures by statement, line item and year (#19 R19)."""

from collections import Counter, defaultdict
from collections.abc import Sequence

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.dossier import agreeing
from bloomberg_invest.domain.figures import STANDARD, Scope, period
from bloomberg_invest.domain.kpis import KpiRules
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.review import correction_in_force, needs_check
from bloomberg_invest.views import (
    Company,
    Figure,
    FigureDetail,
    FigureGrid,
    FigureRow,
    FigureValue,
    FigureYear,
    RejectedFigure,
    ScopeFigures,
    StatementFigures,
)


def company(isin: str, store: GraphStore) -> Company | None:
    issuer = store.issuer(isin)
    if issuer is None:
        return None
    return Company(issuer=issuer, documents=store.list_documents(isin))


def company_figures(
    isin: str, store: GraphStore, label_map: LabelMap, rules: KpiRules
) -> FigureGrid | None:
    """The issuer's figures with the values in force: a corrected figure shows its correction,
    and a rejected figure joins once corrected (#19 R8)."""
    if store.issuer(isin) is None:
        return None
    facts, rejected = store.figures(isin)
    shown = [f for f in (in_force(f, label_map) for f in [*facts, *rejected]) if f is not None]
    shown.sort(key=lambda f: (-f.fiscal_year, f.page, f.line_item, f.breakdown))
    return figure_grid([gated(f, rules) for f in shown], label_map)


def figure_detail(
    figure_id: str, store: GraphStore, label_map: LabelMap, rules: KpiRules
) -> FigureDetail | None:
    """One figure as the dossier shows it: None for no such figure, or a rejected figure nobody
    corrected."""
    found = store.figure(figure_id)
    shown = in_force(found, label_map) if found is not None else None
    if shown is None:
        return None
    figure = gated(shown, rules)
    item = label_map.items.get(figure.line_item)
    return FigureDetail(
        **figure.model_dump(), line_item_title=item.title if item else figure.line_item
    )


def in_force(figure: Figure | RejectedFigure, label_map: LabelMap) -> Figure | None:
    """The figure as the dossier shows it: with its correction's value, read from the cell or
    quote the correction picked, or for a typed value from what the figure was read from. A
    rejected figure counts only once corrected; None until then."""
    fixed = correction_in_force(figure.review)
    if isinstance(figure, Figure) and fixed is None:
        return figure
    if fixed is None or figure.review is None:
        return None
    value = {
        "value_as_written": fixed.value_as_written,
        "value": fixed.value,
        "unit": fixed.unit,
        "scale": fixed.scale,
        "currency": fixed.currency,
    }
    source = figure.review.source
    if isinstance(figure, Figure):
        passage = source or figure.passage
        page = passage.page if passage else figure.page
        return figure.model_copy(update=value | {"passage": passage, "page": page})

    item = label_map.items.get(figure.line_item)
    if item is None or figure.basis_scope is None:
        return None
    when = period(figure.fiscal_year, item.kind)
    return Figure(
        **value,
        id=figure.id,
        line_item=figure.line_item,
        label=figure.label,
        unit_as_written=figure.unit_as_written,
        fiscal_year=figure.fiscal_year,
        period_start=when.start,
        period_end=when.end,
        as_of=when.as_of,
        basis_scope=figure.basis_scope,
        basis_standard=STANDARD[figure.basis_scope],
        breakdown=figure.breakdown,
        recorded_at=figure.recorded_at,
        document=figure.document,
        passage=source,
        page=source.page if source else figure.page,
        review=figure.review,
    )


def gated(figure: Figure, rules: KpiRules) -> Figure:
    """The figure, flagged when it feeds a KPI or screen and nobody checked it (#23 AC2)."""
    needed = figure.review is None and needs_check(figure, rules)
    return figure.model_copy(update={"needs_review": needed})


def figure_grid(figures: Sequence[Figure], label_map: LabelMap) -> FigureGrid:
    """The figures by basis, statement and row, a column per fiscal year. A row is a line item,
    or one breakdown of it, in one currency: the filing's euro tables are rows of their own, not
    disagreements. A line item the label map no longer has is left out, and not counted."""
    listed = [f for f in figures if f.line_item in label_map.items]
    return FigureGrid(
        count=len(listed),
        scopes=[
            _scope(scope, [f for f in listed if f.basis_scope == scope], label_map)
            for scope in Scope
        ],
    )


def _scope(scope: Scope, figures: list[Figure], label_map: LabelMap) -> ScopeFigures:
    years = sorted({f.fiscal_year for f in figures}, reverse=True)
    position = {name: i for i, name in enumerate(label_map.items)}
    currencies = Counter(_currency(f) for f in figures)

    rows: dict[tuple[str, str, str], list[Figure]] = defaultdict(list)
    for figure in figures:
        rows[(figure.line_item, _currency(figure), figure.breakdown)].append(figure)

    def order(key: tuple[str, str, str]) -> tuple[int, int, bool, str]:
        line_item, currency, breakdown = key
        return (position[line_item], -currencies[currency], breakdown != "", breakdown)

    by_statement: dict[str, list[FigureRow]] = defaultdict(list)
    for key in sorted(rows, key=order):
        item = label_map.items[key[0]]
        by_statement[item.statement].append(_row(key, item.title, rows[key], years))
    return ScopeFigures(
        scope=scope,
        years=years,
        statements=[
            StatementFigures(key=key, title=title, rows=by_statement[key])
            for key, title in label_map.statements.items()
            if by_statement[key]
        ],
    )


def _row(
    key: tuple[str, str, str], title: str, figures: list[Figure], years: list[int]
) -> FigureRow:
    line_item, currency, breakdown = key
    # The unit most of the row's figures are written in; the first seen on a tie.
    (unit, scale), _ = Counter((f.unit, f.scale) for f in figures).most_common(1)[0]

    # A checked figure is shown first, and a checked value before the others (#19 R8).
    def value(group: list[Figure]) -> FigureValue:
        sources = sorted(
            group, key=lambda f: (f.review is None, (f.unit, f.scale) != (unit, scale), f.page)
        )
        return FigureValue(shown=sources[0], sources=sources)

    def values(stated: list[Figure]) -> list[FigureValue]:
        shown = [value(g) for g in agreeing(stated)]
        return sorted(shown, key=lambda v: all(f.review is None for f in v.sources))

    return FigureRow(
        line_item=line_item,
        title=title,
        breakdown=breakdown,
        currency=currency,
        unit=unit,
        scale=scale,
        years=[
            FigureYear(fiscal_year=year, values=values(stated))
            for year in years
            if (stated := [f for f in figures if f.fiscal_year == year])
        ],
    )


def _currency(figure: Figure) -> str:
    return figure.currency or figure.unit
