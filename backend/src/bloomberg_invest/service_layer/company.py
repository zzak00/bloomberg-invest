"""An issuer's dossier: its filings, and its figures by statement, line item and year (#19 R19)."""

from collections import Counter, defaultdict
from collections.abc import Sequence

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.dossier import agreeing
from bloomberg_invest.domain.figures import Scope
from bloomberg_invest.domain.label_map import LabelMap
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
    documents = store.list_documents(isin)
    if not documents:
        return None
    return Company(issuer=documents[0].issuer, documents=documents)


def company_figures(isin: str, store: GraphStore, label_map: LabelMap) -> FigureGrid | None:
    if store.issuer(isin) is None:
        return None
    return figure_grid(store.figures(isin), label_map)


def figure_detail(fact_id: str, store: GraphStore, label_map: LabelMap) -> FigureDetail | None:
    figure = store.fact(fact_id)
    if figure is None:
        return None
    item = label_map.items.get(figure.line_item)
    return FigureDetail(
        **figure.model_dump(), line_item_title=item.title if item else figure.line_item
    )


def figure_grid(figures: Sequence[Figure], label_map: LabelMap) -> FigureGrid:
    """The figures by basis, statement and row, a column per fiscal year. A row is a line item,
    or one breakdown of it, in one currency: the filing's euro tables are rows of their own, not
    disagreements. A line item the label map no longer has is left out."""
    return FigureGrid(
        count=len(figures),
        scopes=[
            _scope(scope, [f for f in figures if f.basis_scope == scope], label_map)
            for scope in Scope
        ],
    )


def _scope(scope: Scope, figures: list[Figure], label_map: LabelMap) -> ScopeFigures:
    years = sorted({f.fiscal_year for f in figures}, reverse=True)
    position = {name: i for i, name in enumerate(label_map.items)}
    currencies = Counter(_currency(f) for f in figures)

    rows: dict[tuple[str, str, str], list[Figure]] = defaultdict(list)
    for figure in figures:
        if figure.line_item in label_map.items:
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
        sources = sorted(group, key=lambda f: ((f.unit, f.scale) != (unit, scale), f.passage.page))
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
