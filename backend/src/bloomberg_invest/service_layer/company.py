"""An issuer's dossier: its filings, and its figures by statement, line item and year (#19 R19)."""

from collections import Counter, defaultdict
from collections.abc import Sequence

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.dossier import agreeing
from bloomberg_invest.domain.figures import Scope
from bloomberg_invest.domain.kpis import KpiRules
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.service_layer.figures import gated, in_force
from bloomberg_invest.views import (
    Company,
    Figure,
    FigureDetail,
    FigureGrid,
    FigureRow,
    FigureValue,
    FigureYear,
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

    def value(group: list[Figure]) -> FigureValue:
        sources = sorted(group, key=lambda f: ((f.unit, f.scale) != (unit, scale), f.page))
        return FigureValue(shown=sources[0], sources=sources)

    return FigureRow(
        line_item=line_item,
        title=title,
        breakdown=breakdown,
        currency=currency,
        unit=unit,
        scale=scale,
        years=[
            FigureYear(fiscal_year=year, values=[value(g) for g in agreeing(stated)])
            for year in years
            if (stated := [f for f in figures if f.fiscal_year == year])
        ],
    )


def _currency(figure: Figure) -> str:
    return figure.currency or figure.unit
