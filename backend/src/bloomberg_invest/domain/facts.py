"""The eight kinds of Fact other than financial figures (#19 R5, R6, R7, R8; #24). Pure: the LLM
call and the store are elsewhere.

The LLM reads one page as the figure pass shows it, and returns each fact with the id of the cell
or paragraph it read it from, a quote of that text, and every party twice: as written, and as the
full name it means there. Python keeps a fact only when its quote is in its source and every
number it states is in its quote; one that fails is kept, rejected, with the reason.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from bloomberg_invest.domain.dossier import same_number
from bloomberg_invest.domain.extraction import (
    CellPassage,
    PageSources,
    SourceCell,
    SourceParagraph,
    SpanPassage,
)
from bloomberg_invest.domain.figures import Scope, parse_unit, parse_value, scaled
from bloomberg_invest.domain.names import PartyKind, alias_key, fold, name_key
from bloomberg_invest.domain.review import NUMBER


class FactKind(StrEnum):
    shareholding = "shareholding"
    board_seat = "board_seat"
    audit_mandate = "audit_mandate"
    listing = "listing"
    consolidation = "consolidation"
    dividend = "dividend"
    auditor_opinion = "auditor_opinion"
    related_party_agreement = "related_party_agreement"


FieldType = Literal["number", "unit", "text", "choice", "flag", "date", "year"]


@dataclass(frozen=True)
class Field:
    """One value a kind of fact states. `detail` fields are part of its key, not its value; a
    field that is not `compared` is shown but never makes a Conflict."""

    name: str
    type: FieldType
    description: str
    choices: tuple[str, ...] = ()
    optional: bool = False
    detail: bool = False
    compared: bool = True


@dataclass(frozen=True)
class Spec:
    """A kind of fact: who it names, in which roles, and what it states."""

    roles: tuple[str, ...]
    fields: tuple[Field, ...]
    description: str
    # Its parties are its statement: a listing says a company's shares trade on an exchange,
    # whether or not it gives a ticker.
    named_is_stated: bool = False

    @property
    def time(self) -> Literal["as_of", "fiscal_year"]:
        return "as_of" if any(f.name == "as_of" for f in self.fields) else "fiscal_year"


SCOPES = tuple(s.value for s in Scope)
AS_OF = Field("as_of", "date", "the date it holds on, YYYY-MM-DD")
FISCAL_YEAR = Field("fiscal_year", "year", "the fiscal year it belongs to")
SCOPE = Field("basis_scope", "choice", "group accounts or the parent's own", SCOPES, detail=True)

SPECS: dict[FactKind, Spec] = {
    FactKind.shareholding: Spec(
        ("holder", "held"),
        (
            Field("percent", "number", "the share held, as written, without %", optional=True),
            Field("shares", "number", "the number of shares held, as written", optional=True),
            Field(
                "rights",
                "choice",
                "share of the capital or of the votes",
                ("capital", "voting"),
                detail=True,
            ),
            AS_OF,
        ),
        "who holds how much of a company's capital or votes",
    ),
    FactKind.board_seat: Spec(
        ("member", "company"),
        (
            Field(
                "body",
                "choice",
                "the board, a committee of it, or the executive team",
                ("board", "audit_committee", "other_committee", "executive"),
                detail=True,
            ),
            Field("role", "text", "the role as written: member, chairman, chief executive..."),
            Field(
                "status",
                "choice",
                "whether the member holds the seat on that date, was "
                "appointed to it then, or left it then",
                ("serving", "appointed", "left"),
            ),
            AS_OF,
        ),
        "a person or organisation sitting on a company's board, a committee or its executive",
    ),
    FactKind.audit_mandate: Spec(
        ("auditor", "company"),
        (
            SCOPE,
            Field("partner", "text", "the signing partner's name", optional=True),
            FISCAL_YEAR,
        ),
        "an audit firm auditing a company's accounts for a fiscal year",
    ),
    FactKind.listing: Spec(
        ("company", "exchange"),
        (
            Field("ticker", "text", "the ticker", optional=True),
            Field("isin", "text", "the ISIN", optional=True),
            Field("compartment", "text", "the market compartment", optional=True),
            Field("sector", "text", "the sector the exchange lists it under", optional=True),
            AS_OF,
        ),
        "a company's shares listed on an exchange",
        named_is_stated=True,
    ),
    FactKind.consolidation: Spec(
        ("parent", "subsidiary"),
        (
            Field(
                "interest",
                "number",
                "the percentage of interest, as written, without %",
                optional=True,
            ),
            Field(
                "control",
                "number",
                "the percentage of control or votes, as written, without %",
                optional=True,
            ),
            Field(
                "method",
                "choice",
                "full consolidation (IG), equity method (ME) or proportional (IP)",
                ("full", "equity", "proportional"),
            ),
            AS_OF,
        ),
        "a subsidiary or joint venture in a group's consolidation scope",
    ),
    FactKind.dividend: Spec(
        ("company",),
        (
            Field(
                "measure",
                "choice",
                "per share, or the total for all shares",
                ("per_share", "total"),
                detail=True,
            ),
            Field("amount", "number", "the amount, as written"),
            Field("unit", "unit", 'the unit as stated: "MAD", "MAD millions", "MAD billions"...'),
            Field(
                "status",
                "choice",
                "proposed to the shareholders' meeting, or paid",
                ("proposed", "paid"),
                compared=False,
            ),
            FISCAL_YEAR,
        ),
        "the dividend a company declares for a fiscal year's result, per share or in total",
    ),
    FactKind.auditor_opinion: Spec(
        ("company",),
        (
            SCOPE,
            Field(
                "opinion",
                "choice",
                "the auditors' opinion",
                ("unqualified", "qualified", "adverse", "disclaimer"),
            ),
            Field(
                "emphasis", "flag", "whether the report adds an emphasis of matter (observation)"
            ),
            FISCAL_YEAR,
        ),
        "the auditors' opinion on a company's accounts for a fiscal year",
    ),
    FactKind.related_party_agreement: Spec(
        ("company", "counterparty"),
        (
            Field(
                "nature",
                "text",
                "what it covers in a few words: revenue, charges, "
                "receivables, payables, remuneration, a named agreement...",
                detail=True,
            ),
            Field("amount", "number", "the amount, as written", optional=True),
            Field("unit", "unit", "the unit as stated", optional=True),
            FISCAL_YEAR,
        ),
        "a transaction or agreement between a company and a related party",
    ),
}


# What a table writes for a stake too small to state: a value of its own, never a number.
NOT_SIGNIFICANT = frozenset({"ns", "n.s.", "n.s"})


class FactRejection(StrEnum):
    """Why a proposed fact is not a Fact (#19 R6, for facts stated in words)."""

    unknown_source = "its source id is not on the page"
    quote_not_in_source = "its quote is not in its source"
    number_not_in_quote = "a number it states is not in its quote"
    unreadable_number = "a number it states is not one number"
    unknown_unit = "its unit names no currency"
    unreadable_date = "its date is not a date"
    year_not_on_page = "its year is not on its page"
    not_in_cited_cell = "its number is not in the cell it cites"
    unnamed = "a party has no name"
    no_value = "it states nothing"


@dataclass(frozen=True)
class NameDraft:
    """A party as the fact names it: as written, the full name it means, and the key its Alias
    is matched by."""

    role: str
    written: str
    name: str
    kind: PartyKind
    key: str


@dataclass(frozen=True)
class FactDraft:
    """A fact the LLM proposed, checked; `rejected` says why it is not a Fact."""

    kind: FactKind
    page: int
    source_id: str
    quote: str
    names: tuple[NameDraft, ...]
    values: dict[str, Any]  # each field of the kind, as the LLM gave it (None when not stated)
    passage: CellPassage | SpanPassage | None
    rejected: FactRejection | None = None
    # Derived in Python: a dividend's or agreement's amount in its base unit.
    amount_value: str | None = None
    scale: int | None = None
    currency: str | None = None
    period: tuple[date, date] | None = None


def name_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "written": {"type": "string"},
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": [k.value for k in PartyKind]},
        },
        "required": ["written", "name", "kind"],
        "additionalProperties": False,
    }


def _field_schema(f: Field) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": {"type": "string"},
        "unit": {"type": "string"},
        "text": {"type": "string"},
        "choice": {"type": "string", "enum": list(f.choices)},
        "flag": {"type": "boolean"},
        "date": {"type": "string"},
        "year": {"type": "integer"},
    }[f.type]
    if f.optional:
        if "enum" in base:
            return {"type": ["string", "null"], "enum": [*f.choices, None]}
        return {**base, "type": [base["type"], "null"]}
    return base


def schema() -> dict[str, Any]:
    """The JSON the LLM must return: one list per kind, strict, so every field is present."""
    lists = {}
    for kind, spec in SPECS.items():
        properties: dict[str, Any] = {role: name_schema() for role in spec.roles}
        properties |= {f.name: _field_schema(f) for f in spec.fields}
        properties |= {"source_id": {"type": "string"}, "quote": {"type": "string"}}
        lists[kind.value] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        }
    return {
        "type": "object",
        "properties": lists,
        "required": list(lists),
        "additionalProperties": False,
    }


def instructions(prompt: str) -> str:
    """The prompt followed by every kind, its parties and what it states."""
    lines = []
    for kind, spec in SPECS.items():
        lines.append(f"- {kind.value}: {spec.description}. Parties: {', '.join(spec.roles)}.")
        lines += [
            f"  - {f.name}: {f.description}" + (" (null when not stated)" if f.optional else "")
            for f in spec.fields
        ]
    return prompt + "\n".join(lines)


Heading = tuple[str, int, int]  # a section's title, level and first page


def section_path(headings: Sequence[Heading], page: int) -> list[str]:
    """The sections a page is in, outermost first: what its heading pages say about it. A page
    on its own can be a table of signatures; its section says whose report they sign.
    `headings` are in reading order."""
    path: list[tuple[int, str]] = []
    for title, level, first in headings:
        if first > page:
            break
        path = [p for p in path if p[0] < level] + [(level, title)]
    return [title for _, title in path]


def page_prompt(sources: PageSources, path: Sequence[str]) -> str:
    """The page as the facts pass shows it: its sections, then its paragraphs and tables."""
    return (f"Section: {' > '.join(path)}\n" if path else "") + sources.prompt


def pages_with_text(
    paragraphs: Sequence[SourceParagraph], cells: Sequence[SourceCell]
) -> list[int]:
    """Every page holding a paragraph or a table: any of them can state a fact."""
    return sorted({p.page for p in paragraphs} | {c.page for c in cells})


def drafts(
    response: dict[str, Any], sources: PageSources, path: Sequence[str] = ()
) -> list[FactDraft]:
    """Each fact the LLM returned for the page, checked against its source. `path` is the
    sections the page is in, whose headings may write its year."""
    return [
        _draft(FactKind(kind), item, sources, path)
        for kind in SPECS
        for item in response.get(kind.value, [])
    ]


def _draft(
    kind: FactKind, item: dict[str, Any], sources: PageSources, path: Sequence[str]
) -> FactDraft:
    spec = SPECS[kind]
    source_id, quote = item["source_id"], item["quote"]
    cell = sources.cells.get(source_id)
    paragraph = sources.paragraphs.get(source_id)
    passage: CellPassage | SpanPassage | None = None
    evidence, numbers, cited = None, set(), None
    if cell is not None:
        # A row's cells hold one number each, or a few the parser ran together: read them cell
        # by cell, so `46 | 111` is never the one number `46 111`.
        # A table states a fact along the cell's row, or down its column: a signature block is
        # a firm, its partner and a title, one column per firm.
        passage = CellPassage(cell.id)
        row = row_cells(cell, sources.cells.values())
        column = column_cells(cell, sources.cells.values())
        line = next(
            (
                cells
                for cells in (row, column)
                if plain(quote) in plain(" ".join(c.text for c in cells))
            ),
            row,
        )
        evidence = " ".join(c.text for c in line)
        if _label_then_cell(quote, cell, row):
            # The row's label, then the cited cell: the columns between are left out.
            evidence = quote
        numbers = {n for c in line for n in _numbers(c.text)}
        cited = _numbers(cell.text)
    elif paragraph is not None:
        passage = SpanPassage(paragraph.page, quote, paragraph.text, paragraph.boxes)
        evidence = _following(source_id, sources)
        numbers = _numbers(quote)
    values = {f.name: item.get(f.name) for f in spec.fields}
    names = _names(spec, item)
    draft = FactDraft(kind, sources.page, source_id, quote, names, values, passage)

    page = " ".join(
        [
            *path,
            *(p.text for p in sources.paragraphs.values()),
            *(c.text for c in sources.cells.values()),
        ]
    )
    reason = _refusal(spec, values, names, quote, evidence, numbers, cited, page)
    if reason is not None:
        return replace(draft, rejected=reason)
    if "unit" in values and values.get("amount") is not None:
        unit = parse_unit(values["unit"] or "")
        amount = parse_value(values["amount"])
        if unit is None or unit.currency is None or amount is None:
            return replace(draft, rejected=FactRejection.unknown_unit)
        draft = replace(
            draft,
            amount_value=scaled(amount, unit),
            scale=unit.scale,
            currency=unit.currency,
        )
    if spec.time == "fiscal_year":
        year = values["fiscal_year"]
        draft = replace(draft, period=(date(year, 1, 1), date(year, 12, 31)))
    return draft


def _names(spec: Spec, item: dict[str, Any]) -> tuple[NameDraft, ...]:
    """The fact's parties. An aggregate (`Autres`, `actions propres`) is keyed by the company
    whose holders it stands for: the fact's other party."""
    given = {role: item[role] for role in spec.roles}
    keys = {role: name_key(n["name"] or n["written"]) for role, n in given.items()}
    names = []
    for role, n in given.items():
        kind = PartyKind(n["kind"])
        other = next((keys[r] for r in spec.roles if r != role), "")
        names.append(
            NameDraft(
                role=role,
                written=n["written"].strip(),
                name=(n["name"] or n["written"]).strip(),
                kind=kind,
                key=alias_key(n["name"] or n["written"], kind, other),
            )
        )
    return tuple(names)


def _refusal(
    spec: Spec,
    values: dict[str, Any],
    names: tuple[NameDraft, ...],
    quote: str,
    evidence: str | None,
    numbers: set[Decimal | None],
    cited: set[Decimal | None] | None,
    page: str,
) -> FactRejection | None:
    """Why the fact is not a Fact (D2): its quote must be in its source, and every number it
    states in its quote, or in its cell's row or column, the first in the cell it cites. Its year
    must be on its page, written whole or in a date (`31-déc.-25`)."""
    if evidence is None:
        return FactRejection.unknown_source
    if not plain(quote) or plain(quote) not in plain(evidence):
        return FactRejection.quote_not_in_source
    if any(not n.key or n.key.endswith(":") for n in names):
        return FactRejection.unnamed
    stated = [f for f in spec.fields if f.compared and values.get(f.name) not in (None, "")]
    if not spec.named_is_stated and not [
        f for f in stated if not (f.type in ("date", "year") or f.detail)
    ]:
        # A shareholding with neither a percentage nor a share count says nothing.
        return FactRejection.no_value
    for f in spec.fields:
        value = values.get(f.name)
        if value in (None, ""):
            continue
        if f.type == "number":
            number = parse_value(value)
            if plain(value) in NOT_SIGNIFICANT and plain(value) in plain(evidence).split():
                continue
            if number is None:
                return FactRejection.unreadable_number
            if number not in numbers:
                return FactRejection.number_not_in_quote
        if f.type == "date" and _date(value) is None:
            return FactRejection.unreadable_date
    first = next(
        (
            values[f.name]
            for f in spec.fields
            if f.type == "number"
            and values.get(f.name) not in (None, "")
            and plain(values[f.name]) not in NOT_SIGNIFICANT
        ),
        None,
    )
    if cited is not None and first is not None and parse_value(first) not in cited:
        # A table states the fact along its row: its main number is in the cell it cites, so a
        # voting share is never read from the interest column.
        return FactRejection.not_in_cited_cell
    year = values["fiscal_year"] if spec.time == "fiscal_year" else _date(values["as_of"]).year
    if not _year_on_page(year, page):
        return FactRejection.year_not_on_page
    return None


def _year_on_page(year: int, text: str) -> bool:
    """Whether the page writes the year: whole (`2025`), or ending a date (`31-déc.-25`)."""
    return bool(
        re.search(rf"(?<!\d){year}(?!\d)", text)
        or re.search(rf"\d[-./ ]?\D{{0,6}}[-./]{year % 100:02d}(?![\d,])", text)
    )


def _label_then_cell(quote: str, cell: SourceCell, row: Sequence[SourceCell]) -> bool:
    """Whether the quote is the row's text up to some column, then the cited cell: `Total (b)
    4 518` from a row `Total (b) | 2 841 | 4 518`."""
    q, cited = plain(quote), plain(cell.text)
    if not cited or not q.endswith(cited):
        return False
    label = q[: -len(cited)].strip()
    before = plain(" ".join(c.text for c in row if c.col < cell.col))
    return bool(label) and before.startswith(label)


def row_cells(cell: SourceCell, cells: Iterable[SourceCell]) -> list[SourceCell]:
    """The cells of the cell's table row: a fact read from a table states its row."""
    return sorted(
        (c for c in cells if c.table == cell.table and c.row == cell.row), key=lambda c: c.col
    )


def column_cells(cell: SourceCell, cells: Iterable[SourceCell]) -> list[SourceCell]:
    """The cells of the cell's table column, top to bottom."""
    return sorted(
        (c for c in cells if c.table == cell.table and c.col == cell.col), key=lambda c: c.row
    )


# A quote may run on into the paragraphs right after the one cited: a signature block is a name,
# a partner and a title, each its own paragraph.
FOLLOWING = 3


def _following(source_id: str, sources: PageSources) -> str:
    """The cited paragraph and the few after it on the page, as one text."""
    ids = list(sources.paragraphs)
    start = ids.index(source_id)
    return " ".join(sources.paragraphs[i].text for i in ids[start : start + 1 + FOLLOWING])


def _numbers(text: str) -> set[Decimal | None]:
    """Every number written in the text, as filings write them (`36 681`, `41,2`)."""
    return {parse_value(m.group()) for m in NUMBER.finditer(text)} | {parse_value(text)}


_QUOTES = str.maketrans(
    {
        "’": "'",
        "‘": "'",
        "`": "'",
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "–": "-",
        "\u2014": "-",
        "−": "-",
        "|": " ",
    }
)


def plain(text: str) -> str:
    """Text as a quote is compared: no accents, one kind of quote mark, case and spacing
    ignored."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


# What a fact is as the dossier compares it: who it names and what it states.


@dataclass(frozen=True)
class Stated:
    """A Fact as the rules below read it. `parties` gives each role the identity its name
    resolves to: an Organisation's or Person's id, or the Alias key until a person resolves it."""

    id: str
    kind: FactKind
    parties: tuple[tuple[str, str], ...]  # (role, identity) in the kind's role order
    values: Mapping[str, Any]  # read-only
    scale: int | None  # an amount's, so `3,5` billions agrees with `3 516` millions
    when: date  # its as-of date, or the end of its fiscal year
    annual: bool  # from an annual report, over an issuer page (R8)
    recorded_at: Any
    kept: bool  # a Review in force keeps this value (D5)
    # Where it is read in its filing: page, top, left, and where its quote starts. Facts one Run
    # recorded at once are told apart in the filing's reading order.
    place: tuple[float, ...] = ()


RowKey = tuple[Any, ...]


def row_key(fact: Stated) -> RowKey:
    """What one dossier row shows: a kind, its parties and its details; a fiscal-year kind one
    row per year, an as-of kind one row for every date, showing the latest."""
    spec = SPECS[fact.kind]
    detail = tuple(_text(fact.values.get(f.name)) for f in spec.fields if f.detail)
    year = (fact.values["fiscal_year"],) if spec.time == "fiscal_year" else ()
    return (fact.kind.value, fact.parties, detail, *year)


def agree(a: Stated, b: Stated) -> bool:
    """Two facts with the same key state the same thing: each value the same, numbers within the
    precision they are written to (`53 %` and `53,0 %`). A value one leaves unstated agrees with
    any."""
    for f in SPECS[a.kind].fields:
        if f.detail or not f.compared or f.type in ("date", "year", "unit"):
            continue
        x, y = a.values.get(f.name), b.values.get(f.name)
        if x in (None, "") or y in (None, ""):
            continue
        if f.type == "number":
            scales = (a.scale or 1, b.scale or 1) if f.name == "amount" else (1, 1)
            if not same_number(x, scales[0], y, scales[1]):
                return False
        elif _text(x) != _text(y):
            return False
    return True


def _text(value: Any) -> Any:
    return name_key(value) if isinstance(value, str) else value


def values_of(facts: Sequence[Stated]) -> list[list[Stated]]:
    """The facts grouped by the value they state: two groups at one date are a Conflict."""
    groups: list[list[Stated]] = []
    for fact in facts:
        group = next((g for g in groups if agree(g[0], fact)), None)
        if group is None:
            groups.append([fact])
        else:
            group.append(fact)
    return groups


@dataclass(frozen=True)
class Shown:
    """A dossier row: the fact shown, why, and the values it disagrees with at its date."""

    fact: Stated
    why: Literal["kept", "latest", "annual_report", "earliest"]
    agreeing: tuple[Stated, ...]  # every fact stating the shown value at its date, shown first
    others: tuple[tuple[Stated, ...], ...]  # each other value at the shown date: a Conflict
    # A person kept a value at an earlier date, which a later date's value now replaces: the
    # latest date wins (#19 R8 as settled in #24), and the row says so.
    kept_earlier: bool = False

    @property
    def conflict(self) -> bool:
        return bool(self.others)


def shown(facts: Sequence[Stated]) -> Shown:
    """Which value a row shows (#19 R8): one a person kept; else the latest date's; at one date,
    an annual report's over an issuer page's; else the first recorded. A value kept at an earlier
    date gives way to a later date's."""
    latest = max(f.when for f in facts)
    at_latest = [f for f in facts if f.when == latest]
    groups = values_of(sorted(at_latest, key=lambda f: (f.recorded_at, f.place, f.id)))
    kept = [g for g in groups if any(f.kept for f in g)]
    if kept:
        group, why = kept[0], "kept"
    elif len(groups) == 1:
        group, why = groups[0], "latest"
    else:
        annual = [g for g in groups if any(f.annual for f in g)]
        if len(annual) == 1:
            group, why = annual[0], "annual_report"
        else:
            group, why = (
                min(groups, key=lambda g: min((f.recorded_at, f.place, f.id) for f in g)),
                "earliest",
            )
    first = next((f for f in group if f.kept), None) or min(
        group, key=lambda f: (not f.annual, f.recorded_at, f.place, f.id)
    )
    return Shown(
        fact=first,
        why=why,
        agreeing=(first, *(f for f in group if f is not first)),
        others=tuple(tuple(g) for g in groups if g is not group),
        kept_earlier=any(f.kept and f.when < latest for f in facts),
    )
