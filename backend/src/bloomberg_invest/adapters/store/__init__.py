"""The graph store interface. The API and the CLI see domain models only, never Cypher."""

from datetime import date, datetime
from typing import Protocol

from bloomberg_invest.domain.chunking import ChunkDraft
from bloomberg_invest.domain.extraction import FigureDraft, SourceCell
from bloomberg_invest.domain.facts import FactDraft
from bloomberg_invest.domain.indexing import EmbedInput
from bloomberg_invest.domain.model import DocumentMeta, Organisation, ParsedDocument, RunInfo
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


class GraphStore(Protocol):
    def ensure_schema(self) -> None:
        """Create the uniqueness constraints; safe to run on every start."""

    def record_parse(
        self, meta: DocumentMeta, parsed: ParsedDocument, run: RunInfo, sha256: str
    ) -> str:
        """Store a parse of the PDF with this SHA-256 and return the Document id.

        Re-recording the same PDF keeps the Document and supersedes the previous Run's outputs.
        """

    def record_failed_parse(self, meta: DocumentMeta, run: RunInfo, sha256: str) -> str:
        """Record a parse that failed and return the Document id.

        Writes no Pages or Sections and supersedes nothing: the last good parse stays current.
        """

    def record_chunks(self, document_id: str, chunks: list[ChunkDraft], run: RunInfo) -> str:
        """Store a chunk Run's Chunks, with their index text, for the Document; return the Run id.

        A succeeded Run supersedes the Chunks of earlier chunk Runs. A failed Run is recorded
        with no outputs and supersedes nothing.
        """

    def embed_inputs(self, document_id: str) -> list[EmbedInput]:
        """The Document's current Chunks in reading order, with the index text to embed."""

    def record_embeddings(
        self, document_id: str, vectors: dict[str, list[float]], run: RunInfo
    ) -> str:
        """Store an embed Run's vectors, by Chunk id, for the Document; return the Run id.

        A succeeded Run gives a vector to every current Chunk of the Document, no more and
        no fewer, replacing earlier embed Runs' vectors and superseding those Runs. A failed Run
        is recorded with no vectors.
        """

    def current_chunk_run(self, document_id: str) -> str | None:
        """The chunk Run that produced the Document's current Chunks, if any."""

    def cells(self, document_id: str) -> list[SourceCell]:
        """The Document's current table Cells, by table, row and column."""

    def record_extraction(self, document_id: str, figures: list[FigureDraft], run: RunInfo) -> str:
        """Store an extract Run's figures for the Document; return the Run id.

        A figure that passed its check becomes a Fact citing its Passage, one that failed a
        RejectedFigure. A succeeded Run supersedes earlier extract Runs' outputs, and a new figure
        keeps the check of the previous Run's figure that read the same value from the same
        source (#19 R4). A failed one is recorded with no outputs and supersedes nothing.
        """

    def figures(
        self, isin: str | None = None, ids: list[str] | None = None
    ) -> tuple[list[Figure], list[RejectedFigure]]:
        """Current financial figures with their check in force: the Facts and the
        RejectedFigures, of one issuer or every one, or only those with these ids. Newest fiscal
        year first, then by page."""

    def figure(self, figure_id: str) -> Figure | RejectedFigure | None:
        """One financial figure, Fact or RejectedFigure, current or not, so a link to it keeps
        working."""

    def row_cells(self, figure_id: str) -> list[Candidate]:
        """The current cells of the row of the Cell a figure cites, by column, each with its
        column's headers; none for a figure that cites no Cell."""

    def record_review(self, figure_ids: list[str], review: ReviewDraft) -> str:
        """Record a check of these current figures; return the Review id. A correction that
        picked a number in a paragraph gets a Span the Review cites. Raises LookupError when a
        figure is not current, or the cited cell or page is not."""

    def record_fact_extraction(self, document_id: str, facts: list[FactDraft], run: RunInfo) -> str:
        """Store an extract_facts Run's facts for the Document; return the Run id.

        A fact that passed its check becomes a Fact citing its Passage and naming its parties
        through Aliases, merged by key so every filing shares them; one that failed a
        RejectedFact. A succeeded Run supersedes earlier extract_facts Runs' outputs, never an
        Alias, and a new Fact keeps the Review of the previous Run's that read the same thing from
        the same source (#19 R4). A failed one is recorded with no outputs.
        """

    def facts(
        self, isin: str | None = None, ids: list[str] | None = None
    ) -> tuple[list[StatedFact], list[RejectedFact]]:
        """Current facts of the eight kinds with the Review in force: those a filing of the
        issuer states, or naming it, or every one, or only those with these ids."""

    def fact(self, fact_id: str) -> StatedFact | RejectedFact | None:
        """One fact of the eight kinds, current or not, so a link to it keeps working."""

    def unlinked_names(self, document_id: str) -> list[NameToLink]:
        """The Aliases the Document's current Facts name that resolve to nothing, other than
        names a person said are no Organisation or Person."""

    def known_parties(self) -> list[KnownParty]:
        """Every Organisation (but Aggregates) and Person, with every name it is known by."""

    def record_links(
        self,
        document_id: str,
        links: list[tuple[str, str]],
        aggregates: list[tuple[AggregateName, str]],
        run: RunInfo,
    ) -> tuple[str, int]:
        """Record a link Run of the Document: link each (Alias key, party id) not linked yet,
        and each aggregate Alias, with its company's id, to that company's Aggregate, created on
        first use. Return the Run id and how many Aliases it linked."""

    def resolved_names(self, keys: list[str]) -> dict[str, str]:
        """The id of the Organisation each of these Alias keys resolves to now, if any."""

    def names_to_check(self) -> list[NameCheck]:
        """CHECKS Names: each name current Facts write that no rule linked, unresolved or
        resolved by a person, with every fact naming it."""

    def record_name_review(
        self, key: str, review: NameReviewDraft, aggregates: list[AggregateName]
    ) -> str:
        """Record what a person decides the Alias with this key stands for; return the Review
        id. It supersedes the Alias's link and those of `aggregates`, the company's aggregate
        Aliases, which link again to its Aggregate when it resolves to an Organisation. Raises
        LookupError for no such Alias, Organisation or Person."""

    def search_vector(self, vector: list[float], limit: int) -> list[str]:
        """Current Chunk ids whose vectors are nearest the query's, best first."""

    def chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        """The Chunks, in the order given, with their Document, section path, pages and boxes."""

    def list_documents(self, isin: str | None = None) -> list[DocumentSummary]:
        """Every ingested filing, or one issuer's."""

    def issuer(self, isin: str) -> Organisation | None:
        """The Organisation with this ISIN, if a filing of it is shown: parsed successfully."""

    def get_document(self, document_id: str) -> DocumentDetail | None: ...

    def upsert_listings(
        self, mic: str, shares: list[ListedShare], isins: dict[str, str], at: datetime
    ) -> list[str]:
        """Store the shares an exchange lists, linking each to the Organisation whose ISIN
        `isins` gives for its ticker. Return the tickers stored before that the exchange no
        longer lists: they keep their Listing and closes."""

    def tickers(self, mic: str) -> list[str]:
        """Every share stored for the exchange, listed or no longer."""

    def add_prices(
        self, key: str, closes: list[Close], source: str, currency: str, fetched_at: datetime
    ) -> int:
        """Store a share's closes from a source, in one transaction; return how many were
        written. A session and source has one current close: the same close again writes nothing,
        and a different one from a later answer supersedes it, which is kept (#19 R4). Sessions
        with no close are skipped."""

    def prices(self, key: str, since: date | None = None) -> list[StoredClose]:
        """A share's current closes, from every source, oldest first."""

    def last_session(self, key: str, source: str) -> date | None:
        """The latest session the share has a current close for from this source."""

    def listing(self, isin: str) -> Listing | None:
        """The listing of the Organisation with this ISIN, if it has one; the first by key if
        it has several."""
