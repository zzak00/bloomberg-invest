"""The HTTP API. Run with `uvicorn bloomberg_invest.api.app:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bloomberg_invest.domain import DocumentDetail, DocumentSummary
from bloomberg_invest.files import DocumentFiles
from bloomberg_invest.settings import Settings
from bloomberg_invest.store import GraphStore
from bloomberg_invest.store.neo4j_store import Neo4jStore


class NotFound(BaseModel):
    detail: str


NOT_FOUND = {404: {"model": NotFound, "description": "No such document, or no such page in it"}}


def create_app(store: GraphStore | None = None, files: DocumentFiles | None = None) -> FastAPI:
    """Build the app; without arguments it connects using the environment."""
    if (store is None) != (files is None):
        raise TypeError("create_app takes both store and files, or neither")
    injected = store is not None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if injected:
            yield
            return
        settings = Settings.from_env()
        with settings.driver() as driver:
            app.state.store = Neo4jStore(driver)
            app.state.store.ensure_schema()
            app.state.files = DocumentFiles(settings.data_dir)
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

    return app


app = create_app()
