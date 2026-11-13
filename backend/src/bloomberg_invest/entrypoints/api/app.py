"""The HTTP API. Run with `uvicorn bloomberg_invest.entrypoints.api.app:app`."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from bloomberg_invest import bootstrap
from bloomberg_invest.adapters.embedding import Embedder
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.names import NameVerdict, PartyKind
from bloomberg_invest.domain.prices import CASABLANCA
from bloomberg_invest.domain.review import Verdict
from bloomberg_invest.service_layer.checks import (
    Checks,
    NoReviewer,
    ReviewRefused,
    candidates,
    check_queue,
    record_review,
)
from bloomberg_invest.service_layer.company import company, company_figures, figure_detail
from bloomberg_invest.service_layer.company_facts import (
    company_facts,
    fact_detail,
    record_fact_review,
    rejected_facts,
)
from bloomberg_invest.service_layer.kpis import definitions, scorecard
from bloomberg_invest.service_layer.names import name_checks, parties, record_name_review
from bloomberg_invest.service_layer.prices import price_series
from bloomberg_invest.service_layer.search import search
from bloomberg_invest.settings import Settings
from bloomberg_invest.views import (
    Candidate,
    CheckQueue,
    Chunk,
    Company,
    CompanyFacts,
    DocumentDetail,
    DocumentSummary,
    FactDetail,
    FigureDetail,
    FigureGrid,
    KpiDefinitions,
    NameCheck,
    PartyRef,
    PriceSeries,
    RejectedFact,
    Review,
    Scorecard,
)


class Problem(BaseModel):
    """Why a request failed, in words a person can act on."""

    detail: str


class ReviewRequest(BaseModel):
    """A check of one CHECKS row. A correction gives the right value one way: typed, or picked
    from the figure's own source (`GET /api/figures/{id}/candidates`)."""

    figure_ids: list[str] = Field(min_length=1)
    verdict: Verdict
    value_as_written: str | None = None  # typed
    cell_id: str | None = None  # picked from the figure's table row
    quote: str | None = None  # picked from the figure's paragraph
    quote_start: int | None = None  # where the number picked begins in the paragraph


class FactReviewRequest(BaseModel):
    """Keep a value of a Conflict, so the dossier shows it (D5), or undo that."""

    verdict: Literal[Verdict.accepted, Verdict.reopened]


class NameReviewRequest(BaseModel):
    """What a name stands for (CHECKS Names): the same as a known Organisation or Person, a new
    one, or none; or undo the decision before."""

    verdict: NameVerdict
    party_id: str | None = None  # same_as
    name: str | None = None  # new
    kind: PartyKind | None = None  # new


NOT_FOUND = {404: {"model": Problem, "description": "No such document, or no such page in it"}}
NO_CHUNK = {404: {"model": Problem, "description": "No such chunk"}}
NO_COMPANY = {404: {"model": Problem, "description": "No filing from an issuer with this ISIN"}}
NO_COMPANY_OR_YEAR = {
    404: {
        "model": Problem,
        "description": "No filing from an issuer with this ISIN, or no KPI value for the year",
    }
}
NO_LISTING = {404: {"model": Problem, "description": "No listing for a company with this ISIN"}}
NO_FACT = {
    404: {
        "model": Problem,
        "description": "No such fact, or a rejected figure nobody corrected",
    }
}
NO_NAME = {
    404: {"model": Problem, "description": "No such name, or no such organisation or person"},
    409: {"model": Problem, "description": "The decision does not hold together, and why"},
    503: {"model": Problem, "description": "Nobody can check: REVIEWER is not set"},
}
NO_FIGURE = {404: {"model": Problem, "description": "No such current figure"}}
REVIEW_ERRORS = {
    **NO_FIGURE,
    409: {"model": Problem, "description": "The check does not fit these figures, and why"},
    503: {"model": Problem, "description": "Nobody can check: REVIEWER is not set"},
}


@contextmanager
def checking() -> Iterator[None]:
    """A check's failures as the answers its route declares: 503 with no REVIEWER, 404 for what
    is not current, 409 for a check that does not fit, with why."""
    try:
        yield
    except NoReviewer:
        raise HTTPException(503, "Set REVIEWER in .env to record checks") from None
    except LookupError as error:
        raise HTTPException(404, str(error)) from None
    except ReviewRefused as error:
        raise HTTPException(409, str(error)) from None


def create_app(
    store: GraphStore | None = None,
    files: DocumentFiles | None = None,
    embedder: Embedder | None = None,
    label_map: LabelMap | None = None,
    checks: Checks | None = None,
) -> FastAPI:
    """Build the app; without arguments it connects and loads the embedder using the environment."""
    given = [d is not None for d in (store, files, embedder, label_map, checks)]
    if any(given) and not all(given):
        raise TypeError("create_app takes store, files, embedder, label_map and checks, or none")
    injected = all(given)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if injected:
            yield
            return
        settings = Settings.from_env()
        # Loaded once at startup: queries are embedded with the model the Chunks were.
        app.state.embedder = bootstrap.embedder(settings)
        app.state.label_map = bootstrap.label_map()
        app.state.checks = bootstrap.checks(settings)
        with bootstrap.connect(settings) as deps:
            app.state.store, app.state.files = deps.store, deps.files
            yield

    app = FastAPI(
        title="Bloomberg Invest",
        version="0.1.0",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    if injected:
        app.state.store, app.state.files = store, files
        app.state.embedder, app.state.label_map = embedder, label_map
        app.state.checks = checks

    def get_store() -> GraphStore:
        return app.state.store

    def get_files() -> DocumentFiles:
        return app.state.files

    def get_document(document_id: str) -> DocumentDetail:
        document = get_store().get_document(document_id)
        if document is None:
            raise HTTPException(404, "Document not found")
        return document

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/documents")
    def list_documents() -> list[DocumentSummary]:
        return get_store().list_documents()

    @app.get("/api/documents/{document_id}", responses=NOT_FOUND)
    def document_detail(document_id: str) -> DocumentDetail:
        return get_document(document_id)

    @app.get(
        "/api/documents/{document_id}/pages/{number}.png",
        response_class=FileResponse,
        responses={200: {"content": {"image/png": {}}}, **NOT_FOUND},
    )
    def page_image(document_id: str, number: Annotated[int, Path(ge=1)]) -> FileResponse:
        document = get_document(document_id)
        if number > document.page_count:
            raise HTTPException(404, "Page not found")
        png = get_files().render_page(document.sha256, number)
        return FileResponse(
            png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
        )

    @app.get("/api/search")
    def search_chunks(
        q: Annotated[str, Query(min_length=1, max_length=500, pattern=r"\S")],
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> list[Chunk]:
        """The current Chunks nearest the query, best first."""
        return search(q, limit, get_store(), app.state.embedder)

    @app.get("/api/chunks/{chunk_id}", responses=NO_CHUNK)
    def chunk(chunk_id: str) -> Chunk:
        """One Chunk, current or not, so a search result's link keeps working after a re-chunk."""
        found = get_store().chunks([chunk_id])
        if not found:
            raise HTTPException(404, "Chunk not found")
        return found[0]

    @app.get("/api/companies/{isin}", responses=NO_COMPANY)
    def company_dossier(isin: str) -> Company:
        """The issuer's filings."""
        found = company(isin, get_store())
        if found is None:
            raise HTTPException(404, "Company not found")
        return found

    @app.get("/api/companies/{isin}/prices", responses=NO_LISTING)
    def prices(isin: str) -> PriceSeries:
        """The company's daily closes over the last three years, one per session, oldest
        first: the exchange's close over one typed in by hand (#26)."""
        found = price_series(get_store(), isin, datetime.now(CASABLANCA).date())
        if found is None:
            raise HTTPException(404, "No listing for this company")
        return found

    @app.get("/api/companies/{isin}/figures", responses=NO_COMPANY)
    def figures(isin: str) -> FigureGrid:
        """The issuer's current financial figures on each basis, by statement, line item and
        year, each value with the figures stating it and the Passage each was checked against."""
        found = company_figures(isin, get_store(), app.state.label_map, app.state.checks.rules)
        if found is None:
            raise HTTPException(404, "Company not found")
        return found

    @app.get("/api/companies/{isin}/kpis", responses=NO_COMPANY_OR_YEAR)
    def kpis(isin: str, fiscal_year: int | None = None) -> Scorecard:
        """The issuer's scorecard (#27): its quality KPIs and F-score for the fiscal year, by
        default its last with a computed value, each computed from checked figures or "-" with
        why, with its inputs and their sources."""
        try:
            found = scorecard(
                isin, get_store(), app.state.label_map, app.state.checks.rules, fiscal_year
            )
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        if found is None:
            raise HTTPException(404, "Company not found")
        return found

    @app.get("/api/kpis")
    def kpi_definitions() -> KpiDefinitions:
        """The KPIs page (#27 AC4): every computed KPI, generated from the rules that compute
        it."""
        return definitions(app.state.checks.rules)

    @app.get("/api/companies/{isin}/facts", responses=NO_COMPANY)
    def facts(isin: str) -> CompanyFacts:
        """The issuer's facts of the eight other kinds (#24), by section: one row per kind,
        parties and details, showing the value in force, with any Conflict's other values."""
        found = company_facts(isin, get_store())
        if found is None:
            raise HTTPException(404, "Company not found")
        return found

    @app.get("/api/rejected-facts")
    def refused_facts(isin: str | None = None) -> list[RejectedFact]:
        """The facts of the eight other kinds the check refused, with why (D2), of one company's
        filings or all: for CHECKS, never for the dossier."""
        return rejected_facts(get_store(), isin)

    @app.get("/api/facts/{fact_id}", responses=NO_FACT)
    def fact(fact_id: str) -> FigureDetail | FactDetail:
        """One fact as the dossier shows it, current or not, so a link to it keeps working after
        a re-run: a corrected figure with its correction; a fact of another kind in one sentence,
        with both sides of a Conflict."""
        found = figure_detail(fact_id, get_store(), app.state.label_map, app.state.checks.rules)
        if found is None:
            found = fact_detail(fact_id, get_store(), app.state.checks.rules)
        if found is None:
            raise HTTPException(404, "Fact not found")
        return found

    @app.post(
        "/api/facts/{fact_id}/reviews",
        status_code=status.HTTP_201_CREATED,
        responses=REVIEW_ERRORS,
    )
    def fact_review(fact_id: str, request: FactReviewRequest) -> Review:
        """Keep a value of a Conflict (D5): the dossier shows it. A reopening undoes that."""
        with checking():
            return record_fact_review(fact_id, request.verdict, get_store(), app.state.checks)

    @app.get("/api/names")
    def names() -> list[NameCheck]:
        """CHECKS Names (S7b): each name no rule linked to exactly one Organisation or Person,
        to check first, then those a person resolved."""
        return name_checks(get_store())

    @app.get("/api/parties")
    def known_parties() -> list[PartyRef]:
        """Every Organisation and Person a name can be the same as, by name."""
        return parties(get_store())

    @app.post(
        "/api/names/{key}/reviews",
        status_code=status.HTTP_201_CREATED,
        responses=NO_NAME,
    )
    def name_review(key: str, request: NameReviewRequest) -> list[NameCheck]:
        """Decide what a name stands for, for every filing writing it; returns CHECKS Names as
        it now stands."""
        with checking():
            record_name_review(
                key,
                request.verdict,
                get_store(),
                app.state.checks,
                party_id=request.party_id,
                name=request.name,
                kind=request.kind,
            )
        return name_checks(get_store())

    @app.get("/api/checks")
    def checks_queue(isin: str | None = None) -> CheckQueue:
        """CHECKS: the figures that feed a KPI or screen, checked or not, by filing, problems
        first; of one company or all."""
        return check_queue(get_store(), app.state.label_map, app.state.checks, isin)

    @app.post(
        "/api/reviews",
        status_code=status.HTTP_201_CREATED,
        responses=REVIEW_ERRORS,
    )
    def review(request: ReviewRequest) -> Review:
        """Accept, correct or reopen the figures of one CHECKS row. Checks are never deleted: a
        reopening is a check that undoes the one before."""
        with checking():
            return record_review(
                request.figure_ids,
                request.verdict,
                get_store(),
                get_files(),
                app.state.checks,
                value_as_written=request.value_as_written,
                cell_id=request.cell_id,
                quote=request.quote,
                quote_start=request.quote_start,
            )

    @app.get("/api/figures/{figure_id}/candidates", responses=NO_FIGURE)
    def figure_candidates(figure_id: str) -> list[Candidate]:
        """What a correction can pick from the figure's own source: the numbers of its table
        row, or of its paragraph."""
        found = candidates(figure_id, get_store())
        if found is None:
            raise HTTPException(404, "Figure not found")
        return found

    return app


app = create_app()
