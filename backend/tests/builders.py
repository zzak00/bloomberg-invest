"""Read models built by hand, for service tests that need figures without a store."""

from datetime import UTC, datetime

from bloomberg_invest.domain.figures import Scope
from bloomberg_invest.domain.model import Organisation
from bloomberg_invest.domain.review import Correction
from bloomberg_invest.views import Box, DocumentRef, Figure, Passage, RejectedFigure, Review

MILLIONS, BILLIONS = 1_000_000, 1_000_000_000
DOCUMENT = DocumentRef(
    id="d1",
    issuer=Organisation(isin="MA0000011488", name="Maroc Telecom"),
    doc_type="annual_report",
    fiscal_year=2025,
    currency="MAD",
)


def figure(
    written: str,
    value: str,
    *,
    line_item: str = "revenue",
    year: int = 2025,
    scale: int = MILLIONS,
    currency: str = "MAD",
    breakdown: str = "",
    scope: Scope = Scope.consolidated,
    page: int = 4,
    top: float | None = None,  # where its cell sits on the page
    document: DocumentRef = DOCUMENT,
    review: Review | None = None,
) -> Figure:
    return Figure(
        id=f"{document.id}-{line_item}-{year}-{written}-{page}",
        line_item=line_item,
        label="Chiffre d'affaires",
        value=value,
        value_as_written=written,
        unit_as_written="MAD billions" if scale == BILLIONS else "MAD millions",
        unit=currency,
        scale=scale,
        currency=currency,
        fiscal_year=year,
        period_start=None,
        period_end=None,
        as_of=None,
        basis_scope=scope,
        basis_standard="IFRS",
        breakdown=breakdown,
        recorded_at=datetime(2026, 11, 9, tzinfo=UTC),
        document=document,
        passage=Passage(
            kind="cell",
            page=page,
            boxes=[]
            if top is None
            else [Box(page=page, left=300, top=top, right=350, bottom=top + 16)],
            text=written,
        ),
        page=page,
        review=review,
    )


def rejected(
    written: str,
    *,
    line_item: str = "revenue",
    year: int = 2025,
    reason: str = "its value differs from its cell",
    page: int = 26,
    passage: Passage | None = None,
    review: Review | None = None,
) -> RejectedFigure:
    return RejectedFigure(
        id=f"rejected-{line_item}-{year}-{written}",
        line_item=line_item,
        label="Situation au 01.01.2023",
        value_as_written=written,
        unit_as_written="MAD millions",
        fiscal_year=year,
        basis_scope=Scope.consolidated,
        breakdown="",
        recorded_at=datetime(2026, 11, 9, tzinfo=UTC),
        page=page,
        reason=reason,
        document=DOCUMENT,
        passage=passage,
        review=review,
    )


def review(verdict: str = "accepted", day: int = 10) -> Review:
    return Review(
        id=f"review-{verdict}-{day}",
        verdict=verdict,
        reviewer="Z. Bajjou",
        reviewed_at=datetime(2026, 11, day, tzinfo=UTC),
    )


def corrected(written: str, value: str, *, day: int = 10, source: Passage | None = None) -> Review:
    """A correction in MAD millions, citing the cell or quote picked, or typed."""
    fixed = Correction(
        value_as_written=written,
        unit_as_written="MAD millions",
        value=value,
        unit="MAD",
        scale=MILLIONS,
        currency="MAD",
    )
    return review("corrected", day).model_copy(update={"correction": fixed, "source": source})
