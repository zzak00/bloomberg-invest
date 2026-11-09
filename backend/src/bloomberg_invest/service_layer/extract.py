"""Extract a parsed Document's financial figures: page by page with the LLM, each checked against
its cell or paragraph in Python, recorded as one extract Run (#19 R5, R6; the #10 design)."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.llm import LLM
from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.config import Prompt
from bloomberg_invest.domain.extraction import (
    FigureDraft,
    SourceParagraph,
    SpanPassage,
    drafts,
    instructions,
    page_sources,
    pages_to_extract,
    schema,
)
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.model import RunInfo, RunStatus, RunStep


class ExtractFailed(Exception):
    """Extraction failed; a failed extract Run is recorded on the Document."""

    def __init__(self, document_id: str, run_id: str) -> None:
        super().__init__(f"extraction failed, recorded as failed run {run_id} on {document_id}")
        self.document_id = document_id
        self.run_id = run_id


@dataclass(frozen=True)
class Extraction:
    """How figures are extracted: the model, what it is told, and how many pages at once."""

    llm: LLM
    label_map: LabelMap
    prompt: Prompt
    concurrency: int = 4


@dataclass(frozen=True)
class Extracted:
    run_id: str
    pages: int
    figures: int
    rejected: int


def extract_document(
    document_id: str,
    store: GraphStore,
    files: DocumentFiles,
    parser: Parser,
    extraction: Extraction,
) -> Extracted:
    detail = store.get_document(document_id)
    if detail is None:
        raise LookupError(f"no document {document_id}")
    if detail.run.output is None:
        raise ValueError(f"the parse run {detail.run.id} saved no output to extract; re-ingest")

    started_at = datetime.now(UTC)
    pages: list[int] = []

    def run_info(status: RunStatus = RunStatus.succeeded, error: str | None = None) -> RunInfo:
        llm, prompt = extraction.llm, extraction.prompt
        return RunInfo(
            step=RunStep.extract,
            tool=llm.tool,
            tool_version=llm.tool_version,
            config=llm.config
            | {
                "prompt": f"{prompt.name} {prompt.version}",
                "prompt_sha256": prompt.sha256,
                "label_map": extraction.label_map.version,
                "label_map_sha256": extraction.label_map.sha256,
                "parse_run": detail.run.id,
                "pages": str(len(pages)),
            },
            started_at=started_at,
            finished_at=datetime.now(UTC),
            status=status,
            error=error,
        )

    try:
        # The paragraphs and the Cells come from the same parse: the Document's current one.
        paragraphs = [
            SourceParagraph(b.page, b.text, b.boxes)
            for b in parser.read_blocks(files.data_dir / detail.run.output)
            if b.kind in ("heading", "text")
        ]
        cells = store.cells(document_id)
        pages = pages_to_extract(paragraphs, cells)
        label_map = extraction.label_map
        system = instructions(extraction.prompt.text, label_map)
        answer = schema(label_map)

        def extract_page(page: int) -> list[FigureDraft]:
            sources = page_sources(page, paragraphs, cells)
            response = extraction.llm.complete_json(system, sources.prompt, "figures", answer)
            return drafts(response, sources, label_map)

        with ThreadPoolExecutor(max_workers=extraction.concurrency) as pool:
            found = [f for page in pool.map(extract_page, pages) for f in page]
        found = _quoted(found, files, detail.sha256)
    except Exception as error:
        failed = run_info(RunStatus.failed, f"{type(error).__name__}: {error}")
        run_id = store.record_extraction(document_id, [], failed)
        raise ExtractFailed(document_id, run_id) from error
    run_id = store.record_extraction(document_id, found, run_info())
    rejected = sum(f.rejected is not None for f in found)
    return Extracted(run_id, len(pages), len(found) - rejected, rejected)


def _quoted(found: list[FigureDraft], files: DocumentFiles, sha256: str) -> list[FigureDraft]:
    """Spans boxed by their quote in the PDF's text layer where it is there, so the viewer
    highlights the value and not its paragraph (#19 R19)."""
    spans = [f.passage for f in found if isinstance(f.passage, SpanPassage)]
    if not spans:
        return found
    located = iter(files.quote_boxes(sha256, [(s.page, s.quote, s.boxes) for s in spans]))
    quoted = []
    for figure in found:
        if isinstance(figure.passage, SpanPassage) and (boxes := next(located)) is not None:
            passage = replace(figure.passage, boxes=boxes, boxes_from="quote")
            figure = replace(figure, passage=passage)
        quoted.append(figure)
    return quoted
