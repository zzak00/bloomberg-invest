"""API contract tests: FastAPI's test client against a real Neo4j and stored PDF."""

import hashlib
import shutil

import pytest
from conftest import FIXTURES, make_run
from fakes import FakeEmbedder
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from starlette.routing import Match

from bloomberg_invest import config
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.domain.chunking import Block, ChunkDraft
from bloomberg_invest.domain.extraction import drafts, page_sources
from bloomberg_invest.domain.model import RunStep
from bloomberg_invest.entrypoints.api.app import create_app
from bloomberg_invest.service_layer.embed import embed_document

PDF = FIXTURES / "filing.pdf"
SHA = hashlib.sha256(PDF.read_bytes()).hexdigest()


@pytest.fixture
def files(tmp_path) -> DocumentFiles:
    files = DocumentFiles(tmp_path)
    files.pdf_path(SHA).parent.mkdir(parents=True)
    shutil.copy(PDF, files.pdf_path(SHA))
    return files


class ContractClient(TestClient):
    """A test client that checks every response against the OpenAPI document the app publishes,
    the same document the frontend's API client is generated from."""

    def get(self, url, *args, **kwargs):
        response = super().get(url, *args, **kwargs)
        if url != "/api/openapi.json":
            self._check(response)
        return response

    def _check(self, response):
        spec = self.app.openapi()
        scope = {"type": "http", "method": "GET", "path": response.request.url.path}
        route = next(r for r in self.app.routes if r.matches(scope)[0] == Match.FULL)
        declared = spec["paths"][route.path]["get"]["responses"]
        status = str(response.status_code)
        assert status in declared, f"{route.path} returned {status}, which the contract omits"
        media = response.headers["content-type"].split(";")[0]
        content = declared[status].get("content", {})
        assert media in content, (
            f"{route.path} {status} returned {media}, contract says {list(content)}"
        )
        if media == "application/json":
            schema = {**content[media]["schema"], "components": spec["components"]}
            Draft202012Validator(schema).validate(response.json())


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def client(store, files, embedder) -> TestClient:
    return ContractClient(create_app(store=store, files=files, embedder=embedder))


@pytest.fixture
def document_id(store, meta, parsed) -> str:
    two_pages = parsed.model_copy(update={"pages": parsed.pages[:2], "sections": []})
    return store.record_parse(meta, two_pages, make_run(), SHA)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_documents_lists_the_filing(client, document_id):
    response = client.get("/api/documents")
    assert response.status_code == 200
    [row] = response.json()
    assert row["id"] == document_id
    assert row["issuer"] == {"isin": "MA0000011488", "name": "Maroc Telecom"}
    assert (row["doc_type"], row["fiscal_year"], row["page_count"]) == ("annual_report", 2025, 2)
    assert row["ingested_at"].startswith("2026-11-03T09:04")


def test_document_detail_has_pages_sections_and_run(client, store, meta, parsed):
    document_id = store.record_parse(meta, parsed, make_run(), SHA)
    body = client.get(f"/api/documents/{document_id}").json()
    assert [p["number"] for p in body["pages"]] == [1, 2, 3]
    assert body["sections"][0]["title"] == "1. RÉSULTATS"
    assert body["sections"][0]["children"][0]["page"] == 2
    assert body["run"]["tool"] == "docling"


def test_unknown_document_is_404(client):
    assert client.get("/api/documents/nope").status_code == 404
    assert client.get("/api/documents/nope/pages/1.png").status_code == 404


def test_a_page_renders_as_png(client, document_id):
    response = client.get(f"/api/documents/{document_id}/pages/2.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_rendered_page_is_cached(client, files, document_id):
    client.get(f"/api/documents/{document_id}/pages/1.png")
    assert files.page_png(SHA, 1).exists()


def test_a_page_outside_the_document_is_404(client, document_id):
    assert client.get(f"/api/documents/{document_id}/pages/3.png").status_code == 404
    assert client.get(f"/api/documents/{document_id}/pages/0.png").status_code == 422


def test_openapi_declares_the_contract(client):
    spec = client.get("/api/openapi.json").json()
    assert set(spec["paths"]) == {
        "/api/health",
        "/api/documents",
        "/api/documents/{document_id}",
        "/api/documents/{document_id}/pages/{number}.png",
        "/api/search",
        "/api/chunks/{chunk_id}",
        "/api/companies/{isin}",
        "/api/companies/{isin}/figures",
        "/api/facts/{fact_id}",
    }
    schemas = spec["components"]["schemas"]
    assert {
        "DocumentSummary",
        "DocumentDetail",
        "Section",
        "Run",
        "PageInfo",
        "Chunk",
        "Company",
        "Figure",
        "Passage",
    } <= set(schemas)


def test_the_app_takes_all_its_dependencies_or_none(files):
    with pytest.raises(TypeError, match="store, files and embedder, or none"):
        create_app(files=files)


def block(text: str, page: int) -> Block:
    return Block(kind="text", text=text, page=page, boxes=((page, 50.0, 100.0, 300.0, 120.0),))


@pytest.fixture
def searchable(store, document, embedder) -> str:
    """Two embedded Chunks: the dividend on p. 2, revenue on p. 3."""
    document_id, ids = document
    texts = [
        (ids["1.1 En dirham"], ("1. RÉSULTATS", "1.1 En dirham"), "Le dividende proposé", 2),
        (ids["1.2 En euro"], ("1. RÉSULTATS", "1.2 En euro"), "Le chiffre d'affaires", 3),
    ]
    drafts = [
        ChunkDraft(
            index=i,
            kind="text",
            section_id=section,
            paragraphs=(block(text, page),),
            text=text,
            token_count=4,
            pages=(page,),
            refers_to=(),
            path=path,
        )
        for i, (section, path, text, page) in enumerate(texts)
    ]
    store.record_chunks(document_id, drafts, make_run().model_copy(update={"step": RunStep.chunk}))
    embed_document(document_id, store, embedder)
    return document_id


def test_search_returns_the_nearest_chunks_with_where_they_are(client, searchable):
    response = client.get("/api/search", params={"q": "dividende proposé"})

    assert response.status_code == 200
    first, second = response.json()
    assert (first["text"], first["kind"]) == ("Le dividende proposé", "text")
    assert first["section_path"] == ["1. RÉSULTATS", "1.1 En dirham"]
    assert first["pages"] == [2]
    assert first["boxes"] == [
        {"page": 2, "left": 50.0, "top": 100.0, "right": 300.0, "bottom": 120.0}
    ]
    assert first["document"]["id"] == searchable
    assert first["document"]["issuer"]["name"] == "Maroc Telecom"
    assert second["text"] == "Le chiffre d'affaires"


def test_search_returns_at_most_the_limit(client, searchable):
    assert len(client.get("/api/search", params={"q": "dividende", "limit": 1}).json()) == 1


@pytest.mark.parametrize(
    "params", [{"q": ""}, {"q": "   "}, {"q": "x", "limit": 0}, {"q": "x", "limit": 51}]
)
def test_a_blank_query_or_a_limit_out_of_range_is_rejected(client, params):
    assert client.get("/api/search", params=params).status_code == 422


def test_search_with_nothing_embedded_returns_nothing(client):
    assert client.get("/api/search", params={"q": "dividende"}).json() == []


def test_a_chunk_opens_by_its_id_for_the_source_viewer(client, searchable):
    [hit] = client.get("/api/search", params={"q": "dividende", "limit": 1}).json()

    response = client.get(f"/api/chunks/{hit['id']}")

    assert response.status_code == 200
    assert response.json() == hit


def test_an_unknown_chunk_is_404(client):
    response = client.get("/api/chunks/nope")
    assert response.status_code == 404
    assert response.json() == {"detail": "Chunk not found"}


@pytest.fixture
def extracted(store, document_id) -> dict[str, str]:
    """Figures extracted from the stored income statement: two that match their cells and one
    that doesn't. Returns the Fact ids by value, and the RejectedFigure's id."""
    label_map = config.label_map()
    sources = page_sources(2, [], store.cells(document_id))
    answer = {
        "figures": [
            {
                "line_item": item,
                "fiscal_year": year,
                "basis_scope": "consolidated",
                "breakdown": "",
                "source_id": source,
                "value_as_written": value,
                "unit_scale": "MAD millions",
            }
            for item, year, source, value in [
                ("revenue", 2025, "t2.0.r1.c2", "36 681"),
                ("revenue", 2024, "t2.0.r1.c1", "36 699"),
                ("net_income", 2025, "t2.0.r2.c2", "7 121"),
            ]
        ]
    }
    run = make_run().model_copy(update={"step": RunStep.extract, "output": None})
    store.record_extraction(document_id, drafts(answer, sources, label_map), label_map, run)
    return {f.value_as_written: f.id for f in store.figures("MA0000011488")}


def test_a_company_lists_its_filings_and_statements(client, document_id):
    company = client.get("/api/companies/MA0000011488").json()
    assert company["issuer"] == {"isin": "MA0000011488", "name": "Maroc Telecom"}
    assert [d["id"] for d in company["documents"]] == [document_id]
    assert [s["key"] for s in company["statements"]] == [
        "income_statement",
        "balance_sheet",
        "cash_flow",
        "per_share",
        "reported",
    ]
    assert company["statements"][0]["line_items"][:2] == ["revenue", "operating_income_ebit"]


def test_an_unknown_company_is_404(client):
    assert client.get("/api/companies/MA0000000000").status_code == 404
    assert client.get("/api/companies/MA0000000000/figures").status_code == 404


def test_a_company_s_figures_are_its_checked_facts_only(client, extracted):
    figures = client.get("/api/companies/MA0000011488/figures").json()
    assert [(f["line_item"], f["fiscal_year"], f["value"]) for f in figures] == [
        ("revenue", 2025, "36681000000"),
        ("revenue", 2024, "36699000000"),
    ]
    revenue = figures[0]
    assert (revenue["line_item_title"], revenue["statement"]) == ("Revenue", "income_statement")
    assert (revenue["period_start"], revenue["period_end"]) == ("2025-01-01", "2025-12-31")
    assert (revenue["basis_scope"], revenue["basis_standard"], revenue["currency"]) == (
        "consolidated",
        "IFRS",
        "MAD",
    )
    assert revenue["passage"] == {
        "kind": "cell",
        "page": 2,
        "boxes": [{"page": 2, "left": 380.0, "top": 140.0, "right": 540.0, "bottom": 156.0}],
        "text": "36 681",
        "quote": None,
    }


def test_a_fact_opens_by_its_id_for_the_source_viewer(client, extracted, document_id):
    fact = client.get(f"/api/facts/{extracted['36 681']}").json()
    assert (fact["value_as_written"], fact["label"]) == ("36 681", "Chiffre d'affaires")
    assert fact["document"]["id"] == document_id


def test_an_unknown_or_rejected_figure_is_404(client, extracted, driver):
    assert client.get("/api/facts/nope").status_code == 404
    records, _, _ = driver.execute_query("MATCH (n:RejectedFigure) RETURN n.id AS id")
    [rejected] = [r["id"] for r in records]
    assert client.get(f"/api/facts/{rejected}").status_code == 404
