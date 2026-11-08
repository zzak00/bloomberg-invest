"""The HTTP API. Run with `uvicorn bloomberg_invest.entrypoints.api.app:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bloomberg_invest import bootstrap
from bloomberg_invest.adapters.embedding import Embedder
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.service_layer.search import search
from bloomberg_invest.settings import Settings
from bloomberg_invest.views import DocumentDetail, DocumentSummary, SearchHit


class NotFound(BaseModel):
    detail: str


NOT_FOUND = {404: {"model": NotFound, "description": "No such document, or no such page in it"}}


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
    ) -> list[SearchHit]:
        """The current Chunks nearest the query, best first."""
        return search(q, limit, get_store(), app.state.embedder)

    return app


app = create_app()
