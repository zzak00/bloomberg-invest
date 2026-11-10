"""API contract tests: FastAPI's test client against a real Neo4j and stored PDF."""

import hashlib
import shutil

import pytest
from conftest import FIXTURES, INCOME_ANSWER, extract_income, make_run
from fakes import FakeEmbedder
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from starlette.routing import Match

from bloomberg_invest import config
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.domain.chunking import Block, ChunkDraft
from bloomberg_invest.domain.extraction import SourceParagraph
from bloomberg_invest.domain.model import RunStep
from bloomberg_invest.entrypoints.api.app import create_app
from bloomberg_invest.service_layer.checks import Checks
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

    def post(self, url, *args, **kwargs):
        response = super().post(url, *args, **kwargs)
        self._check(response)
        return response

    def _check(self, response):
        spec = self.app.openapi()
        method = response.request.method
        scope = {"type": "http", "method": method, "path": response.request.url.path}
        route = next(r for r in self.app.routes if r.matches(scope)[0] == Match.FULL)
        declared = spec["paths"][route.path][method.lower()]["responses"]
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


def app(store, files, embedder, reviewer: str | None = "Z. Bajjou"):
    checks = Checks(config.kpi_rules(config.label_map()), reviewer)
    return create_app(
        store=store, files=files, embedder=embedder, label_map=config.label_map(), checks=checks
    )


@pytest.fixture
def client(store, files, embedder) -> TestClient:
    return ContractClient(app(store, files, embedder))


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
        "/api/checks",
        "/api/reviews",
        "/api/figures/{figure_id}/candidates",
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
        "FigureDetail",
        "FigureGrid",
        "Passage",
        "Scope",
        "CheckQueue",
        "CheckRow",
        "Review",
        "ReviewRequest",
        "Verdict",
        "CheckStatus",
        "Correction",
        "Candidate",
        "Problem",
    } <= set(schemas)


def test_the_app_takes_all_its_dependencies_or_none(files):
    with pytest.raises(TypeError, match="store, files, embedder, label_map and checks, or none"):
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
    that doesn't. Returns the Fact ids by value."""
    extract_income(store, document_id)
    facts, rejected = store.figures("MA0000011488")
    return {f.value_as_written: f.id for f in [*facts, *rejected]}


def test_a_company_lists_its_filings(client, document_id):
    company = client.get("/api/companies/MA0000011488").json()
    assert company["issuer"] == {"isin": "MA0000011488", "name": "Maroc Telecom"}
    assert [d["id"] for d in company["documents"]] == [document_id]


def test_an_unknown_company_is_404(client):
    assert client.get("/api/companies/MA0000000000").status_code == 404
    assert client.get("/api/companies/MA0000000000/figures").status_code == 404


def test_a_company_s_figures_are_its_checked_facts_only_by_statement_and_year(client, extracted):
    grid = client.get("/api/companies/MA0000011488/figures").json()
    assert grid["count"] == 2
    [consolidated, company_only] = grid["scopes"]
    assert (consolidated["scope"], consolidated["years"]) == ("consolidated", [2025, 2024])
    assert company_only == {"scope": "company-only", "years": [], "statements": []}
    [income] = consolidated["statements"]
    assert (income["key"], income["title"]) == ("income_statement", "Income statement")
    [row] = income["rows"]
    assert (row["title"], row["unit"], row["scale"]) == ("Revenue", "MAD", 1_000_000)
    assert [
        (y["fiscal_year"], [v["shown"]["value"] for v in y["values"]]) for y in row["years"]
    ] == [
        (2025, ["36681000000"]),
        (2024, ["36699000000"]),
    ]
    revenue = row["years"][0]["values"][0]["shown"]
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
    assert revenue["page"] == 2


def test_a_fact_opens_by_its_id_for_the_source_viewer(client, extracted, document_id):
    fact = client.get(f"/api/facts/{extracted['36 681']}").json()
    assert (fact["value_as_written"], fact["label"]) == ("36 681", "Chiffre d'affaires")
    assert fact["line_item_title"] == "Revenue"
    assert fact["document"]["id"] == document_id


def test_an_unknown_figure_or_a_rejected_one_nobody_corrected_is_404(client, extracted):
    assert client.get("/api/facts/nope").status_code == 404
    assert client.get(f"/api/facts/{extracted['7 121']}").status_code == 404


# CHECKS (#23)


def queue(client, **params):
    return client.get("/api/checks", params=params).json()


def rows_of(checks):
    return [row for group in checks["groups"] for row in group["rows"]]


def test_checks_lists_what_feeds_a_kpi_rejected_figures_first(client, extracted, document_id):
    checks = queue(client)
    assert checks["reviewer"] == "Z. Bajjou"
    assert checks["counts"] == {"to_check": 2, "rejected": 1, "done": 0}
    assert checks["companies"] == [{"isin": "MA0000011488", "name": "Maroc Telecom"}]
    [group] = checks["groups"]
    assert group["document"]["id"] == document_id
    assert [
        (r["title"], r["fiscal_year"], r["value_as_written"], r["status"]) for r in group["rows"]
    ] == [
        ("Net income", 2025, "7 121", "rejected"),
        ("Revenue", 2025, "36 681", "to_check"),
        ("Revenue", 2024, "36 699", "to_check"),
    ]
    revenue = group["rows"][1]
    assert (revenue["label"], revenue["basis_scope"], revenue["period_end"]) == (
        "Chiffre d'affaires",
        "consolidated",
        "2025-12-31",
    )
    assert (revenue["value"], revenue["unit_as_written"], revenue["passage"]["text"]) == (
        "36681000000",
        "MAD millions",
        "36 681",
    )
    assert "Revenue growth" in revenue["feeds"]
    misread = group["rows"][0]
    assert (misread["rejected"], misread["value"], misread["passage"]["text"]) == (
        "its value differs from its cell",
        None,
        "7 112",
    )


def review(client, row, verdict="accepted", **fields):
    return client.post(
        "/api/reviews", json={"figure_ids": row["figure_ids"], "verdict": verdict, **fields}
    )


def test_accepting_a_figure_records_who_and_when_and_clears_its_flag(client, extracted):
    revenue = rows_of(queue(client))[1]
    fact = client.get(f"/api/facts/{extracted['36 681']}").json()
    assert (fact["review"], fact["needs_review"]) == (None, True)

    response = review(client, revenue)
    assert response.status_code == 201
    recorded = response.json()
    assert (recorded["verdict"], recorded["reviewer"]) == ("accepted", "Z. Bajjou")

    fact = client.get(f"/api/facts/{extracted['36 681']}").json()
    assert (fact["review"]["id"], fact["review"]["reviewer"], fact["needs_review"]) == (
        recorded["id"],
        "Z. Bajjou",
        False,
    )
    assert fact["review"]["reviewed_at"] == recorded["reviewed_at"]
    checks = queue(client)
    assert checks["counts"] == {"to_check": 1, "rejected": 1, "done": 1}
    # Every status is listed, in the same order: the page filters, and keeps a row just checked
    # where it was.
    assert [(r["value_as_written"], r["status"]) for r in rows_of(checks)] == [
        ("7 121", "rejected"),
        ("36 681", "accepted"),
        ("36 699", "to_check"),
    ]


def test_every_figure_in_the_dossier_carries_its_review_status(client, extracted):
    review(client, rows_of(queue(client))[1])
    grid = client.get("/api/companies/MA0000011488/figures").json()
    [row] = grid["scopes"][0]["statements"][0]["rows"]
    shown = {y["fiscal_year"]: y["values"][0]["shown"] for y in row["years"]}
    assert (shown[2025]["review"]["verdict"], shown[2025]["needs_review"]) == ("accepted", False)
    assert (shown[2024]["review"], shown[2024]["needs_review"]) == (None, True)


def test_a_rejected_figure_is_corrected_from_a_cell_of_its_row(client, extracted):
    misread = rows_of(queue(client))[0]
    choices = client.get(f"/api/figures/{misread['figure_ids'][0]}/candidates").json()
    assert [(c["kind"], c["value_as_written"], c["context"]) for c in choices] == [
        ("cell", "6 968", "31-déc.-24"),
        ("cell", "7 112", "31-déc.-25"),
    ]
    picked = choices[1]
    response = review(client, misread, "corrected", cell_id=picked["cell_id"])
    assert response.status_code == 201
    recorded = response.json()
    fixed = recorded["correction"]
    assert (fixed["value_as_written"], fixed["value"], fixed["unit"]) == (
        "7 112",
        "7112000000",
        "MAD",
    )
    assert (recorded["source"]["kind"], recorded["source"]["text"]) == ("cell", "7 112")
    row = rows_of(queue(client))[0]
    assert (
        row["status"],
        row["value_as_written"],
        row["review"]["correction"]["value_as_written"],
    ) == (
        "corrected",
        "7 121",  # CHECKS shows what was read, and the correction
        "7 112",
    )


def test_a_corrected_rejected_figure_joins_the_dossier_with_the_cell_picked(client, extracted):
    misread = rows_of(queue(client))[0]
    [_, right] = client.get(f"/api/figures/{misread['figure_ids'][0]}/candidates").json()
    review(client, misread, "corrected", cell_id=right["cell_id"])

    grid = client.get("/api/companies/MA0000011488/figures").json()
    assert grid["count"] == 3
    [_, net_income] = grid["scopes"][0]["statements"][0]["rows"]
    assert net_income["title"] == "Net income"
    [year] = net_income["years"]
    shown = year["values"][0]["shown"]
    assert (shown["value_as_written"], shown["value"], shown["review"]["verdict"]) == (
        "7 112",
        "7112000000",
        "corrected",
    )
    assert (shown["passage"]["text"], shown["page"], shown["period_end"]) == (
        "7 112",
        2,
        "2025-12-31",
    )
    fact = client.get(f"/api/facts/{extracted['7 121']}").json()
    assert (fact["value_as_written"], fact["line_item_title"]) == ("7 112", "Net income")


def test_a_typed_correction_is_parsed_in_the_figure_s_unit(client, extracted):
    revenue = rows_of(queue(client))[1]
    response = review(client, revenue, "corrected", value_as_written="36 680")
    assert response.status_code == 201
    recorded = response.json()
    assert (recorded["correction"]["value"], recorded["source"]) == ("36680000000", None)
    # The dossier shows the correction where the figure was read.
    fact = client.get(f"/api/facts/{extracted['36 681']}").json()
    assert (fact["value_as_written"], fact["value"]) == ("36 680", "36680000000")
    assert (fact["passage"]["text"], fact["review"]["verdict"]) == ("36 681", "corrected")


def test_reopening_puts_a_figure_back_to_checks(client, extracted):
    revenue = rows_of(queue(client))[1]
    review(client, revenue)
    assert review(client, revenue, "reopened").json()["verdict"] == "reopened"
    assert queue(client)["counts"] == {"to_check": 2, "rejected": 1, "done": 0}


@pytest.mark.parametrize(
    ("row", "verdict", "fields", "message"),
    [
        (0, "accepted", {}, "A rejected figure can only be corrected"),
        (1, "corrected", {}, "Give the right value one way"),
        (1, "corrected", {"value_as_written": "1", "quote": "1"}, "Give the right value one way"),
        (1, "corrected", {"value_as_written": "36 681 ou 36 699"}, "is not one number"),
        (1, "corrected", {"cell_id": "nope"}, "not in the figure's table row"),
        (1, "corrected", {"quote": "36 681"}, "not in the figure's paragraph"),
    ],
)
def test_a_check_that_does_not_fit_its_figures_is_refused_with_why(
    client, extracted, row, verdict, fields, message
):
    response = review(client, rows_of(queue(client))[row], verdict, **fields)
    assert response.status_code == 409
    assert message in response.json()["detail"]
    assert queue(client)["counts"]["done"] == 0


def test_one_check_covers_one_value(client, store, document_id):
    # The model reads revenue 2025 twice: from its own cell, and from net income's.
    extract_income(store, document_id, [*INCOME_ANSWER, ("revenue", 2025, "t2.0.r2.c2", "7 112")])
    rows = [
        r for r in rows_of(queue(client)) if (r["title"], r["fiscal_year"]) == ("Revenue", 2025)
    ]
    assert [(r["value_as_written"], r["conflict"]) for r in rows] == [
        ("36 681", True),
        ("7 112", True),
    ]
    response = client.post(
        "/api/reviews",
        json={"figure_ids": rows[0]["figure_ids"] + rows[1]["figure_ids"], "verdict": "accepted"},
    )
    assert response.status_code == 409
    assert "different values" in response.json()["detail"]


def test_a_figure_that_feeds_no_kpi_cannot_be_checked(client, store, document_id):
    extract_income(store, document_id, [("share_capital", 2025, "t2.0.r1.c2", "36 681")])
    assert rows_of(queue(client)) == []
    [share_capital], _ = store.figures("MA0000011488")
    response = client.post(
        "/api/reviews", json={"figure_ids": [share_capital.id], "verdict": "accepted"}
    )
    assert response.status_code == 409
    assert "needs no check" in response.json()["detail"]


def test_one_check_covers_one_line_item_and_year(client, extracted):
    revenue, previous = rows_of(queue(client))[1:]
    response = client.post(
        "/api/reviews",
        json={"figure_ids": revenue["figure_ids"] + previous["figure_ids"], "verdict": "accepted"},
    )
    assert response.status_code == 409
    assert "one line item, year, basis and currency" in response.json()["detail"]


def test_checking_an_unknown_figure_is_404(client, extracted):
    response = client.post("/api/reviews", json={"figure_ids": ["nope"], "verdict": "accepted"})
    assert response.status_code == 404
    assert client.get("/api/figures/nope/candidates").status_code == 404


def test_checks_are_refused_until_the_reviewer_is_set(store, files, embedder, extracted):
    client = ContractClient(app(store, files, embedder, reviewer=None))
    assert queue(client)["reviewer"] is None
    response = review(client, rows_of(queue(client))[1])
    assert response.status_code == 503
    assert response.json() == {"detail": "Set REVIEWER in .env to record checks"}


def test_the_queue_filters_by_company(client, extracted):
    assert queue(client, isin="MA0000000000") == {
        "reviewer": "Z. Bajjou",
        "counts": {"to_check": 0, "rejected": 0, "done": 0},
        "companies": [{"isin": "MA0000011488", "name": "Maroc Telecom"}],
        "groups": [],
    }
    assert len(rows_of(queue(client, isin="MA0000011488"))) == 3


# Page 1 of the fixture PDF: one paragraph that writes "31" twice, on one line.
KEY_FIGURES = SourceParagraph(
    page=1,
    text=(
        "Les chiffres clés du Groupe sont présentés ci-dessous en millions de dirhams, selon les "
        "normes IFRS, pour les exercices clos au 31 décembre 2024 et au 31 décembre 2025."
    ),
    boxes=((1, 50.0, 255.0, 545.0, 285.0),),
)


def test_a_quoted_figure_is_corrected_from_the_number_picked_where_it_was_picked(
    client, store, document_id
):
    extract_income(
        store, document_id, [("revenue", 2025, "p1.0", "2025")], page=1, paragraphs=(KEY_FIGURES,)
    )
    [row] = rows_of(queue(client))
    choices = client.get(f"/api/figures/{row['figure_ids'][0]}/candidates").json()
    assert [(c["value_as_written"], c["start"] is not None) for c in choices] == [
        ("31", True),
        ("2024", True),
        ("31", True),
        ("2025", True),
    ]
    first, second = choices[0], choices[2]
    assert first["context"] != second["context"]

    response = review(client, row, "corrected", quote="31", quote_start=second["start"])
    assert response.status_code == 201
    source = response.json()["source"]
    assert (source["kind"], source["quote"], source["page"]) == ("span", "31", 1)
    # Boxed on the second "31" (from x = 335 pt), not the first (from x = 224 pt).
    [box] = source["boxes"]
    assert box["left"] > 300
    fact = client.get(f"/api/facts/{row['figure_ids'][0]}").json()
    assert (fact["value_as_written"], fact["passage"]["quote"]) == ("31", "31")


def test_a_figure_that_feeds_no_kpi_needs_no_review(client, store, document_id):
    extract_income(store, document_id, [("share_capital", 2025, "t2.0.r1.c2", "36 681")])
    [share_capital], _ = store.figures("MA0000011488")
    fact = client.get(f"/api/facts/{share_capital.id}").json()
    assert (fact["review"], fact["needs_review"]) == (None, False)
    grid = client.get("/api/companies/MA0000011488/figures").json()
    [row] = grid["scopes"][0]["statements"][0]["rows"]
    assert row["years"][0]["values"][0]["shown"]["needs_review"] is False


def test_a_checked_value_is_shown_first_in_the_dossier(client, store, document_id):
    # Revenue 2025 read twice: from its own cell, and from net income's.
    extract_income(store, document_id, [*INCOME_ANSWER, ("revenue", 2025, "t2.0.r2.c2", "7 112")])
    rows = [
        r for r in rows_of(queue(client)) if (r["title"], r["fiscal_year"]) == ("Revenue", 2025)
    ]
    second = next(r for r in rows if r["value_as_written"] == "7 112")
    assert review(client, second).status_code == 201

    grid = client.get("/api/companies/MA0000011488/figures").json()
    [revenue] = grid["scopes"][0]["statements"][0]["rows"]
    year = next(y for y in revenue["years"] if y["fiscal_year"] == 2025)
    assert [v["shown"]["value_as_written"] for v in year["values"]] == ["7 112", "36 681"]


def test_a_value_whose_check_carried_over_only_in_part_is_not_checked(client, store, document_id):
    def income(text: str, minute: int):
        paragraph = SourceParagraph(page=2, text=text, boxes=((2, 50.0, 220.0, 545.0, 240.0),))
        answer = [INCOME_ANSWER[0], ("revenue", 2025, "p2.0", "36 681")]
        extract_income(store, document_id, answer, minute=minute, paragraphs=(paragraph,))

    income("Le chiffre d'affaires atteint 36 681 MDH.", minute=10)
    [row] = rows_of(queue(client))
    assert row["sources"] == 2
    assert review(client, row).status_code == 201

    # Re-extracted: the cell reads the same, the paragraph does not, so one check carries over.
    income("Le chiffre d'affaires consolidé atteint 36 681 MDH.", minute=20)
    [row] = rows_of(queue(client))
    assert (row["status"], row["review"]) == ("to_check", None)
    grid = client.get("/api/companies/MA0000011488/figures").json()
    [revenue] = grid["scopes"][0]["statements"][0]["rows"]
    [value] = revenue["years"][0]["values"]
    assert value["shown"]["needs_review"] is True
