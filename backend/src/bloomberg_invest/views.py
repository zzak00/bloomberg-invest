"""Read models: the shapes the store returns and the API serves."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from bloomberg_invest.domain.facts import FactKind
from bloomberg_invest.domain.figures import Scope
from bloomberg_invest.domain.model import Bbox, DocType, Organisation, PageInfo, RunInfo
from bloomberg_invest.domain.names import NameStatus, NameVerdict, PartyKind
from bloomberg_invest.domain.review import CheckStatus, Correction, Verdict


class Section(BaseModel):
    id: str
    title: str
    level: int
    page: int
    bbox: Bbox | None
    children: list["Section"] = []


class Run(RunInfo):
    id: str


class DocumentSummary(BaseModel):
    id: str
    issuer: Organisation
    doc_type: DocType
    fiscal_year: int
    regulator: str
    source_url: str | None
    page_count: int
    ingested_at: datetime


class DocumentRef(BaseModel):
    id: str
    issuer: Organisation
    doc_type: DocType
    fiscal_year: int


class Box(BaseModel):
    """A region of a page in PDF points, top-left origin."""

    page: int
    left: float
    top: float
    right: float
    bottom: float


class TablePart(BaseModel):
    """Which part of a split table a Chunk is: parts of one table share `table_id`."""

    table_id: str
    part: int
    parts: int


class Chunk(BaseModel):
    """A Chunk with where to find it: what search returns and the source viewer highlights."""

    id: str
    kind: Literal["text", "table"]
    text: str
    pages: list[int]
    boxes: list[Box]  # the regions of its blocks, which the source viewer highlights
    section_path: list[str]
    table: TablePart | None = None  # tables only
    document: DocumentRef


class DocumentDetail(DocumentSummary):
    sha256: str
    pages: list[PageInfo]
    sections: list[Section]
    run: Run


class Passage(BaseModel):
    """The exact span a Fact cites: a table cell, or a quoted range of a paragraph."""

    kind: Literal["cell", "span"]
    page: int
    boxes: list[Box]  # what the source viewer highlights: the cell, or the quote
    text: str  # the cell's text, or the paragraph's
    quote: str | None = None  # spans: the value as quoted


class Review(BaseModel):
    """A person's check of a figure (#19 R9). On a figure it is the check in force, so accepted or
    corrected: a figure whose latest check reopened it has none."""

    id: str
    verdict: Verdict
    reviewer: str
    reviewed_at: datetime
    correction: Correction | None = None  # the right value, for a correction
    source: Passage | None = None  # the cell or the quote picked; None for a typed value


class Figure(BaseModel):
    """A financial figure Fact (#19 R5, R6): checked against its Passage before it was stored."""

    kind: Literal["financial_figure"] = "financial_figure"
    id: str
    line_item: str  # a line item of the label map
    label: str  # the filing's own wording
    value: str  # exact decimal in the base unit: "36681000000"
    value_as_written: str  # "36 681"
    unit_as_written: str  # as the LLM read it: "MAD millions"
    unit: str  # "MAD", "%", "shares", "MAD/share"
    scale: int  # what the written value is multiplied by: 1, 1 000, 1 000 000...
    currency: str | None
    fiscal_year: int
    period_start: date | None  # flows
    period_end: date | None
    as_of: date | None  # stocks
    basis_scope: Scope
    basis_standard: str
    breakdown: str  # empty for the line item itself, else which part of it
    recorded_at: datetime
    document: DocumentRef
    # What it was read from. The dossier shows a corrected figure with the source of its
    # correction, which a typed value does not have.
    passage: Passage | None
    page: int  # the page it was read on
    review: Review | None  # the check in force; None when nobody checked it (#23 AC4)
    # It feeds a KPI or screen and nobody checked it yet (#19 R10). Set by the service layer,
    # which knows the KPI rules; the store leaves it False.
    needs_review: bool = False


class FigureDetail(Figure):
    """A figure with its line item's title in the current label map, as the viewer names it."""

    line_item_title: str


class Listing(BaseModel):
    """A share's listing on an exchange (#26): what its closes are kept under."""

    ticker: str
    mic: str  # the exchange (ISO 10383): XCAS for the Bourse de Casablanca
    name: str  # as the exchange lists it
    sector: str
    compartment: str


class LastClose(BaseModel):
    """A share's latest close, as the dossier shows it."""

    session: date
    close: str  # a decimal, as the source gave it
    currency: str
    change: str | None  # from the session before, as a fraction (`0.0212`); None for the first
    source: str
    history_start: date  # the first session stored


class Company(BaseModel):
    """An issuer's dossier: its filings, and its listing and last close once it has them."""

    issuer: Organisation
    documents: list[DocumentSummary]
    listing: Listing | None = None
    last_close: LastClose | None = None


class PricePoint(BaseModel):
    session: date
    close: str


class PriceSeries(BaseModel):
    """A share's closes, oldest first: one per session, the exchange's over a manual one."""

    listing: Listing
    closes: list[PricePoint]


class FigureValue(BaseModel):
    """One value a line item takes in a year, and every figure stating it, rounded or not."""

    shown: Figure  # the one a click opens: in the row's unit, from the earliest page
    sources: list[Figure]


class FigureYear(BaseModel):
    fiscal_year: int
    values: list[FigureValue]  # more than one: the filing disagrees with itself


class FigureRow(BaseModel):
    """A line item, or one breakdown of it, in one currency, by fiscal year."""

    line_item: str
    title: str  # the line item's title in the label map
    breakdown: str  # empty for the line item itself
    currency: str  # the currency, or the unit for a percentage or a share count
    unit: str  # the unit and scale most of its figures are written in
    scale: int
    years: list[FigureYear]  # newest first, only years with a value


class StatementFigures(BaseModel):
    key: str
    title: str
    rows: list[FigureRow]  # in the label map's order, the filing's main currency first


class ScopeFigures(BaseModel):
    scope: Scope
    years: list[int]  # every fiscal year with a figure on this basis, newest first
    statements: list[StatementFigures]  # in the label map's order, only those with rows


class FigureGrid(BaseModel):
    """An issuer's current figures as the dossier lists them, on each basis."""

    count: int  # every current figure, on both bases
    scopes: list[ScopeFigures]


class RejectedFigure(BaseModel):
    """What the LLM proposed, and why the check refused it (#19 R6). It has no parsed value; a
    person can only correct it."""

    id: str
    line_item: str
    label: str
    value_as_written: str
    unit_as_written: str
    fiscal_year: int
    basis_scope: Scope | None
    breakdown: str
    recorded_at: datetime
    page: int  # the page the LLM read
    reason: str
    document: DocumentRef
    passage: Passage | None  # None when the id it cited is not on the page
    review: Review | None


class CheckRow(BaseModel):
    """One value to check: every figure of one filing stating it, or one rejected figure."""

    figure_ids: list[str]  # what a check of this row reviews; the one shown first
    document: DocumentRef
    line_item: str
    title: str  # the line item's title in the label map
    statement: str  # its statement's title
    breakdown: str
    fiscal_year: int
    basis_scope: Scope | None
    period_start: date | None
    period_end: date | None
    as_of: date | None
    label: str  # the filing's own wording
    value_as_written: str
    unit_as_written: str
    value: str | None  # parsed, in the base unit; None for a rejected figure
    unit: str | None
    scale: int | None
    currency: str | None
    passage: Passage | None  # the source shown: the earliest page's
    page: int  # the page it was read on: its passage's, or the page the LLM read
    sources: int  # how many passages of the filing state it
    conflict: bool  # the filing states another value for the same line item and year
    rejected: str | None  # why the check refused it, for a rejected figure
    feeds: list[str]  # the KPIs and screens it feeds
    review: Review | None
    status: CheckStatus
    # D4: another filing's check covers this value, which it states too; that filing.
    checked_in: DocumentRef | None = None


class CheckCounts(BaseModel):
    to_check: int
    rejected: int  # rejected figures: they can only be corrected
    done: int


class CheckGroup(BaseModel):
    document: DocumentRef
    rows: list[CheckRow]


class CheckQueue(BaseModel):
    """CHECKS (#19 R9): the figures that feed a KPI or screen, problems first."""

    reviewer: str | None  # who checks on this app; None until REVIEWER is set
    counts: CheckCounts  # for the company asked
    companies: list[Organisation]  # every company with a figure to check or checked
    groups: list[CheckGroup]  # one per filing


class Candidate(BaseModel):
    """A value a correction can pick from the figure's own source: a cell of the same table row,
    or a number in the same paragraph."""

    kind: Literal["cell", "quote"]
    value_as_written: str
    cell_id: str | None = None  # cells
    start: int | None = None  # quotes: where the number begins in the paragraph
    context: str  # the column's header for a cell, the words around a quote


class PartyRef(BaseModel):
    """An Organisation or Person a name resolves to."""

    id: str
    name: str
    kind: PartyKind  # an Aggregate's is `free_float` or `treasury_shares`
    isin: str | None = None  # an issuer's, whose dossier it opens


class Party(BaseModel):
    """A party a fact names: as written, the full name the extractor read, and what it resolves
    to; `resolved` is None until the name is linked or a person resolves it in CHECKS."""

    role: str
    written: str
    name: str
    alias: str  # the Alias key: what CHECKS resolves once for every filing writing it
    resolved: PartyRef | None
    not_a_party: bool = False  # a person said the name is no Organisation or Person


FactValue = str | int | bool | None


class StatedFact(BaseModel):
    """A Fact of one of the eight kinds other than financial figures (#24), checked against its
    Passage before it was stored."""

    id: str
    kind: FactKind
    parties: list[Party]  # in the kind's role order
    values: dict[str, FactValue]  # the kind's fields, as written (`percent`: "53")
    amount_value: str | None = None  # an amount in its base unit, exact
    scale: int | None = None
    currency: str | None = None
    as_of: date | None = None  # as-of kinds
    fiscal_year: int | None = None  # fiscal-year kinds
    period_start: date | None = None
    period_end: date | None = None
    quote: str
    recorded_at: datetime
    document: DocumentRef
    passage: Passage
    page: int
    review: Review | None  # a value a person kept (D5); None until one does


class RejectedFact(BaseModel):
    """A fact the LLM proposed that its quote does not state (#19 R6). Kept with the reason,
    never shown in the dossier."""

    id: str
    kind: FactKind
    parties: list[Party]
    values: dict[str, FactValue]
    quote: str
    recorded_at: datetime
    page: int
    reason: str
    document: DocumentRef
    passage: Passage | None


class KnownParty(BaseModel):
    """An Organisation or Person and every name it is known by, for linking names to it."""

    id: str
    name: str
    kind: PartyKind
    names: list[str]  # its own, its Listings', and the names a person resolved to it


class NameToLink(BaseModel):
    """An Alias the current facts of a filing name that resolves to nothing yet."""

    key: str
    name: str
    kind: PartyKind


class NameSource(BaseModel):
    """Where a filing writes a name: the fact naming it, and the Passage it was read from."""

    fact_id: str
    kind: FactKind
    role: str
    written: str
    quote: str
    document: DocumentRef
    page: int
    passage: Passage


class NameReview(BaseModel):
    """A person's decision about what a name stands for: the one in force on it."""

    id: str
    verdict: NameVerdict
    reviewer: str
    reviewed_at: datetime


class NameCheck(BaseModel):
    """A CHECKS Names row (S7b): a name no rule linked to exactly one Organisation or Person,
    or one a person resolved."""

    alias: str  # the Alias key the decision is recorded on
    name: str  # the full name the extractor read
    kind: PartyKind  # what the extractor proposed it is
    status: NameStatus
    resolved: PartyRef | None  # what it resolves to
    review: NameReview | None  # the decision in force
    sources: list[NameSource]  # every current fact naming it, by filing and page
    candidates: list[PartyRef] = []  # the parties it most likely means, for "Same as"


class Sentence(BaseModel):
    """A fact in one sentence, its value marked: `Société Alpha holds` `53 %` `of Gamma`."""

    before: str
    value: str
    after: str


class FactRow(BaseModel):
    """One dossier row: the value shown for a kind, its parties and details (#19 R8), with every
    fact stating it at its date, and each other value stated then (a Conflict)."""

    kind: FactKind
    shown: StatedFact
    why: Literal["kept", "latest", "annual_report", "earliest"]
    sentence: Sentence
    sources: list[StatedFact]  # every fact stating the shown value at its date, the shown first
    others: list[list[StatedFact]]  # each other value at that date, its facts
    conflict: bool
    # A person kept a value at an earlier date, which this later value replaces.
    kept_earlier: bool = False


class FactSection(BaseModel):
    key: str
    title: str
    rows: list[FactRow]


class CompanyFacts(BaseModel):
    """An issuer's facts of the eight kinds, as the dossier lists them under its figures."""

    count: int  # current facts in the sections
    sections: list[FactSection]  # in the dossier's order, only those with rows
    unlinked: int  # facts of its filings waiting for a name to be checked in CHECKS


class FactSide(BaseModel):
    """One value of a Conflict, as the inspector shows it side by side (S3b)."""

    fact: StatedFact
    sources: int  # facts stating it at that date
    in_use: bool


class FactDetail(StatedFact):
    """A fact as the inspector shows it (S3): in one sentence, and next to every other value
    stated for its key at its date when it is a Conflict."""

    sentence: Sentence
    why: Literal["kept", "latest", "annual_report", "earliest"] | None  # None: not the shown one
    sides: list[FactSide]  # the values at the row's date, the one in use first; one: no Conflict
