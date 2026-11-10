"""CHECKS (#19 R4, R9, R10; #23): the figures a person must check before they count, and the
checks themselves. Only consolidated figures that feed a KPI or screen need one."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.dossier import agreeing
from bloomberg_invest.domain.figures import parse_value
from bloomberg_invest.domain.kpis import KpiRules
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.review import (
    InvalidCorrection,
    QuotedSource,
    ReviewDraft,
    Verdict,
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
    Proposed,
    RecordedReview,
)

StatusFilter = Literal["open", "needs_review", "done", "all"]
SHOWN: dict[StatusFilter, set[str]] = {
    "open": {"to_check", "needs_review"},
    "needs_review": {"needs_review"},
    "done": {"accepted", "corrected"},
    "all": {"to_check", "needs_review", "accepted", "corrected"},
}
CONTEXT = 32  # characters shown on each side of a number a correction can pick


@dataclass(frozen=True)
class Checks:
    """What checking needs: the KPI rules that say which figures need a check, and who checks.
    One app runs per laptop (#19 Scope), so the reviewer is a setting."""

    rules: KpiRules
    reviewer: str | None


class ReviewRequest(BaseModel):
    """A check of one CHECKS row. A correction gives the right value one way: typed, or picked
    from the figure's own source (`GET /api/figures/{id}/candidates`)."""

    figure_ids: list[str] = Field(min_length=1)
    verdict: Verdict
    value_as_written: str | None = None  # typed
    cell_id: str | None = None  # picked from the figure's table row
    quote: str | None = None  # picked from the figure's paragraph


class NoReviewer(Exception):
    """Checks are refused until the app knows who checks."""

    def __str__(self) -> str:
        return "Set REVIEWER in .env to record checks"


class ReviewRefused(ValueError):
    """A check the figures don't allow, with the reason a person can act on."""


def gated(figure: Figure, rules: KpiRules) -> Figure:
    """The figure, flagged when it feeds a KPI or screen and nobody checked it (#23 AC2)."""
    needed = figure.review is None and needs_review(
        figure.basis_scope, figure.line_item, figure.breakdown, rules
    )
    return figure.model_copy(update={"needs_review": needed})


def check_queue(
    store: GraphStore,
    label_map: LabelMap,
    checks: Checks,
    isin: str | None = None,
    status: StatusFilter = "open",
) -> CheckQueue:
    facts, rejected = store.checkable()
    rows = queue_rows(facts, rejected, label_map, checks.rules)
    companies = {r.document.issuer.isin: r.document.issuer for r in rows}
    mine = [r for r in rows if isin is None or r.document.issuer.isin == isin]
    groups: dict[str, CheckGroup] = {}
    for row in mine:
        if row.status in SHOWN[status]:
            group = groups.setdefault(row.document.id, CheckGroup(document=row.document, rows=[]))
            group.rows.append(row)
    return CheckQueue(
        reviewer=checks.reviewer,
        counts=CheckCounts(
            to_check=sum(r.status == "to_check" for r in mine),
            needs_review=sum(r.status == "needs_review" for r in mine),
            done=sum(r.status in ("accepted", "corrected") for r in mine),
        ),
        companies=sorted(companies.values(), key=lambda o: o.name),
        groups=sorted(
            groups.values(),
            key=lambda g: (g.document.issuer.name, -g.document.fiscal_year, g.document.doc_type),
        ),
    )


def queue_rows(
    facts: Sequence[Figure], rejected: Sequence[Proposed], label_map: LabelMap, rules: KpiRules
) -> list[CheckRow]:
    """A row per value each filing states for a figure that needs a check, and one per rejected
    figure that would. Problems come first: rejected figures, then values the filing states
    differently elsewhere (≠), then the rest by statement, line item and year, newest first."""
    statements = list(label_map.statements)
    position = {name: i for i, name in enumerate(label_map.items)}

    def needed(line_item: str, scope: str | None, breakdown: str) -> bool:
        return line_item in label_map.items and needs_review(scope, line_item, breakdown, rules)

    # A filing's figures of one line item, year, basis and currency: grouped by the value they
    # state, two groups disagree.
    keyed: dict[tuple[str, ...], list[Figure]] = defaultdict(list)
    for f in facts:
        if needed(f.line_item, f.basis_scope, f.breakdown):
            key = (f.document.id, f.line_item, str(f.fiscal_year), f.basis_scope, f.breakdown)
            keyed[(*key, f.currency or f.unit)].append(f)
    rows = [
        _fact_row(group, label_map, rules, conflict=len(groups) > 1)
        for stated in keyed.values()
        for groups in [agreeing(stated)]
        for group in groups
    ]
    rows += [
        _rejected_row(p, label_map, rules)
        for p in rejected
        if needed(p.line_item, p.basis_scope, p.breakdown)
    ]

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
    shown = min(group, key=lambda f: (f.passage.page, f.id))
    reviews = [f.review for f in group if f.review is not None]
    # A row is checked once every figure stating its value is: a re-extract may keep the check
    # of some and not others.
    review = max(reviews, key=lambda r: r.reviewed_at) if len(reviews) == len(group) else None
    item = label_map.items[shown.line_item]
    return CheckRow(
        figure_ids=[shown.id, *sorted(f.id for f in group if f is not shown)],
        document=shown.document,
        line_item=shown.line_item,
        title=item.title,
        statement=label_map.statements[item.statement],
        breakdown=shown.breakdown,
        fiscal_year=shown.fiscal_year,
        basis_scope=shown.basis_scope,
        period_start=shown.period_start,
        period_end=shown.period_end,
        as_of=shown.as_of,
        label=shown.label,
        value_as_written=shown.value_as_written,
        unit_as_written=shown.unit_as_written,
        value=shown.value,
        unit=shown.unit,
        scale=shown.scale,
        currency=shown.currency,
        passage=shown.passage,
        page=shown.passage.page,
        sources=len(group),
        conflict=conflict,
        rejected=None,
        feeds=rules.feeds(shown.line_item, shown.breakdown),
        review=review,
        status=review.verdict if review else "to_check",
    )


def _rejected_row(p: Proposed, label_map: LabelMap, rules: KpiRules) -> CheckRow:
    item = label_map.items[p.line_item]
    return CheckRow(
        figure_ids=[p.id],
        document=p.document,
        line_item=p.line_item,
        title=item.title,
        statement=label_map.statements[item.statement],
        breakdown=p.breakdown,
        fiscal_year=p.fiscal_year,
        basis_scope=p.basis_scope,
        period_start=None,
        period_end=None,
        as_of=None,
        label=p.label,
        value_as_written=p.value_as_written,
        unit_as_written=p.unit_as_written,
        value=None,
        unit=None,
        scale=None,
        currency=None,
        passage=p.passage,
        page=p.page,
        sources=1,
        conflict=False,
        rejected=p.reason,
        feeds=rules.feeds(p.line_item, p.breakdown),
        review=p.review,
        status=p.review.verdict if p.review else "needs_review",
    )


def candidates(figure_id: str, store: GraphStore) -> list[Candidate] | None:
    """What a correction of the figure can pick from its own source: the numbers of its table
    row, or of its paragraph. None when there is no such current figure."""
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
        Candidate(kind="quote", value_as_written=number, context=_around(text, number))
        for number in numbers_in(text)
    ]


def _around(text: str, number: str) -> str:
    """The number with the words around it, cut at whole words."""
    start = text.index(number)
    end = start + len(number)
    before, after = text[max(0, start - CONTEXT) : start], text[end : end + CONTEXT]
    if start > CONTEXT:
        before = "…" + before[before.find(" ") + 1 :]
    if end + CONTEXT < len(text):
        after = after[: after.rfind(" ")] + "…"
    return before + number + after


def _one(figure_id: str, store: GraphStore) -> Figure | Proposed | None:
    facts, rejected = store.checkable(ids=[figure_id])
    return next(iter([*facts, *rejected]), None)


def record_review(
    request: ReviewRequest,
    store: GraphStore,
    files: DocumentFiles,
    checks: Checks,
    now: datetime | None = None,
) -> RecordedReview:
    """Record a check of one CHECKS row's figures and return it. Raises NoReviewer without a
    REVIEWER, LookupError when a figure is not current, ReviewRefused when the check does not
    fit the figures."""
    if not checks.reviewer:
        raise NoReviewer()
    ids = list(dict.fromkeys(request.figure_ids))
    facts, rejected = store.checkable(ids=ids)
    found: dict[str, Figure | Proposed] = {f.id: f for f in [*facts, *rejected]}
    if len(found) != len(ids):
        raise LookupError("Some of these figures are not current: reload CHECKS")
    first = found[ids[0]]
    keys = {
        (f.document.id, f.line_item, f.fiscal_year, f.basis_scope, f.breakdown)
        for f in found.values()
    }
    if len(keys) > 1:
        raise ReviewRefused("One check covers one line item, year and basis of one filing")
    if request.verdict == Verdict.accepted and rejected:
        raise ReviewRefused("A rejected figure can only be corrected")

    fixed, cell_id, quoted = None, None, None
    if request.verdict == Verdict.corrected:
        given = [v for v in (request.value_as_written, request.cell_id, request.quote) if v]
        if len(given) != 1:
            raise ReviewRefused("Give the right value one way: typed, a cell, or a quote")
        value = request.value_as_written
        if request.cell_id:
            cell = next(
                (c for c in store.row_cells(first.id) if c.cell_id == request.cell_id), None
            )
            if cell is None:
                raise ReviewRefused("That cell is not in the figure's table row")
            value, cell_id = cell.value_as_written, cell.cell_id
        if request.quote:
            quoted = _quoted(first, request.quote, store, files)
            value = quoted.quote
        try:
            fixed = correction(value or "", first.unit_as_written)
        except InvalidCorrection as error:
            raise ReviewRefused(f"The right value can't be read: {error}") from None

    draft = ReviewDraft(
        verdict=request.verdict,
        reviewer=checks.reviewer,
        reviewed_at=now or datetime.now(UTC),
        correction=fixed,
        cell_id=cell_id,
        quoted=quoted,
    )
    review_id = store.record_review(ids, draft)
    return RecordedReview(
        id=review_id,
        verdict=draft.verdict,
        reviewer=draft.reviewer,
        reviewed_at=draft.reviewed_at,
        value_as_written=fixed.value_as_written if fixed else None,
        value=fixed.value if fixed else None,
    )


def _quoted(
    figure: Figure | Proposed, quote: str, store: GraphStore, files: DocumentFiles
) -> QuotedSource:
    passage = figure.passage
    if passage is None or passage.kind != "span" or quote not in numbers_in(passage.text):
        raise ReviewRefused("That number is not in the figure's paragraph")
    document = store.get_document(figure.document.id)
    if document is None:
        raise LookupError(f"no document {figure.document.id}")
    near = [(b.page, b.left, b.top, b.right, b.bottom) for b in passage.boxes]
    boxes = files.quote_near(document.sha256, passage.page, quote, near)
    if boxes is None:
        raise ReviewRefused("That number is not in the page's text layer: type it instead")
    return QuotedSource(page=passage.page, quote=quote, text=passage.text, boxes=boxes)
