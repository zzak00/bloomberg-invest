"""Neo4j implementation of the graph store (ADR 0003).

Neo4j Community enforces uniqueness only. Required properties are enforced by the domain models,
which every write goes through. Reads never return Superseded nodes (ADR 0002).
"""

from datetime import date, datetime

from neo4j import Driver

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.adapters.store.neo4j_store._chunks import _record_chunks
from bloomberg_invest.adapters.store.neo4j_store._cypher import (
    CURRENT,
    EMBEDDABLE_CHUNKS,
    FIGURE_BY_ID,
    LATEST_PARSE,
    LATEST_REVIEW,
    VECTOR_INDEX,
    current,
)
from bloomberg_invest.adapters.store.neo4j_store._embed import _record_embeddings
from bloomberg_invest.adapters.store.neo4j_store._extract import _record_extraction
from bloomberg_invest.adapters.store.neo4j_store._facts import (
    FACT_BY_ID,
    FACT_KINDS,
    PARTIES,
    _fact_or_rejected,
    _record_fact_extraction,
)
from bloomberg_invest.adapters.store.neo4j_store._names import (
    CURRENT_FACTS,
    CURRENT_LINK,
    KNOWN,
    UNLINKED,
    _known,
    _name_check,
    _record_links,
    _record_name_review,
)
from bloomberg_invest.adapters.store.neo4j_store._parse import _record_parse, _record_run
from bloomberg_invest.adapters.store.neo4j_store._prices import (
    PRICE_CONSTRAINTS,
    _add_prices,
    _listing,
    _stored,
    _upsert_listings,
)
from bloomberg_invest.adapters.store.neo4j_store._reads import (
    _boxes,
    _document_ref,
    _either,
    _run,
    _summary,
    _table_part,
    _tree,
)
from bloomberg_invest.adapters.store.neo4j_store._review import _record_review
from bloomberg_invest.domain.chunking import ChunkDraft
from bloomberg_invest.domain.extraction import FigureDraft, SourceCell
from bloomberg_invest.domain.facts import FactDraft
from bloomberg_invest.domain.figures import FINANCIAL_FIGURE
from bloomberg_invest.domain.indexing import EmbedInput
from bloomberg_invest.domain.model import (
    DocumentMeta,
    Organisation,
    PageInfo,
    ParsedDocument,
    RunInfo,
)
from bloomberg_invest.domain.names import AggregateName, NameReviewDraft
from bloomberg_invest.domain.prices import Close, ListedShare, StoredClose
from bloomberg_invest.domain.review import ReviewDraft
from bloomberg_invest.views import (
    Candidate,
    Chunk,
    DocumentDetail,
    DocumentSummary,
    Figure,
    KnownParty,
    Listing,
    NameCheck,
    NameToLink,
    RejectedFact,
    RejectedFigure,
    StatedFact,
)

CONSTRAINTS = [
    ("Document", "id"),
    ("Document", "sha256"),
    ("Run", "id"),
    ("Organisation", "isin"),
    ("Section", "id"),
    ("Chunk", "id"),
    ("Table", "id"),
    ("Cell", "id"),
    ("Fact", "id"),
    ("RejectedFigure", "id"),
    ("Span", "id"),
    ("Review", "id"),
    ("Organisation", "id"),
    ("Person", "id"),
    ("Alias", "key"),
    ("RejectedFact", "id"),
]


INDEXES = [
    # Neo4j quantizes vectors to bits by default; full precision keeps the measured ranking.
    f"""CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS FOR (n:Chunk) ON n.embedding
    OPTIONS {{indexConfig: {{`vector.similarity_function`: 'cosine',
                             `vector.quantization.type`: 'NONE'}}}}""",
]


class Neo4jStore(GraphStore):
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def ensure_schema(self) -> None:
        # Organisations stored before #24 were keyed by ISIN only; facts name them by id.
        self._driver.execute_query(
            "MATCH (o:Organisation) WHERE o.id IS NULL SET o.id = randomUUID()"
        )
        for label, prop in CONSTRAINTS:
            self._driver.execute_query(
                f"CREATE CONSTRAINT {label.lower()}_{prop} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )
        for constraint in PRICE_CONSTRAINTS:
            self._driver.execute_query(constraint)
        for index in INDEXES:
            self._driver.execute_query(index)
        self._driver.execute_query("CALL db.awaitIndexes(60)")

    def record_parse(
        self, meta: DocumentMeta, parsed: ParsedDocument, run: RunInfo, sha256: str
    ) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_parse, meta, parsed, run, sha256)

    def record_failed_parse(self, meta: DocumentMeta, run: RunInfo, sha256: str) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_run, meta, run, sha256)[0]

    def record_chunks(self, document_id: str, chunks: list[ChunkDraft], run: RunInfo) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_chunks, document_id, chunks, run)

    def embed_inputs(self, document_id: str) -> list[EmbedInput]:
        records, _, _ = self._driver.execute_query(
            f"""
            {EMBEDDABLE_CHUNKS}
            RETURN n.id AS id, n.index_text AS text ORDER BY n.index
            """,
            document_id=document_id,
        )
        return [EmbedInput(r["id"], r["text"]) for r in records]

    def record_embeddings(
        self, document_id: str, vectors: dict[str, list[float]], run: RunInfo
    ) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_embeddings, document_id, vectors, run)

    def current_chunk_run(self, document_id: str) -> str | None:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (n:Chunk)-[:FROM_DOCUMENT]->(:Document {{id: $id}})
            WHERE {CURRENT}
            MATCH (n)-[:PRODUCED_BY]->(r:Run)
            RETURN DISTINCT r.id AS id
            """,
            id=document_id,
        )
        # A chunk Run supersedes every earlier one's Chunks in its own transaction.
        if len(records) > 1:
            raise RuntimeError(f"current Chunks of {document_id} come from {len(records)} Runs")
        return records[0]["id"] if records else None

    def cells(self, document_id: str) -> list[SourceCell]:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (:Document {{id: $id}})-[:HAS_TABLE]->(t:Table)-[:HAS_CELL]->(n:Cell)
            WHERE {CURRENT}
            RETURN n, t.index AS table ORDER BY t.index, n.row, n.col
            """,
            id=document_id,
        )
        return [
            SourceCell(
                id=r["n"]["id"],
                table=r["table"],
                page=r["n"]["page"],
                row=r["n"]["row"],
                col=r["n"]["col"],
                col_span=r["n"]["col_span"],
                text=r["n"]["text"],
                bbox=tuple(r["n"]["bbox"]),
            )
            for r in records
        ]

    def record_extraction(self, document_id: str, figures: list[FigureDraft], run: RunInfo) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_extraction, document_id, figures, run)

    def figures(
        self, isin: str | None = None, ids: list[str] | None = None
    ) -> tuple[list[Figure], list[RejectedFigure]]:
        records, _, _ = self._driver.execute_query(
            f"""
            CALL () {{
                MATCH (n:Fact {{kind: $kind}}) RETURN n
                UNION
                MATCH (n:RejectedFigure {{kind: $kind}}) RETURN n
            }}
            WITH n WHERE {CURRENT} AND ($ids IS NULL OR n.id IN $ids)
            MATCH (n)-[:ABOUT]->(o:Organisation) WHERE $isin IS NULL OR o.isin = $isin
            MATCH (n)-[:FROM_DOCUMENT]->(d:Document)
            OPTIONAL MATCH (n)-[:CITES]->(passage:Passage)
            {LATEST_REVIEW}
            RETURN n, d, o, passage, rv, rp
            ORDER BY n.fiscal_year DESC, coalesce(passage.page, n.page), n.line_item, n.breakdown
            """,
            kind=FINANCIAL_FIGURE,
            isin=isin,
            ids=ids,
        )
        read = [_either(r) for r in records]
        return (
            [f for f in read if isinstance(f, Figure)],
            [f for f in read if isinstance(f, RejectedFigure)],
        )

    def figure(self, figure_id: str) -> Figure | RejectedFigure | None:
        records, _, _ = self._driver.execute_query(
            f"""
            WITH $id AS id
            {FIGURE_BY_ID}
            WITH n WHERE n.kind = $kind
            MATCH (n)-[:ABOUT]->(o:Organisation), (n)-[:FROM_DOCUMENT]->(d:Document)
            OPTIONAL MATCH (n)-[:CITES]->(passage:Passage)
            {LATEST_REVIEW}
            RETURN n, d, o, passage, rv, rp
            """,
            id=figure_id,
            kind=FINANCIAL_FIGURE,
        )
        return _either(records[0]) if records else None

    def row_cells(self, figure_id: str) -> list[Candidate]:
        records, _, _ = self._driver.execute_query(
            f"""
            WITH $id AS id
            {FIGURE_BY_ID}
            MATCH (n)-[:CITES]->(cited:Cell)<-[:HAS_CELL]-(t:Table)
            MATCH (t)-[:HAS_CELL]->(c:Cell {{row: cited.row}}) WHERE {current("c")}
            CALL (t, c) {{
                OPTIONAL MATCH (t)-[:HAS_CELL]->(h:Cell {{col: c.col, column_header: true}})
                WITH h ORDER BY h.row
                RETURN collect(h.text) AS headers
            }}
            RETURN c.id AS id, c.text AS text, headers ORDER BY c.col
            """,
            id=figure_id,
        )
        return [
            Candidate(
                kind="cell",
                value_as_written=r["text"],
                cell_id=r["id"],
                context=" ".join(" ".join(h.split()) for h in r["headers"]),
            )
            for r in records
        ]

    def record_review(self, figure_ids: list[str], review: ReviewDraft) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_review, figure_ids, review)

    def record_fact_extraction(self, document_id: str, facts: list[FactDraft], run: RunInfo) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_fact_extraction, document_id, facts, run)

    def facts(
        self, isin: str | None = None, ids: list[str] | None = None
    ) -> tuple[list[StatedFact], list[RejectedFact]]:
        records, _, _ = self._driver.execute_query(
            f"""
            CALL () {{
                MATCH (n:Fact) WHERE n.kind IN $kinds RETURN n
                UNION
                MATCH (n:RejectedFact) RETURN n
            }}
            WITH n WHERE {CURRENT} AND ($ids IS NULL OR n.id IN $ids)
            MATCH (n)-[:ABOUT]->(o:Organisation), (n)-[:FROM_DOCUMENT]->(d:Document)
            WITH n, o, d WHERE $isin IS NULL OR o.isin = $isin OR EXISTS {{
                (n)-[:NAMES]->(:Alias)-[link:ALIAS_OF]->(:Organisation {{isin: $isin}})
                WHERE {CURRENT_LINK}
            }}
            OPTIONAL MATCH (n)-[:CITES]->(passage:Passage)
            {LATEST_REVIEW}
            {PARTIES}
            RETURN n, d, o, passage, rv, rp, parties
            ORDER BY n.kind, coalesce(passage.page, n.page), n.id
            """,
            kinds=FACT_KINDS,
            isin=isin,
            ids=ids,
        )
        read = [_fact_or_rejected(r) for r in records]
        return (
            [f for f in read if isinstance(f, StatedFact)],
            [f for f in read if isinstance(f, RejectedFact)],
        )

    def fact(self, fact_id: str) -> StatedFact | RejectedFact | None:
        records, _, _ = self._driver.execute_query(
            f"""
            WITH $id AS id
            {FACT_BY_ID}
            WITH n WHERE n.kind IN $kinds
            MATCH (n)-[:ABOUT]->(o:Organisation), (n)-[:FROM_DOCUMENT]->(d:Document)
            OPTIONAL MATCH (n)-[:CITES]->(passage:Passage)
            {LATEST_REVIEW}
            {PARTIES}
            RETURN n, d, o, passage, rv, rp, parties
            """,
            id=fact_id,
            kinds=FACT_KINDS,
        )
        return _fact_or_rejected(records[0]) if records else None

    def unlinked_names(self, document_id: str) -> list[NameToLink]:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (d:Document {{id: $id}})
            {CURRENT_FACTS}
            MATCH (n)-[:NAMES]->(a:Alias)
            WHERE NOT coalesce(a.not_a_party, false) AND {UNLINKED}
            RETURN DISTINCT a.key AS key, a.name AS name, a.kind AS kind ORDER BY key
            """,
            id=document_id,
        )
        return [NameToLink(**r.data()) for r in records]

    def known_parties(self) -> list[KnownParty]:
        records, _, _ = self._driver.execute_query(KNOWN)
        return [KnownParty(**k) for k in _known(records)]

    def record_links(
        self,
        document_id: str,
        links: list[tuple[str, str]],
        aggregates: list[tuple[AggregateName, str]],
        run: RunInfo,
    ) -> tuple[str, int]:
        with self._driver.session() as session:
            return session.execute_write(_record_links, document_id, links, aggregates, run)

    def resolved_names(self, keys: list[str]) -> dict[str, str]:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (a:Alias)-[link:ALIAS_OF]->(o:Organisation)
            WHERE a.key IN $keys AND {CURRENT_LINK}
            RETURN a.key AS key, o.id AS id
            """,
            keys=keys,
        )
        return {r["key"]: r["id"] for r in records}

    def names_to_check(self) -> list[NameCheck]:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (n:Fact)-[names:NAMES]->(a:Alias)
            WHERE n.kind IN $kinds AND {CURRENT}
            OPTIONAL MATCH (a)-[link:ALIAS_OF]->(e) WHERE {CURRENT_LINK}
            WITH n, names, a, e, link
            WHERE e IS NULL OR EXISTS {{ (:Review {{id: link.by}}) }}
            MATCH (n)-[:FROM_DOCUMENT]->(d:Document)-[:ISSUED_BY]->(o:Organisation)
            MATCH (n)-[:CITES]->(passage:Passage)
            OPTIONAL CALL (a) {{
                MATCH (rv:Review)-[:REVIEWS]->(a)
                RETURN rv ORDER BY rv.reviewed_at DESC LIMIT 1
            }}
            WITH a, e, rv, n, names, d, o, passage
            ORDER BY o.name, d.fiscal_year DESC, passage.page, n.id
            RETURN a, e, rv, collect({{n: n, role: names.role, written: names.written, d: d,
                                      o: o, passage: passage}}) AS sources
            ORDER BY a.key
            """,
            kinds=FACT_KINDS,
        )
        return [_name_check(r) for r in records]

    def record_name_review(
        self, key: str, review: NameReviewDraft, aggregates: list[AggregateName]
    ) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_name_review, key, review, aggregates)

    def search_vector(self, vector: list[float], limit: int) -> list[str]:
        records, _, _ = self._driver.execute_query(
            f"""
            CYPHER 25
            MATCH (n:Chunk)
            SEARCH n IN (VECTOR INDEX {VECTOR_INDEX} FOR $vector LIMIT $limit) SCORE AS score
            RETURN n.id AS id ORDER BY score DESC
            """,
            vector=vector,
            limit=limit,
        )
        return [r["id"] for r in records]

    def chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        records, _, _ = self._driver.execute_query(
            """
            UNWIND range(0, size($ids) - 1) AS i
            MATCH (n:Chunk {id: $ids[i]})-[:FROM_DOCUMENT]->(d:Document)
            MATCH (d)-[:ISSUED_BY]->(o:Organisation)
            CALL (n) {
                MATCH (n)-[:ON_PAGE]->(p:Page)
                WITH p ORDER BY p.number
                RETURN collect(p.number) AS pages
            }
            RETURN n, d, o, pages
            ORDER BY i
            """,
            ids=chunk_ids,
        )
        return [
            Chunk(
                id=r["n"]["id"],
                kind=r["n"]["kind"],
                text=r["n"]["text"],
                pages=r["pages"],
                boxes=_boxes(r["n"]["boxes"]),
                section_path=r["n"]["section_path"],
                table=_table_part(r["n"]),
                document=_document_ref(r["d"], r["o"]),
            )
            for r in records
        ]

    def list_documents(self, isin: str | None = None) -> list[DocumentSummary]:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (d:Document)-[:ISSUED_BY]->(o:Organisation)
            WHERE $isin IS NULL OR o.isin = $isin
            {LATEST_PARSE}
            CALL (d) {{
                MATCH (d)-[:HAS_PAGE]->(n:Page) WHERE {CURRENT} RETURN count(n) AS pages
            }}
            RETURN d, o, run, pages
            ORDER BY o.name, d.fiscal_year DESC, d.doc_type
            """,
            isin=isin,
        )
        return [_summary(r["d"], r["o"], r["run"], r["pages"]) for r in records]

    def issuer(self, isin: str) -> Organisation | None:
        records, _, _ = self._driver.execute_query(
            """
            MATCH (d:Document)-[:ISSUED_BY]->(o:Organisation {isin: $isin})
            WHERE EXISTS { (:Run {step: 'parse', status: 'succeeded'})-[:PROCESSED]->(d) }
            RETURN o LIMIT 1
            """,
            isin=isin,
        )
        if not records:
            return None
        return Organisation(isin=records[0]["o"]["isin"], name=records[0]["o"]["name"])

    def get_document(self, document_id: str) -> DocumentDetail | None:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (d:Document {{id: $id}})-[:ISSUED_BY]->(o:Organisation)
            {LATEST_PARSE}
            CALL (d) {{
                MATCH (d)-[:HAS_PAGE]->(n:Page) WHERE {CURRENT}
                WITH n ORDER BY n.number
                RETURN collect(n {{.number, .width, .height}}) AS pages
            }}
            CALL (d) {{
                MATCH (d)-[:HAS_SECTION*]->(n:Section) WHERE {CURRENT}
                MATCH (parent)-[:HAS_SECTION]->(n)
                WITH n, CASE WHEN parent:Section THEN parent.id END AS parent_id
                ORDER BY n.order
                RETURN collect(n {{.id, .title, .level, .page, .bbox, parent_id: parent_id}})
                    AS sections
            }}
            RETURN d, o, run, pages, sections
            """,
            id=document_id,
        )
        if not records:
            return None
        r = records[0]
        summary = _summary(r["d"], r["o"], r["run"], len(r["pages"]))
        return DocumentDetail(
            **summary.model_dump(),
            sha256=r["d"]["sha256"],
            pages=[PageInfo(**p) for p in r["pages"]],
            sections=_tree(r["sections"]),
            run=_run(r["run"]),
        )

    def upsert_listings(
        self, mic: str, shares: list[ListedShare], isins: dict[str, str], at: datetime
    ) -> list[str]:
        with self._driver.session() as session:
            return session.execute_write(_upsert_listings, mic, shares, isins, at)

    def tickers(self, mic: str) -> list[str]:
        records, _, _ = self._driver.execute_query(
            "MATCH (l:Listing {mic: $mic}) RETURN l.ticker AS ticker ORDER BY ticker", mic=mic
        )
        return [r["ticker"] for r in records]

    def add_prices(
        self, key: str, closes: list[Close], source: str, currency: str, fetched_at: datetime
    ) -> int:
        with self._driver.session() as session:
            return session.execute_write(_add_prices, key, closes, source, currency, fetched_at)

    def prices(self, key: str, since: date | None = None) -> list[StoredClose]:
        records, _, _ = self._driver.execute_query(
            """
            MATCH (p:Price {listing: $key})
            WHERE NOT coalesce(p.superseded, false) AND ($since IS NULL OR p.date >= $since)
            RETURN p ORDER BY p.date, p.source
            """,
            key=key,
            since=since,
        )
        return [_stored(r) for r in records]

    def last_session(self, key: str, source: str) -> date | None:
        records, _, _ = self._driver.execute_query(
            "MATCH (p:Price {listing: $key, source: $source}) "
            "WHERE NOT coalesce(p.superseded, false) RETURN max(p.date) AS last",
            key=key,
            source=source,
        )
        last = records[0]["last"]
        return last.to_native() if last else None

    def listing(self, isin: str) -> Listing | None:
        records, _, _ = self._driver.execute_query(
            "MATCH (:Organisation {isin: $isin})-[:LISTED_AS]->(l:Listing) "
            "RETURN l ORDER BY l.key LIMIT 1",
            isin=isin,
        )
        return _listing(records[0]["l"]) if records else None
