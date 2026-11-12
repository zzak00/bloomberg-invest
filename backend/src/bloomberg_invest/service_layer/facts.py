"""Extract a parsed Document's facts of the eight other kinds (#24): page by page with the LLM, each
checked against its cell or paragraph in Python, recorded as one extract_facts Run. The figure
pass and its prompt stay as they are (D1)."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.llm import LLM
from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.config import Prompt
from bloomberg_invest.domain.extraction import SourceParagraph, SpanPassage, page_sources
from bloomberg_invest.domain.facts import (
    FactDraft,
    Heading,
    drafts,
    instructions,
    page_prompt,
    pages_with_text,
    schema,
    section_path,
)
from bloomberg_invest.domain.model import RunInfo, RunStatus, RunStep
from bloomberg_invest.views import Section


class FactsFailed(Exception):
    """Extracting facts failed; a failed extract_facts Run is recorded on the Document."""

    def __init__(self, document_id: str, run_id: str) -> None:
        super().__init__(
            f"fact extraction failed, recorded as failed run {run_id} on {document_id}"
        )
        self.document_id = document_id
        self.run_id = run_id


@dataclass(frozen=True)
class FactExtraction:
    """How facts are extracted: the model, what it is told, and how many pages at once."""

    llm: LLM
    prompt: Prompt
    concurrency: int = 4


@dataclass(frozen=True)
class ExtractedFacts:
    run_id: str
    pages: int
    facts: int
    rejected: int


def extract_facts(
    document_id: str,
    store: GraphStore,
    files: DocumentFiles,
    parser: Parser,
    extraction: FactExtraction,
) -> ExtractedFacts:
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
            step=RunStep.extract_facts,
            tool=llm.tool,
            tool_version=llm.tool_version,
            config=llm.config
            | {
                "prompt": f"{prompt.name} {prompt.version}",
                "prompt_sha256": prompt.sha256,
                "parse_run": detail.run.id,
                "pages": str(len(pages)),
            },
            started_at=started_at,
            finished_at=datetime.now(UTC),
            status=status,
            error=error,
        )

    try:
        paragraphs = [
            SourceParagraph(b.page, b.text, b.boxes)
            for b in parser.read_blocks(files.data_dir / detail.run.output)
            if b.kind in ("heading", "text")
        ]
        cells = store.cells(document_id)
        headings = _headings(detail.sections)
        pages = pages_with_text(paragraphs, cells)
        system = instructions(extraction.prompt.text)
        answer = schema()

        def extract_page(page: int) -> list[FactDraft]:
            sources = page_sources(page, paragraphs, cells)
            path = section_path(headings, page)
            response = extraction.llm.complete_json(
                system, page_prompt(sources, path), "facts", answer
            )
            return drafts(response, sources, path)

        with ThreadPoolExecutor(max_workers=extraction.concurrency) as pool:
            found = [f for page in pool.map(extract_page, pages) for f in page]
        found = _quoted(found, files, detail.sha256)
    except Exception as error:
        failed = run_info(RunStatus.failed, f"{type(error).__name__}: {error}")
        run_id = store.record_fact_extraction(document_id, [], failed)
        raise FactsFailed(document_id, run_id) from error
    run_id = store.record_fact_extraction(document_id, found, run_info())
    rejected = sum(f.rejected is not None for f in found)
    return ExtractedFacts(run_id, len(pages), len(found) - rejected, rejected)


def _headings(sections: list[Section]) -> list[Heading]:
    """The outline as reading-order headings: each section, then its children."""
    found: list[Heading] = []
    for section in sections:
        found.append((section.title, section.level, section.page))
        found += _headings(section.children)
    return found


def _quoted(found: list[FactDraft], files: DocumentFiles, sha256: str) -> list[FactDraft]:
    """Spans boxed by their quote in the PDF's text layer where it is there, so the viewer
    highlights the words the fact is read from, not its whole paragraph (#19 R19)."""
    spans = [f.passage for f in found if isinstance(f.passage, SpanPassage)]
    if not spans:
        return found
    located = iter(files.quote_boxes(sha256, [(s.page, s.quote, s.boxes) for s in spans]))
    quoted = []
    for fact in found:
        if isinstance(fact.passage, SpanPassage) and (boxes := next(located)) is not None:
            fact = replace(fact, passage=replace(fact.passage, boxes=boxes, boxes_from="quote"))
        quoted.append(fact)
    return quoted
