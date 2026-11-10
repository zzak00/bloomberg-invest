"""CHECKS (#19 R4, R9, R10; #23): the figures a person must check before they count, and the
checks themselves. Only consolidated figures that feed a KPI or screen need one."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.dossier import agreeing
from bloomberg_invest.domain.figures import Scope, parse_value
from bloomberg_invest.domain.kpis import KpiRules
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.review import (
    CheckStatus,
    InvalidCorrection,
    QuotedSource,
    ReviewDraft,
    Verdict,
    around,
    correction,
    needs_review,
    numbers_in,
)
from bloomberg_invest.views import (
    Candidate,
    CheckCounts,
    CheckGroup,
    CheckQueue,
    CheckRow,
    Figure,
    RejectedFigure,
    Review,
)


@dataclass(frozen=True)
class Checks:
    """What checking needs: the KPI rules that say which figures need a check, and who checks.
    One app runs per laptop (#19 Scope), so the reviewer is a setting."""

    rules: KpiRules
    reviewer: str | None


class NoReviewer(Exception):
    """Checks are refused until the app knows who checks."""


class ReviewRefused(ValueError):
    """A check the figures don't allow, with the reason a person can act on."""


def check_key(figure: Figure | RejectedFigure) -> tuple[str, str, int, Scope | None, str]:
    """What one check covers: a line item, or one breakdown of it, in one fiscal year and on one
    basis, as one filing states it."""
    return (
        figure.document.id,
        figure.line_item,
        figure.fiscal_year,
        figure.basis_scope,
        figure.breakdown,
    )


def _needed(figure: Figure | RejectedFigure, rules: KpiRules) -> bool:
    return needs_review(figure.basis_scope, figure.line_item, figure.breakdown, rules)


def check_queue(
    store: GraphStore, label_map: LabelMap, checks: Checks, isin: str | None = None
) -> CheckQueue:
    """Every row to check or checked, of one company or all; the page filters by status, so a
    row just checked stays where it was."""
    facts, rejected = store.figures()
    rows = queue_rows(facts, rejected, label_map, checks.rules)
    companies = {r.document.issuer.isin: r.document.issuer for r in rows}
    mine = [r for r in rows if isin is None or r.document.issuer.isin == isin]
    groups: dict[str, CheckGroup] = {}
    for row in mine:
        group = groups.setdefault(row.document.id, CheckGroup(document=row.document, rows=[]))
        group.rows.append(row)
    done = {CheckStatus.accepted, CheckStatus.corrected}
    return CheckQueue(
        reviewer=checks.reviewer,
        counts=CheckCounts(
            to_check=sum(r.status == CheckStatus.to_check for r in mine),
            needs_review=sum(r.status == CheckStatus.needs_review for r in mine),
            done=sum(r.status in done for r in mine),
        ),
        companies=sorted(companies.values(), key=lambda o: o.name),
        groups=sorted(
            groups.values(),
            key=lambda g: (g.document.issuer.name, -g.document.fiscal_year, g.document.doc_type),
        ),
    )


def queue_rows(
    facts: Sequence[Figure],
    rejected: Sequence[RejectedFigure],
    label_map: LabelMap,
    rules: KpiRules,
) -> list[CheckRow]:
    """A row per value each filing states for a figure that needs a check, and one per rejected
    figure that would. Problems come first: rejected figures, then values the filing states
    differently elsewhere (≠), then the rest by statement, line item and year, newest first."""
    statements = list(label_map.statements)
    position = {name: i for i, name in enumerate(label_map.items)}

    # A filing's figures of one line item, year, basis and currency: grouped by the value they
    # state, two groups disagree.
    keyed: dict[tuple[Any, ...], list[Figure]] = defaultdict(list)
    for f in facts:
        if _needed(f, rules):
            keyed[(*check_key(f), f.currency or f.unit)].append(f)
    rows = [
        _fact_row(group, label_map, rules, conflict=len(groups) > 1)
        for stated in keyed.values()
        for groups in [agreeing(stated)]
        for group in groups
    ]
    rows += [_rejected_row(r, label_map, rules) for r in rejected if _needed(r, rules)]

    def order(row: CheckRow) -> tuple[object, ...]:
        item = label_map.items[row.line_item]
        problem = 0 if row.rejected else 1 if row.conflict else 2
        return (
            problem,
            statements.index(item.statement),
            position[row.line_item],
            -row.fiscal_year,
            row.breakdown,
            row.page,
        )

    return sorted(rows, key=order)


def _fact_row(
    group: list[Figure], label_map: LabelMap, rules: KpiRules, conflict: bool
) -> CheckRow:
    shown = min(group, key=lambda f: (f.page, f.id))
    reviews = [f.review for f in group if f.review is not None]
    # A row is checked once every figure stating its value is: a re-extract may keep the check
    # of some and not others.
    review = max(reviews, key=lambda r: r.reviewed_at) if len(reviews) == len(group) else None
    return _row(
        shown,
        [shown.id, *sorted(f.id for f in group if f is not shown)],
        label_map,
        rules,
        review=review,
        status=CheckStatus(review.verdict) if review else CheckStatus.to_check,
        period_start=shown.period_start,
        period_end=shown.period_end,
        as_of=shown.as_of,
        value=shown.value,
        unit=shown.unit,
        scale=shown.scale,
        currency=shown.currency,
        sources=len(group),
        conflict=conflict,
        rejected=None,
    )


def _rejected_row(figure: RejectedFigure, label_map: LabelMap, rules: KpiRules) -> CheckRow:
    review = figure.review
    return _row(
        figure,
        [figure.id],
        label_map,
        rules,
        review=review,
        status=CheckStatus(review.verdict) if review else CheckStatus.needs_review,
        period_start=None,
        period_end=None,
        as_of=None,
        value=None,
        unit=None,
        scale=None,
        currency=None,
        sources=1,
        conflict=False,
        rejected=figure.reason,
    )


def _row(
    shown: Figure | RejectedFigure,
    figure_ids: list[str],
    label_map: LabelMap,
    rules: KpiRules,
    **specific: Any,
) -> CheckRow:
    """The fields a row takes from the figure it shows, whether a Fact or a rejected figure."""
    item = label_map.items[shown.line_item]
    return CheckRow(
        figure_ids=figure_ids,
        document=shown.document,
        line_item=shown.line_item,
        title=item.title,
        statement=label_map.statements[item.statement],
        breakdown=shown.breakdown,
        fiscal_year=shown.fiscal_year,
        basis_scope=shown.basis_scope,
        label=shown.label,
        value_as_written=shown.value_as_written,
        unit_as_written=shown.unit_as_written,
        passage=shown.passage,
        page=shown.page,
        feeds=rules.feeds(shown.line_item, shown.breakdown),
        **specific,
    )


def candidates(figure_id: str, store: GraphStore) -> list[Candidate] | None:
    """What a correction of the figure can pick from its own source: the numbers of its table
    row, or of its paragraph each place it is written. None when there is no such current
    figure."""
    figure = _one(figure_id, store)
    if figure is None:
        return None
    passage = figure.passage
    if passage is None:
        return []
    if passage.kind == "cell":
        return [c for c in store.row_cells(figure_id) if parse_value(c.value_as_written)]
    text = passage.text
    return [
        Candidate(kind="quote", value_as_written=number.text, context=around(text, number))
        for number in numbers_in(text)
    ]


def _one(figure_id: str, store: GraphStore) -> Figure | RejectedFigure | None:
    facts, rejected = store.figures(ids=[figure_id])
    return next(iter([*facts, *rejected]), None)


def record_review(
    figure_ids: Sequence[str],
    verdict: Verdict,
    store: GraphStore,
    files: DocumentFiles,
    checks: Checks,
    *,
    value_as_written: str | None = None,
    cell_id: str | None = None,
    quote: str | None = None,
    now: datetime | None = None,
) -> Review:
    """Record a check of one CHECKS row's figures and return it. A correction gives the right
    value one way: typed, a cell of the figure's table row, or a number of its paragraph.

    Raises NoReviewer without a REVIEWER, LookupError when a figure is not current, and
    ReviewRefused when the check does not fit the figures."""
    if not checks.reviewer:
        raise NoReviewer()
    ids = list(dict.fromkeys(figure_ids))
    if not ids:
        raise ReviewRefused("A check names the figures it covers")
    facts, rejected = store.figures(ids=ids)
    found: dict[str, Figure | RejectedFigure] = {f.id: f for f in [*facts, *rejected]}
    if len(found) != len(ids):
        raise LookupError("Some of these figures are not current: reload CHECKS")
    first = found[ids[0]]
    if not all(_needed(f, checks.rules) for f in found.values()):
        raise ReviewRefused("A figure that feeds no KPI or screen needs no check")
    if len({check_key(f) for f in found.values()}) > 1:
        raise ReviewRefused("One check covers one line item, year and basis of one filing")
    if rejected and len(ids) > 1:
        raise ReviewRefused("A rejected figure is checked on its own")
    if len(agreeing(facts)) > 1:
        raise ReviewRefused("These figures state different values: check each value on its own")
    if verdict == Verdict.accepted and rejected:
        raise ReviewRefused("A rejected figure can only be corrected")

    fixed, cited, quoted = None, None, None
    if verdict == Verdict.corrected:
        given = [v for v in (value_as_written, cell_id, quote) if v]
        if len(given) != 1:
            raise ReviewRefused("Give the right value one way: typed, a cell, or a quote")
        value = value_as_written
        if cell_id:
            cell = next((c for c in store.row_cells(first.id) if c.cell_id == cell_id), None)
            if cell is None:
                raise ReviewRefused("That cell is not in the figure's table row")
            value, cited = cell.value_as_written, cell.cell_id
        if quote:
            quoted = _quoted(first, quote, store, files)
            value = quoted.quote
        try:
            fixed = correction(value or "", first.unit_as_written)
        except InvalidCorrection as error:
            raise ReviewRefused(f"The right value can't be read: {error}") from None

    draft = ReviewDraft(
        verdict=verdict,
        reviewer=checks.reviewer,
        reviewed_at=now or datetime.now(UTC),
        correction=fixed,
        cell_id=cited,
        quoted=quoted,
    )
    review_id = store.record_review(ids, draft)
    # The check as the figures now read it, with the source a correction cites; a reopening
    # leaves them with none.
    read = _one(first.id, store)
    if read is not None and read.review is not None and read.review.id == review_id:
        return read.review
    return Review(
        id=review_id, verdict=draft.verdict, reviewer=draft.reviewer, reviewed_at=draft.reviewed_at
    )


def _quoted(
    figure: Figure | RejectedFigure, quote: str, store: GraphStore, files: DocumentFiles
) -> QuotedSource:
    passage = figure.passage
    if (
        passage is None
        or passage.kind != "span"
        or quote not in {n.text for n in numbers_in(passage.text)}
    ):
        raise ReviewRefused("That number is not in the figure's paragraph")
    document = store.get_document(figure.document.id)
    if document is None:
        raise LookupError(f"no document {figure.document.id}")
    near = [(b.page, b.left, b.top, b.right, b.bottom) for b in passage.boxes]
    boxes = files.quote_near(document.sha256, passage.page, quote, near)
    if boxes is None:
        raise ReviewRefused("That number is not in the page's text layer: type it instead")
    return QuotedSource(page=passage.page, quote=quote, text=passage.text, boxes=boxes)
