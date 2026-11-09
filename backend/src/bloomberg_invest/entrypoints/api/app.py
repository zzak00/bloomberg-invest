"""The HTTP API. Run with `uvicorn bloomberg_invest.entrypoints.api.app:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bloomberg_invest import bootstrap, config
from bloomberg_invest.adapters.embedding import Embedder
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.service_layer.company import company
from bloomberg_invest.service_layer.search import search
from bloomberg_invest.settings import Settings
from bloomberg_invest.views import Chunk, Company, DocumentDetail, DocumentSummary, Figure


class NotFound(BaseModel):
    detail: str


NOT_FOUND = {404: {"model": NotFound, "description": "No such document, or no such page in it"}}
NO_CHUNK = {404: {"model": NotFound, "description": "No such chunk"}}
NO_COMPANY = {404: {"model": NotFound, "description": "No filing from an issuer with this ISIN"}}
NO_FACT = {404: {"model": NotFound, "description": "No such financial figure"}}


def create_app(
    store: GraphStore | None = None,
    files: DocumentFiles | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    """Build the app; without arguments it connects and loads the embedder using the environment."""
    given = [d is not None for d in (store, files, embedder)]
    if any(given) and not all(given):
        raise TypeError("create_app takes store, files and embedder, or none")
    injected = all(given)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if injected:
            yield
            return
        settings = Settings.from_env()
        # Loaded once at startup: queries are embedded with the model the Chunks were.
        app.state.embedder = bootstrap.embedder(settings)
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
        app.state.store, app.state.files, app.state.embedder = store, files, embedder

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

    def get_company(isin: str) -> Company:
        found = company(isin, get_store(), config.label_map())
        if found is None:
            raise HTTPException(404, "Company not found")
        return found

    @app.get("/api/companies/{isin}", responses=NO_COMPANY)
    def company_dossier(isin: str) -> Company:
        """The issuer's filings, and the statements its figures are grouped by."""
        return get_company(isin)

    @app.get("/api/companies/{isin}/figures", responses=NO_COMPANY)
    def company_figures(isin: str) -> list[Figure]:
        """The issuer's current financial figures, each with the Passage it was checked against."""
        get_company(isin)
        return get_store().figures(isin)

    @app.get("/api/facts/{fact_id}", responses=NO_FACT)
    def fact(fact_id: str) -> Figure:
        """One financial figure, current or not, so a link to it keeps working after a re-run."""
        found = get_store().fact(fact_id)
        if found is None:
            raise HTTPException(404, "Fact not found")
        return found

    return app


app = create_app()
