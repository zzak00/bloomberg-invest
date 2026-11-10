"""What the dossier and the source viewer show of a figure: its value in force, and whether it
still needs a check (#19 R8, R10)."""

from bloomberg_invest.domain.figures import STANDARD, period
from bloomberg_invest.domain.kpis import KpiRules
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.review import Verdict, needs_review
from bloomberg_invest.views import Figure, RejectedFigure


def in_force(figure: Figure | RejectedFigure, label_map: LabelMap) -> Figure | None:
    """The figure with the value a person checked: a correction's value, read from the cell or
    the quote it picked, or for a typed value from what the figure was read from. A rejected
    figure counts only once corrected; None until then."""
    review = figure.review
    corrected = review is not None and review.verdict == Verdict.corrected
    if isinstance(figure, Figure) and not corrected:
        return figure
    if review is None or not corrected:
        return None
    fixed = {
        "value_as_written": review.value_as_written,
        "value": review.value,
        "unit": review.unit,
        "scale": review.scale,
        "currency": review.currency,
    }
    if isinstance(figure, Figure):
        passage = review.source or figure.passage
        page = passage.page if passage else figure.page
        return figure.model_copy(update=fixed | {"passage": passage, "page": page})

    item = label_map.items.get(figure.line_item)
    if item is None or figure.basis_scope is None:
        return None
    when = period(figure.fiscal_year, item.kind)
    passage = review.source
    return Figure(
        **fixed,
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
        passage=passage,
        page=passage.page if passage else figure.page,
        review=review,
    )


def gated(figure: Figure, rules: KpiRules) -> Figure:
    """The figure, flagged when it feeds a KPI or screen and nobody checked it (#23 AC2)."""
    needed = figure.review is None and needs_review(
        figure.basis_scope, figure.line_item, figure.breakdown, rules
    )
    return figure.model_copy(update={"needs_review": needed})
