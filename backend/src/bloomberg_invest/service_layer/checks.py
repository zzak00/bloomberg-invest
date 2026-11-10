"""CHECKS (#19 R4, R9, R10; #23): the figures a person must check before they count, and the
checks themselves. Only consolidated figures that feed a KPI or screen need one."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.dossier import agreeing
from bloomberg_invest.domain.figures import parse_value
from bloomberg_invest.domain.kpis import KpiRules
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.review import (
    CheckKey,
    CheckStatus,
    InvalidCorrection,
    QuotedSource,
    ReviewDraft,
    Verdict,
    around,
    check_of,
    correction,
    fact_key,
    fact_status,
    needs_check,
    numbers_in,
    refusal,
    rejected_status,
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


def check_queue(
    store: GraphStore, label_map: LabelMap, checks: Checks, isin: str | None = None
) -> CheckQueue:
    """Every row to check or checked, of one company or all; the page filters by status, so a
    row just checked stays where it was."""
    facts, rejected = store.figures()
    rows = queue_rows(facts, rejected, label_map, checks.rules)
    companies = {r.document.issuer.isin: r.document.issuer for r in rows}
    company_rows = [r for r in rows if isin is None or r.document.issuer.isin == isin]
    groups: dict[str, CheckGroup] = {}
    for row in company_rows:
        group = groups.setdefault(row.document.id, CheckGroup(document=row.document, rows=[]))
        group.rows.append(row)
    done = {CheckStatus.accepted, CheckStatus.corrected}
    return CheckQueue(
        reviewer=checks.reviewer,
        counts=CheckCounts(
            to_check=sum(r.status == CheckStatus.to_check for r in company_rows),
            rejected=sum(r.status == CheckStatus.rejected for r in company_rows),
            done=sum(r.status in done for r in company_rows),
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
    keyed: dict[CheckKey, list[Figure]] = defaultdict(list)
    for f in facts:
        if needs_check(f, rules):
            keyed[fact_key(f)].append(f)
    rows = [
        _fact_row(group, label_map, rules, conflict=len(groups) > 1)
        for stated in keyed.values()
        for groups in [agreeing(stated)]
        for group in groups
    ]
    rows += [_rejected_row(r, label_map, rules) for r in rejected if needs_check(r, rules)]

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
    review = check_of([f.review for f in group])
    return _row(
        shown,
        [shown.id, *sorted(f.id for f in group if f is not shown)],
        label_map,
        rules,
        review=review,
        status=fact_status(review),
        sources=len(group),
        conflict=conflict,
    )


def _rejected_row(figure: RejectedFigure, label_map: LabelMap, rules: KpiRules) -> CheckRow:
    review = figure.review
    return _row(
        figure,
        [figure.id],
        label_map,
        rules,
        review=review,
        status=rejected_status(review),
        sources=1,
        conflict=False,
    )


def _row(
    shown: Figure | RejectedFigure,
    figure_ids: list[str],
    label_map: LabelMap,
    rules: KpiRules,
    *,
    review: Review | None,
    status: CheckStatus,
    sources: int,
    conflict: bool,
) -> CheckRow:
    """A row showing a Fact, with what was parsed, or a rejected figure, with why."""
    fact = shown if isinstance(shown, Figure) else None
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
        period_start=fact.period_start if fact else None,
        period_end=fact.period_end if fact else None,
        as_of=fact.as_of if fact else None,
        label=shown.label,
        value_as_written=shown.value_as_written,
        unit_as_written=shown.unit_as_written,
        value=fact.value if fact else None,
        unit=fact.unit if fact else None,
        scale=fact.scale if fact else None,
        currency=fact.currency if fact else None,
        passage=shown.passage,
        page=shown.page,
        sources=sources,
        conflict=conflict,
        rejected=shown.reason if isinstance(shown, RejectedFigure) else None,
        feeds=rules.feeds(shown.line_item, shown.breakdown),
        review=review,
        status=status,
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
        Candidate(
            kind="quote",
            value_as_written=number.text,
            start=number.start,
            context=around(text, number),
        )
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
    quote_start: int | None = None,
    now: datetime | None = None,
) -> Review:
    """Record a check of one CHECKS row's figures and return it. A correction gives the right
    value one way: typed, a cell of the figure's table row, or a number of its paragraph, where
    `quote_start` says it begins (the first place it is written when not given).

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
    reason = refusal(facts, rejected, verdict, checks.rules)
    if reason is not None:
        raise ReviewRefused(reason)
    shown = found[ids[0]]

    fixed, cited, quoted = None, None, None
    if verdict == Verdict.corrected:
        given = [v for v in (value_as_written, cell_id, quote) if v]
        if len(given) != 1:
            raise ReviewRefused("Give the right value one way: typed, a cell, or a quote")
        value = value_as_written
        if cell_id:
            cell = next((c for c in store.row_cells(shown.id) if c.cell_id == cell_id), None)
            if cell is None:
                raise ReviewRefused("That cell is not in the figure's table row")
            value, cited = cell.value_as_written, cell.cell_id
        if quote:
            quoted = _quoted(shown, quote, quote_start, store, files)
            value = quoted.quote
        try:
            fixed = correction(value or "", shown.unit_as_written)
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
    read = _one(shown.id, store)
    if read is not None and read.review is not None and read.review.id == review_id:
        return read.review
    return Review(
        id=review_id, verdict=draft.verdict, reviewer=draft.reviewer, reviewed_at=draft.reviewed_at
    )


def _quoted(
    figure: Figure | RejectedFigure,
    quote: str,
    start: int | None,
    store: GraphStore,
    files: DocumentFiles,
) -> QuotedSource:
    """The number picked in the figure's paragraph, boxed where it was picked."""
    passage = figure.passage
    if passage is None or passage.kind != "span":
        raise ReviewRefused("That number is not in the figure's paragraph")
    written = [n for n in numbers_in(passage.text) if n.text == quote]
    picked = next((n for n in written if start is None or n.start == start), None)
    if picked is None:
        raise ReviewRefused("That number is not in the figure's paragraph")
    document = store.get_document(figure.document.id)
    if document is None:
        raise LookupError(f"no document {figure.document.id}")
    near = [(b.page, b.left, b.top, b.right, b.bottom) for b in passage.boxes]
    # Which time the paragraph writes it, when more than once: boxed there or refused.
    if len(written) > 1:
        boxes = files.quote_near(
            document.sha256, passage.page, quote, near, written.index(picked), len(written)
        )
    else:
        boxes = files.quote_near(document.sha256, passage.page, quote, near)
    if boxes is None:
        raise ReviewRefused(
            "That number can't be found in the page's text layer where it was picked: "
            "type it instead"
        )
    return QuotedSource(page=passage.page, quote=quote, text=passage.text, boxes=boxes)
