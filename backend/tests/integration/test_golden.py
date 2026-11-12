"""The golden harness (#22 AC5, #24 AC5): ingest golden v0 once, with the LLM's answers replayed,
then score the figures against `figures.csv`, as #10 scored the extractors, and the other facts
and their names against `golden.md`'s tables (sections 3 and 4.1 to 4.8, D6).

A golden figure is correct when a Fact on its page has the same fiscal year, scope, line item and
number: the check already passed, or it would not be a Fact. #10 measured 148 of 158. A golden
fact is matched when a Fact of its kind names the same golden entities and states its number;
each kind has a floor, set at the first scored run and only ever raised.

The answers come from recordings next to the golden PDF (`data/recordings/`, never committed:
they are derived from the AMMC report). Record one once, live, on the machine that parses, by
naming it in LLM_RECORD (`figures`, `facts`, or both, comma separated):

    LLM_RECORD=facts uv run --extra ingest --env-file <secrets> pytest -m golden -s \\
        tests/integration/test_golden.py
"""

import csv
import os
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest
from conftest import GOLDEN, GOLDEN_PDF, GOLDEN_SHA, PARSE_CACHE, CachedParser, azure_settings
from fakes import FakeEmbedder

pytestmark = [pytest.mark.ingest, pytest.mark.golden]
pytest.importorskip("docling", reason="needs the ingest extra")

from bloomberg_invest import bootstrap, config
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.llm.recording import RecordingLLM, ReplayLLM
from bloomberg_invest.adapters.store.neo4j_store import Neo4jStore
from bloomberg_invest.adapters.tokens import TiktokenCounter
from bloomberg_invest.domain.chunking import Caps
from bloomberg_invest.domain.facts import FactKind
from bloomberg_invest.domain.figures import number, parse_value
from bloomberg_invest.domain.model import DocType, DocumentMeta, Organisation
from bloomberg_invest.domain.names import name_key
from bloomberg_invest.domain.prices import ListedShare
from bloomberg_invest.service_layer.extract import Extraction
from bloomberg_invest.service_layer.facts import FactExtraction
from bloomberg_invest.service_layer.ingest import Ingested, ingest
from bloomberg_invest.service_layer.names import link_names

RECORDINGS = GOLDEN_PDF.parents[1] / "recordings"
# Named like the notebook's recording, so both replay the same answers.
FIGURES_RECORDING = RECORDINGS / f"{GOLDEN_SHA[:12]}-extract-figures-v1.jsonl"
FACTS_RECORDING = RECORDINGS / f"{GOLDEN_SHA[:12]}-extract-facts-v1.jsonl"
# No text layer (p. 26) or unreadable (p. 58) in golden v0, as in #10.
EXCLUDED_PAGES = {26, 58}
TARGET = 148
# Golden facts matched per kind: the first scored run's, only ever raised (a ratchet).
FLOORS = {
    FactKind.shareholding: 32,
    FactKind.board_seat: 3,
    FactKind.audit_mandate: 4,
    FactKind.listing: 3,
    FactKind.consolidation: 15,
    FactKind.dividend: 2,
    FactKind.auditor_opinion: 1,
    FactKind.related_party_agreement: 7,
}
# Golden entities a fact names, of 55.
ENTITY_FLOOR = 42


def llm(recording, name: str):
    """Live and recording when LLM_RECORD names it, replaying otherwise."""
    if name in os.environ.get("LLM_RECORD", "").split(","):
        return RecordingLLM(bootstrap.llm(azure_settings()), recording)
    if recording.exists():
        return ReplayLLM(recording)
    pytest.skip(f"no recording at {recording}; record it once with LLM_RECORD={name}")


@pytest.fixture(scope="module")
def golden(driver, tmp_path_factory) -> Iterator[tuple[Neo4jStore, Ingested]]:
    """Golden v0 ingested once for every score below, on a wiped test database."""
    if not GOLDEN_PDF.exists():
        pytest.skip(f"golden PDF not found at {GOLDEN_PDF}")
    driver.execute_query("MATCH (n) DETACH DELETE n")
    store = Neo4jStore(driver)
    store.ensure_schema()
    meta = DocumentMeta(
        issuer=Organisation(isin="MA0000011488", name="Maroc Telecom"),
        doc_type=DocType.annual_report,
        fiscal_year=2025,
    )
    ingested = ingest(
        GOLDEN_PDF,
        meta,
        store,
        DocumentFiles(tmp_path_factory.mktemp("data")),
        CachedParser(PARSE_CACHE),
        TiktokenCounter(),
        Caps(text=2000, table=1500),
        FakeEmbedder(),
        Extraction(
            llm(FIGURES_RECORDING, "figures"),
            config.label_map(),
            config.extract_prompt(),
            concurrency=4,
        ),
        FactExtraction(llm(FACTS_RECORDING, "facts"), config.facts_prompt(), concurrency=4),
    )
    # As in the stack: the Bourse lists the issuer under its legal name (#26), which the report
    # uses too, and the next link Run reads it.
    store.upsert_listings(
        "XCAS",
        [ListedShare("IAM", "ITISSALAT AL-MAGHRIB", "Télécommunications", "Principal A")],
        {"IAM": meta.issuer.isin},
        datetime(2026, 11, 12, tzinfo=UTC),
    )
    linked = link_names(ingested.document_id, store)
    yield store, replace(ingested, linked=linked)


# Figures (#22 AC5).


def fiscal_year(period: str) -> int:
    """FY2025 and 2025-12-31 are both fiscal year 2025."""
    return int(period[2:]) if period.startswith("FY") else int(period[:4])


def golden_figures() -> list[dict]:
    with (GOLDEN / "figures.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        r | {"page": int(r["page"]), "year": fiscal_year(r["period"])}
        for r in rows
        if r["page"].isdigit() and int(r["page"]) not in EXCLUDED_PAGES and r["period"]
    ]


def outcome(golden: dict, facts: list, rejected: list[dict]) -> str:
    def same_value(f_page, f_year, f_value) -> bool:
        return (f_page, f_year, number(f_value)) == (
            golden["page"],
            golden["year"],
            number(golden["value_as_written"]),
        )

    same = [f for f in facts if same_value(f.passage.page, f.fiscal_year, f.value_as_written)]
    labelled = [
        f
        for f in same
        if (f.line_item, f.basis_scope) == (golden["line_item"], golden["basis_scope"])
    ]
    if labelled:
        return "correct"
    if any(
        same_value(r["page"], r["fiscal_year"], r["value"])
        and (r["line_item"], r["scope"]) == (golden["line_item"], golden["basis_scope"])
        for r in rejected
    ):
        return "rejected by the check"
    return "wrong label" if same else "missing"


def test_golden_figures_are_extracted_as_well_as_in_the_bake_off(golden, driver):
    store, ingested = golden
    facts, _ = store.figures("MA0000011488")
    records, _, _ = driver.execute_query(
        """
        MATCH (n:RejectedFigure)-[:PRODUCED_BY]->(:Run {id: $run})
        RETURN n.page AS page, n.fiscal_year AS fiscal_year, n.value_as_written AS value,
               n.line_item AS line_item, n.basis_scope AS scope, n.reason AS reason
        """,
        run=ingested.extracted.run_id,
    )
    rejected = [dict(r) for r in records]
    golden_rows = golden_figures()
    results = [(g, outcome(g, facts, rejected)) for g in golden_rows]
    counts = Counter(o for _, o in results)

    print(
        f"\n{ingested.extracted.pages} pages, {ingested.extracted.figures} figures, "
        f"{ingested.extracted.rejected} rejected by the check; golden: {dict(counts)}"
    )
    print("| Outcome | Page | Line item | Scope | Year | Value | Label in report |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for g, o in results:
        if o != "correct":
            print(
                f"| {o} | {g['page']} | {g['line_item']} | {g['basis_scope']} | {g['year']} "
                f"| {g['value_as_written']} | {g['raw_label']} |"
            )
    for reason, n in Counter(r["reason"] for r in rejected).items():
        print(f"rejected, {reason}: {n}")

    assert len(golden_rows) == 158
    assert counts["correct"] >= TARGET, dict(counts)


# Entities and facts (#24 AC5), read from golden.md's tables.


def tables(markdown: str) -> dict[str, list[dict[str, str]]]:
    """Each table of golden.md under its heading's number (`3`, `4.1`...), as rows by column."""
    found: dict[str, list[dict[str, str]]] = {}
    heading = None
    header: list[str] | None = None
    for line in markdown.splitlines():
        if m := re.match(r"^#{2,3} (\d+(?:\.\d+)?)\.? ", line):
            heading, header = m.group(1), None
            continue
        if not line.startswith("|") or heading is None:
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
        elif not set("".join(cells)) <= set("-: "):
            found.setdefault(heading, []).append(dict(zip(header, cells, strict=False)))
    return found


@dataclass(frozen=True)
class GoldenEntity:
    id: str
    name: str
    keys: frozenset[str]


# golden.md's notes inside a name: `(p. 32)`, `(typo, p. 44)`, `(Associé, Deloitte Audit)`...
NOTE = re.compile(
    r"\((?:p\.|pp\.|typo|brand|regulator|absorbed|merged|pre-|group label|Associé)[^)]*\)"
)


def golden_entities(rows: list[dict[str, str]]) -> list[GoldenEntity]:
    """Section 3: each entity with the keys of its canonical name and of each alias as written,
    without the notes golden.md adds."""
    entities = []
    for row in rows:
        keys = set()
        for name in [row["Canonical name"], *row["Aliases as written"].split(";")]:
            if "mapped to" in name:
                continue
            name = NOTE.sub("", name).replace('"', "")
            name = name.replace("Madame ", "").replace("Monsieur ", "")
            if key := name_key(name):
                keys.add(key)
        entities.append(GoldenEntity(row["#"], row["Canonical name"], frozenset(keys)))
    return entities


def resolver(entities: list[GoldenEntity]):
    """Which golden entity a name means: by its key, else by the start of a golden.md
    description of a party (`Maroc Telecom (via CMC)`, `Free float (written "Autres"...)`)."""
    by_key = {k: e.id for e in entities for k in e.keys}

    def resolve(name: str) -> str | None:
        start = re.split(r"\s\(|\s-\s|,", name)[0]
        return by_key.get(name_key(name)) or by_key.get(name_key(start))

    return resolve


def first_number(text: str):
    m = re.search(r"\d[\d  ]*(?:,\d+)?", text)
    return parse_value(m.group().strip()) if m else None


@dataclass
class Score:
    matched: list[str]
    missing: list[str]
    extras: int


def party_ids(fact, resolve) -> dict[str, str | None]:
    """Each role's golden entity: by the full name the extractor read, or as written."""
    return {p.role: resolve(p.name) or resolve(p.written) for p in fact.parties}


def same_number(golden: str, written) -> bool:
    expected = first_number(golden)
    return expected is None or (written is not None and parse_value(str(written)) == expected)


def match_kind(kind: FactKind, rows, facts, resolve) -> Score:
    """A golden row is matched by a Fact of its kind naming the same golden entities and stating
    its number, where the row gives one; each Fact matches one row at most."""
    candidates = [f for f in facts if f.kind == kind]
    used: set[str] = set()
    matched, missing = [], []
    for row in rows:
        ok = next((f for f in candidates if f.id not in used and fits(kind, row, f, resolve)), None)
        if ok is None:
            missing.append(row["#"])
        else:
            used.add(ok.id)
            matched.append(row["#"])
    return Score(matched, missing, len(candidates) - len(used))


def fits(kind: FactKind, row: dict[str, str], fact, resolve) -> bool:
    ids, v = party_ids(fact, resolve), fact.values
    match kind:
        case FactKind.shareholding:
            return (
                ids.get("holder") == resolve(row["Holder"])
                and ids.get("held") == resolve(row["Held"])
                and same_number(row["%"], v.get("percent"))
            )
        case FactKind.board_seat:
            return (ids.get("member"), ids.get("company")) == (
                resolve(row["Person / org"]),
                resolve(row["Company"]),
            )
        case FactKind.audit_mandate:
            scope = "consolidated" if "consolidated" in row["Scope"] else "company-only"
            return ids.get("auditor") == resolve(row["Firm"]) and v.get("basis_scope") == scope
        case FactKind.listing:
            exchange = resolve(row["Exchange"])
            return ids.get("company") == resolve(row["Company"]) and (
                exchange is None or ids.get("exchange") == exchange
            )
        case FactKind.consolidation:
            return ids.get("subsidiary") == resolve(row["Subsidiary"]) and same_number(
                row["% interest 2025"], v.get("interest")
            )
        case FactKind.dividend:
            year = int(re.search(r"FY(\d{4})", row["Fiscal year"]).group(1))
            amount = row["Per share"] if row["Per share"][:1].isdigit() else row["Total"]
            return fact.fiscal_year == year and same_number(amount, v.get("amount"))
        case FactKind.auditor_opinion:
            opinion = row["Opinion"].lower()
            scope = "consolidated" if row["Scope"].lower().startswith("consolidated") else None
            return (
                v.get("basis_scope") == (scope or "company-only")
                and str(v.get("opinion")) in opinion
                and bool(v.get("emphasis")) == ("emphasis" in opinion)
            )
        case FactKind.related_party_agreement:
            other = row["Parties"].split(" - ", 1)[-1]
            if fact.fiscal_year != int(row["Year"]):
                return False
            if (counterparty := resolve(other)) is not None:
                return ids.get("counterparty") == counterparty
            # No golden entity: "other Etisalat sister companies", "mandataires sociaux".
            words = set(name_key(f"{other} {row['Covers']}").split())
            written = next((p for p in fact.parties if p.role == "counterparty"), None)
            said = name_key(f"{written.name if written else ''} {v.get('nature') or ''}")
            return bool(words & set(said.split()))
    return False


def statable(kind: FactKind, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """The rows a Fact can state from a quote: golden.md marks the shareholdings the report
    implies but never states ("not stated" in %), SH4 and SH21."""
    if kind != FactKind.shareholding:
        return rows
    return [r for r in rows if not r["%"].startswith("not stated")]


SECTIONS = {
    "4.1": FactKind.shareholding,
    "4.2": FactKind.board_seat,
    "4.3": FactKind.audit_mandate,
    "4.4": FactKind.listing,
    "4.5": FactKind.consolidation,
    "4.6": FactKind.dividend,
    "4.7": FactKind.auditor_opinion,
    "4.8": FactKind.related_party_agreement,
}


def test_golden_md_tables_are_read_as_written():
    found = tables((GOLDEN / "golden.md").read_text())
    assert [len(found[s]) for s in SECTIONS] == [36, 3, 4, 3, 15, 3, 2, 11]
    assert [
        r["#"] for r in found["4.1"] if r not in statable(FactKind.shareholding, found["4.1"])
    ] == [
        "SH4",
        "SH21",
    ]
    entities = golden_entities(found["3"])
    assert len(entities) == 55
    resolve = resolver(entities)
    assert resolve("Itissalat Al-Maghrib (IAM) S.A") == resolve("Maroc Telecom") == "E1"
    assert resolve("Maroc Telecom (via CMC)") == "E1"
    assert resolve("Moov Afrivca Niger") == "E17"
    assert resolve("Lamia Lemkecher") == "P1"
    assert resolve("Autres") is None


def test_golden_facts_and_names_are_extracted_and_linked(golden):
    store, ingested = golden
    found = tables((GOLDEN / "golden.md").read_text())
    entities = golden_entities(found["3"])
    resolve = resolver(entities)
    facts, rejected = store.facts()

    scores = {
        kind: match_kind(kind, statable(kind, found[s]), facts, resolve)
        for s, kind in SECTIONS.items()
    }
    # A golden entity is named when a fact names it; one named several ways is a name CHECKS
    # asks about once per way.
    named: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        for party in fact.parties:
            if (golden_id := resolve(party.name) or resolve(party.written)) is not None:
                named[golden_id].add(party.alias)
    unknown = {
        p.alias
        for f in facts
        for p in f.parties
        if (resolve(p.name) or resolve(p.written)) is None and ":" not in p.alias
    }
    to_check = [n for n in store.names_to_check() if n.status == "to_check"]
    # Names the link Run resolved: each to the golden entity its name means, never another.
    linked = [
        (party, resolve(party.name) or resolve(party.written), resolve(party.resolved.name))
        for f in facts
        for party in f.parties
        if party.resolved is not None and ":" not in party.alias
    ]
    wrong = sorted({(p.written, p.resolved.name) for p, said, got in linked if said != got})

    print(
        f"\n{ingested.facts.pages} pages, {ingested.facts.facts} facts, "
        f"{ingested.facts.rejected} rejected by the check; linked {ingested.linked.linked} "
        f"names, {ingested.linked.to_check} to check"
    )
    print("| Kind | Golden | Matched | Missing | Extra facts |")
    print("| --- | --- | --- | --- | --- |")
    for kind, score in scores.items():
        total = len(score.matched) + len(score.missing)
        print(
            f"| {kind.value} | {total} | {len(score.matched)} | {', '.join(score.missing)} "
            f"| {score.extras} |"
        )
    print(
        f"entities named: {len(named)} of {len(entities)}; not named: "
        f"{', '.join(e.id for e in entities if e.id not in named)}"
    )
    print(
        f"names no golden entity has: {len(unknown)}; names in CHECKS: {len(to_check)}; "
        f"names linked: {len({p.alias for p, _, _ in linked})}, wrongly: {wrong}"
    )
    for reason, n in Counter(r.reason for r in rejected).items():
        print(f"rejected, {reason}: {n}")

    for kind, score in scores.items():
        assert len(score.matched) >= FLOORS[kind], (kind, score)
    assert len(named) >= ENTITY_FLOOR
    assert wrong == []
    # Every Fact cites a Passage on a page of the report, with its time and when it was recorded.
    assert all(f.passage is not None and 1 <= f.page <= 90 for f in facts)
    assert all((f.as_of or f.fiscal_year) and f.recorded_at for f in facts)
