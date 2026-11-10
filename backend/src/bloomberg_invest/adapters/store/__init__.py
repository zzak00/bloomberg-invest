"""The graph store interface. The API and the CLI see domain models only, never Cypher."""

from typing import Protocol

from bloomberg_invest.domain.chunking import ChunkDraft
from bloomberg_invest.domain.extraction import FigureDraft, SourceCell
from bloomberg_invest.domain.indexing import EmbedInput
from bloomberg_invest.domain.model import DocumentMeta, Organisation, ParsedDocument, RunInfo
from bloomberg_invest.domain.review import ReviewDraft
from bloomberg_invest.views import (
    Candidate,
    Chunk,
    DocumentDetail,
    DocumentSummary,
    Figure,
    Proposed,
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

    def figures(self, isin: str) -> list[Figure]:
        """The issuer's current financial figure Facts, newest fiscal year first."""

    def fact(self, fact_id: str) -> Figure | None:
        """One financial figure Fact, current or not, so a link to it keeps working."""

    def checkable(
        self, isin: str | None = None, ids: list[str] | None = None
    ) -> tuple[list[Figure], list[Proposed]]:
        """Current financial figures with their check in force: the Facts and the
        RejectedFigures, of one issuer or every one, or only those with these ids."""

    def row_cells(self, figure_id: str) -> list[Candidate]:
        """The current cells of the row of the Cell a figure cites, by column, each with its
        column's headers; none for a figure that cites no Cell."""

    def record_review(self, figure_ids: list[str], review: ReviewDraft) -> str:
        """Record a check of these current figures; return the Review id. A correction that
        picked a number in a paragraph gets a Span the Review cites. Raises LookupError when a
        figure is not current, or the cited cell or page is not."""

    def search_vector(self, vector: list[float], limit: int) -> list[str]:
        """Current Chunk ids whose vectors are nearest the query's, best first."""

    def chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        """The Chunks, in the order given, with their Document, section path, pages and boxes."""

    def list_documents(self, isin: str | None = None) -> list[DocumentSummary]:
        """Every ingested filing, or one issuer's."""

    def issuer(self, isin: str) -> Organisation | None:
        """The Organisation with this ISIN, if a filing of it is shown: parsed successfully."""

    def get_document(self, document_id: str) -> DocumentDetail | None: ...
