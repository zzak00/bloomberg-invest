"""The graph store interface. The API and the CLI see domain models only, never Cypher."""

from typing import Protocol

from bloomberg_invest.domain.model import DocumentMeta, ParsedDocument, RunInfo
from bloomberg_invest.views import DocumentDetail, DocumentSummary


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

    def list_documents(self) -> list[DocumentSummary]: ...

    def get_document(self, document_id: str) -> DocumentDetail | None: ...
