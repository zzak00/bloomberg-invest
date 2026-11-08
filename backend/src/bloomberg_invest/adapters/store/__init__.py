"""The graph store interface. The API and the CLI see domain models only, never Cypher."""

from typing import Protocol

from bloomberg_invest.domain.chunking import ChunkDraft
from bloomberg_invest.domain.model import DocumentMeta, ParsedDocument, RunInfo
from bloomberg_invest.views import Chunk, DocumentDetail, DocumentSummary


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

    def search_units(self, document_id: str) -> list[tuple[str, str]]:
        """The Document's current Chunks in reading order: (Chunk id, index text).

        Every Chunk is a search unit; its index text is what gets embedded.
        """

    def record_embeddings(
        self, document_id: str, vectors: dict[str, list[float]], run: RunInfo
    ) -> str:
        """Store an embed Run's vectors, by Chunk id, for the Document; return the Run id.

        A succeeded Run replaces the vectors of earlier embed Runs and supersedes them. A failed
        Run is recorded with no vectors. Every id must be a current search unit of the Document.
        """

    def search_vector(self, vector: list[float], limit: int) -> list[str]:
        """Current Chunk ids whose vectors are nearest the query's, best first."""

    def chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        """The Chunks, in the order given, with their Document, section path, pages and boxes."""

    def list_documents(self) -> list[DocumentSummary]: ...

    def get_document(self, document_id: str) -> DocumentDetail | None: ...
