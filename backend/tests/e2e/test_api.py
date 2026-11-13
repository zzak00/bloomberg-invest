"""API contract tests: FastAPI's test client against a real Neo4j and stored PDF."""

import hashlib
import os
import shutil
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import FIXTURES, INCOME_ANSWER, extract_income, make_run
from fakes import BOURSE_FIXTURES, FakeEmbedder, bourse_server
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from starlette.routing import Match

from bloomberg_invest import bootstrap, config
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.prices.bourse_casablanca import BourseCasablanca
from bloomberg_invest.domain.chunking import Block, ChunkDraft
from bloomberg_invest.domain.extraction import SourceParagraph, page_sources
from bloomberg_invest.domain.facts import FactKind
from bloomberg_invest.domain.facts import drafts as fact_drafts
from bloomberg_invest.domain.kpis import KpiChange, KpiResult, KpiStatus
from bloomberg_invest.domain.model import DocType, RunStep
from bloomberg_invest.domain.prices import CASABLANCA, XCAS, Close, ListedShare
from bloomberg_invest.entrypoints import cli
from bloomberg_invest.entrypoints import prices as prices_entrypoint
from bloomberg_invest.entrypoints.api.app import create_app
from bloomberg_invest.service_layer.checks import Checks
from bloomberg_invest.service_layer.embed import embed_document
from bloomberg_invest.service_layer.facts import ExtractedFacts
from bloomberg_invest.service_layer.kpis import Computed, compute_kpis
from bloomberg_invest.service_layer.names import Linked, link_names

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
    checks = Checks(config.kpi_rules(config.label_map()), reviewer, config.label_map())
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
        "/api/companies/{isin}/prices",
        "/api/facts/{fact_id}",
        "/api/checks",
        "/api/reviews",
        "/api/figures/{figure_id}/candidates",
        "/api/companies/{isin}/facts",
        "/api/facts/{fact_id}/reviews",
        "/api/names",
        "/api/names/{key}/reviews",
        "/api/parties",
        "/api/rejected-facts",
        "/api/companies/{isin}/kpis",
        "/api/kpis",
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
        "CompanyFacts",
        "FactDetail",
        "NameCheck",
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


def test_a_company_with_no_listing_shows_no_close(client, document_id):
    company = client.get("/api/companies/MA0000011488").json()
    assert (company["listing"], company["last_close"]) == (None, None)
    response = client.get("/api/companies/MA0000011488/prices")
    assert response.status_code == 404
    assert response.json()["detail"] == "No listing for this company"


def listed(store, *closes: tuple[int, str], source: str = "bourse-casablanca") -> date:
    """IAM listed and linked to Maroc Telecom, with closes `days` ago; returns today."""
    today = datetime.now(CASABLANCA).date()
    share = ListedShare("IAM", "ITISSALAT AL-MAGHRIB", "Télécommunications", "Principal A")
    store.upsert_listings(XCAS, [share], {"IAM": "MA0000011488"}, datetime.now(UTC))
    rows = [Close(today - timedelta(days=d), Decimal(v)) for d, v in closes]
    store.add_prices("XCAS:IAM", rows, source, "MAD", datetime.now(UTC))
    return today


def test_a_listed_company_shows_its_last_close_and_change(client, store, document_id):
    today = listed(store, (1200, "80"), (2, "89.80"), (1, "91.70"))
    company = client.get("/api/companies/MA0000011488").json()
    assert company["listing"] == {
        "ticker": "IAM",
        "mic": "XCAS",
        "name": "ITISSALAT AL-MAGHRIB",
        "sector": "Télécommunications",
        "compartment": "Principal A",
    }
    assert company["last_close"] == {
        "session": str(today - timedelta(days=1)),
        "close": "91.7",
        "currency": "MAD",
        "change": "0.0212",
        "source": "bourse-casablanca",
        "history_start": str(today - timedelta(days=1200)),
    }
    series = client.get("/api/companies/MA0000011488/prices").json()
    # Three years back: the close of 1,200 days ago is history, not in the line.
    # Closes are written without trailing zeros, so one close is written one way.
    assert [p["close"] for p in series["closes"]] == ["89.8", "91.7"]


def test_a_listing_with_no_closes_yet_has_no_last_close(client, store, document_id):
    listed(store)
    company = client.get("/api/companies/MA0000011488").json()
    assert (company["listing"]["ticker"], company["last_close"]) == ("IAM", None)
    assert client.get("/api/companies/MA0000011488/prices").json()["closes"] == []


@pytest.fixture
def prices_cli(monkeypatch, tmp_path, driver):
    """`bloomberg prices ...` on the test Neo4j, the Bourse adapter reading the recorded
    fixtures (#26 AC5) on 11/11/2026, and the made-up share ABC linked to Maroc Telecom."""
    monkeypatch.setenv("NEO4J_URI", os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7688"))
    monkeypatch.setenv("NEO4J_PASSWORD", os.environ.get("NEO4J_TEST_PASSWORD", "test-password"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    server = {"fetch": bourse_server}
    monkeypatch.setitem(
        bootstrap.PRICE_SOURCES,
        XCAS,
        lambda settings: BourseCasablanca(fetch=lambda url: server["fetch"](url), pause=0),
    )
    monkeypatch.setattr(bootstrap.config, "listing_isins", lambda mic: {"ABC": "MA0000011488"})
    monkeypatch.setattr(prices_entrypoint, "_today", lambda: date(2026, 11, 11))

    def run(*argv: str) -> int:
        return cli.main(["prices", *argv])

    run.server = server
    return run


def test_a_backfill_through_the_cli_shows_in_the_api_and_a_rerun_changes_nothing(
    client, document_id, prices_cli, capsys
):
    assert prices_cli("backfill", "--ticker", "ABC") == 0
    first = client.get("/api/companies/MA0000011488/prices").json()
    assert [(p["session"], p["close"]) for p in first["closes"]] == [
        ("2026-11-03", "50"),
        ("2026-11-05", "51.95"),
        ("2026-11-09", "52.4"),
    ]
    capsys.readouterr()
    assert prices_cli("backfill", "--ticker", "ABC") == 0
    assert "0 new closes, 0 drifted, 0 errors" in capsys.readouterr().out
    assert client.get("/api/companies/MA0000011488/prices").json() == first


def test_an_empty_answer_through_the_cli_fails_the_run(client, document_id, prices_cli, capsys):
    assert prices_cli("backfill", "--ticker", "ABC") == 0
    prices_cli.server["fetch"] = lambda url: (
        (BOURSE_FIXTURES / "empty.json").read_bytes()
        if "stock-historical" in url
        else bourse_server(url)
    )
    capsys.readouterr()
    assert prices_cli("daily") == 1
    assert "error: ABC: empty answer from 2026-10-12 to 2026-11-11" in capsys.readouterr().err


def test_a_csv_through_the_cli_fills_a_gap_the_api_then_shows(
    client, document_id, prices_cli, tmp_path, capsys
):
    assert prices_cli("backfill", "--ticker", "ABC") == 0
    csv = tmp_path / "closes.csv"
    csv.write_text("ticker,date,close\nABC,2026-11-02,49.5\nABC,2026-11-03,1\n")
    capsys.readouterr()
    assert prices_cli("import", str(csv)) == 0
    assert "ABC: 1 added, 1 skipped: already closed" in capsys.readouterr().out
    series = client.get("/api/companies/MA0000011488/prices").json()
    assert [(p["session"], p["close"]) for p in series["closes"]][:2] == [
        ("2026-11-02", "49.5"),
        ("2026-11-03", "50"),
    ]


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


def test_checks_lists_no_figure_in_another_currency_than_the_filing_s(client, store, document_id):
    """#56: a translation of the statements into euros is kept, but never needs a check."""
    extract_income(store, document_id, unit="EUR millions")
    facts, _ = store.figures("MA0000011488")
    assert facts and {f.currency for f in facts} == {"EUR"}
    assert {f.document.currency for f in facts} == {"MAD"}
    checks = queue(client)
    assert rows_of(checks) == []
    assert checks["counts"] == {"to_check": 0, "rejected": 0, "done": 0}


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
        (1, "corrected", {"value_as_written": "18 70 2"}, "is not one number"),
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
        "dividends": [],
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
    # The viewer describes the figure it opens: the one whose check carried over.
    fact = client.get(f"/api/facts/{value['shown']['id']}").json()
    assert (fact["review"]["verdict"], fact["needs_review"]) == ("accepted", False)


# Facts of the eight other kinds (#24): the dossier's sections, the inspector, a Conflict kept,
# and CHECKS Names.

OWNERS = SourceParagraph(
    2,
    "Au 31 décembre 2025, le capital est réparti comme suit : - Société Alpha : 53% ; "
    "- Itissalat Al-Maghrib : 2% ; - Autres : 45%. Selon la page émetteur : Société Alpha : 54%.",
    ((2, 50.0, 300.0, 540.0, 330.0),),
)


def holding(holder: str, percent: str, quote: str, kind: str = "company", name=None) -> dict:
    return {
        "holder": {"written": holder, "name": name or holder, "kind": kind},
        "held": {"written": "Maroc Telecom", "name": "Maroc Telecom", "kind": "company"},
        "percent": percent,
        "shares": None,
        "rights": "capital",
        "as_of": "2025-12-31",
        "source_id": "p2.0",
        "quote": quote,
    }


def record_facts(store, document_id, answer, minute=20):
    sources = page_sources(2, [OWNERS], [])
    response = {k.value: answer if k == FactKind.shareholding else [] for k in FactKind}
    run = make_run(minute).model_copy(update={"step": RunStep.extract_facts, "output": None})
    return store.record_fact_extraction(document_id, fact_drafts(response, sources), run)


@pytest.fixture
def with_facts(store, document_id):
    record_facts(
        store,
        document_id,
        [
            holding("Société Alpha", "53", "Société Alpha : 53%"),
            holding("Itissalat Al-Maghrib", "2", "Itissalat Al-Maghrib : 2%"),
            holding("Autres", "45", "Autres : 45%", "free_float", "Free float"),
        ],
    )
    link_names(document_id, store)
    return document_id


def test_a_company_s_facts_are_listed_by_section_whether_their_names_are_known_or_not(
    client, with_facts
):
    facts = client.get("/api/companies/MA0000011488/facts").json()
    [ownership] = facts["sections"]
    assert (ownership["key"], ownership["title"]) == ("ownership", "Ownership")
    rows = {r["shown"]["values"]["percent"]: r for r in ownership["rows"]}
    assert rows["45"]["sentence"] == {
        "before": "Free float holds ",
        "value": "45 %",
        "after": " of Maroc Telecom",
    }
    assert (rows["45"]["why"], rows["45"]["conflict"]) == ("latest", False)
    # A holder no rule linked is shown as the filing names it, and waits in CHECKS Names.
    [holder, _] = rows["53"]["shown"]["parties"]
    assert (holder["name"], holder["resolved"]) == ("Société Alpha", None)
    assert facts["unlinked"] == 0
    names = client.get("/api/names").json()
    assert [(n["alias"], n["status"]) for n in names] == [
        ("itissalat al maghrib", "to_check"),
        ("societe alpha", "to_check"),
    ]
    # No known name shares a word with it: the person picks among every Organisation and Person.
    assert names[0]["candidates"] == []
    assert [e["name"] for e in client.get("/api/parties").json()] == ["Maroc Telecom"]


def test_resolving_a_name_puts_its_facts_in_the_dossier(client, with_facts):
    [issuer] = [e["id"] for e in client.get("/api/parties").json()]
    answer = client.post(
        "/api/names/itissalat al maghrib/reviews", json={"verdict": "same_as", "party_id": issuer}
    )
    assert answer.status_code == 201
    assert [n["status"] for n in answer.json()] == ["to_check", "resolved"]
    created = client.post(
        "/api/names/societe alpha/reviews",
        json={"verdict": "new", "name": "Société Alpha", "kind": "holding"},
    )
    assert created.status_code == 201
    facts = client.get("/api/companies/MA0000011488/facts").json()
    assert sorted(r["sentence"]["before"] for r in facts["sections"][0]["rows"]) == [
        "Free float holds ",
        "Maroc Telecom holds ",
        "Société Alpha holds ",
    ]
    [holder, _] = next(
        r for r in facts["sections"][0]["rows"] if r["shown"]["values"]["percent"] == "53"
    )["shown"]["parties"]
    assert (holder["resolved"]["name"], holder["resolved"]["kind"]) == ("Société Alpha", "holding")


def test_a_name_decision_that_does_not_hold_together_is_refused(client, with_facts):
    assert (
        client.post("/api/names/societe alpha/reviews", json={"verdict": "new"}).status_code == 409
    )
    missing = client.post(
        "/api/names/societe alpha/reviews", json={"verdict": "same_as", "party_id": "nobody"}
    )
    assert missing.status_code == 404
    assert (
        client.post("/api/names/nobody/reviews", json={"verdict": "not_a_party"}).status_code == 404
    )


def test_a_conflict_shows_both_values_and_the_one_kept(client, store, with_facts):
    record_facts(
        store,
        with_facts,
        [
            holding("Société Alpha", "53", "Société Alpha : 53%"),
            holding("Société Alpha", "54", "Société Alpha : 54%"),
        ],
        minute=40,
    )
    client.post(
        "/api/names/societe alpha/reviews",
        json={"verdict": "new", "name": "Société Alpha", "kind": "holding"},
    )
    [row] = client.get("/api/companies/MA0000011488/facts").json()["sections"][0]["rows"]
    assert (row["conflict"], row["why"], row["shown"]["values"]["percent"]) == (
        True,
        "earliest",
        "53",
    )
    [[other]] = row["others"]
    detail = client.get(f"/api/facts/{other['id']}").json()
    assert detail["kind"] == "shareholding"
    assert [(s["sentence"]["value"], s["in_use"], s["why"]) for s in detail["sides"]] == [
        ("53 %", True, "earliest"),
        ("54 %", False, None),
    ]
    kept = client.post(f"/api/facts/{other['id']}/reviews", json={"verdict": "accepted"})
    assert kept.status_code == 201
    [row] = client.get("/api/companies/MA0000011488/facts").json()["sections"][0]["rows"]
    assert (row["why"], row["shown"]["values"]["percent"], row["conflict"]) == ("kept", "54", True)
    undone = client.post(f"/api/facts/{other['id']}/reviews", json={"verdict": "reopened"})
    assert undone.status_code == 201
    [row] = client.get("/api/companies/MA0000011488/facts").json()["sections"][0]["rows"]
    assert row["shown"]["values"]["percent"] == "53"


def test_a_fact_opens_in_the_inspector_with_its_passage(client, with_facts):
    rows = client.get("/api/companies/MA0000011488/facts").json()["sections"][0]["rows"]
    row = next(r for r in rows if r["shown"]["values"]["percent"] == "45")
    detail = client.get(f"/api/facts/{row['shown']['id']}").json()
    assert (detail["passage"]["kind"], detail["passage"]["quote"], detail["page"]) == (
        "span",
        "Autres : 45%",
        2,
    )
    assert detail["why"] == "latest"
    assert [s["in_use"] for s in detail["sides"]] == [True]


def test_undoing_a_value_nobody_kept_is_refused(client, with_facts):
    row = client.get("/api/companies/MA0000011488/facts").json()["sections"][0]["rows"][0]
    answer = client.post(f"/api/facts/{row['shown']['id']}/reviews", json={"verdict": "reopened"})
    assert answer.status_code == 409
    assert client.post("/api/facts/nope/reviews", json={"verdict": "accepted"}).status_code == 404


def issuer_page(store, meta, parsed) -> str:
    """The issuer's page on the exchange's site: a second filing of the same company."""
    page_meta = meta.model_copy(update={"doc_type": DocType.issuer_page})
    two_pages = parsed.model_copy(update={"pages": parsed.pages[:2], "sections": []})
    return store.record_parse(page_meta, two_pages, make_run(2), "e" * 64)


def test_two_filings_disagreeing_show_the_annual_report_s_value_and_both(
    client, store, meta, parsed, with_facts
):
    """#19 R8: at one date, an annual report's value over an issuer page's; both stay visible."""
    other = issuer_page(store, meta, parsed)
    record_facts(store, other, [holding("Société Alpha", "54", "Société Alpha : 54%")], minute=5)
    link_names(other, store)
    rows = client.get("/api/companies/MA0000011488/facts").json()["sections"][0]["rows"]
    alpha = [r for r in rows if r["shown"]["parties"][0]["name"] == "Société Alpha"]
    [row] = alpha
    assert (row["shown"]["values"]["percent"], row["why"], row["conflict"]) == (
        "53",
        "annual_report",
        True,
    )
    [[page_value]] = row["others"]
    assert (page_value["values"]["percent"], page_value["document"]["doc_type"]) == (
        "54",
        "issuer_page",
    )


def test_two_filings_agreeing_are_one_value_stated_twice(client, store, meta, parsed, with_facts):
    other = issuer_page(store, meta, parsed)
    record_facts(store, other, [holding("Société Alpha", "53,0", "Société Alpha : 53%")], minute=5)
    rows = client.get("/api/companies/MA0000011488/facts").json()["sections"][0]["rows"]
    [row] = [r for r in rows if r["shown"]["parties"][0]["name"] == "Société Alpha"]
    assert (row["conflict"], len(row["sources"])) == (False, 2)


def test_rejected_facts_are_listed_with_why(client, store, document_id):
    record_facts(store, document_id, [holding("Société Alpha", "55", "Société Alpha : 53%")])
    [rejected] = client.get("/api/rejected-facts?isin=MA0000011488").json()
    assert (rejected["reason"], rejected["values"]["percent"], rejected["page"]) == (
        "a number it states is not in its quote",
        "55",
        2,
    )
    assert client.get("/api/companies/MA0000011488/facts").json()["sections"] == []


def scorecard(client) -> dict:
    return client.get("/api/companies/MA0000011488/kpis").json()


def kpi(card: dict, name: str) -> dict:
    return next(k for k in card["kpis"] if k["name"] == name)


def kpi_values(driver, name: str) -> list[tuple[str | None, bool]]:
    """Every KpiValue the graph keeps for a KPI and FY2025, current or not, oldest first."""
    records, _, _ = driver.execute_query(
        "MATCH (k:KpiValue {kpi: $kpi, fiscal_year: 2025}) "
        "RETURN k.value AS value, coalesce(k.superseded, false) AS superseded "
        "ORDER BY k.computed_at",
        kpi=name,
    )
    return [(r["value"], r["superseded"]) for r in records]


def test_a_kpi_with_an_input_waiting_for_check_reads_a_dash_and_why(client, extracted):
    """#27 AC2: nothing is computed from an unchecked input."""
    assert scorecard(client) == {
        "fiscal_year": None,
        "years": [],
        "window": 3,
        "basis": "Consolidated · IFRS",
        "rule_version": "v1",
        "since": "2026-10-29",
        "financial": False,
        "sector": None,
        "kpis": [],
    }
    review(client, rows_of(queue(client))[1])  # revenue FY2025
    card = scorecard(client)
    assert card["fiscal_year"] == 2025
    growth = kpi(card, "revenue_growth")
    assert (growth["status"], growth["value"], growth["reason"]) == (
        "unchecked",
        None,
        "Waiting for check: Revenue FY2024",
    )
    assert [(i["title"], i["fiscal_year"], i["status"]) for i in growth["inputs"]] == [
        ("Revenue", 2025, "checked"),
        ("Revenue", 2024, "unchecked"),
    ]
    assert growth["inputs"][0]["checked_by"] == "Z. Bajjou"
    assert growth["inputs"][0]["value_as_written"] == "36 681"
    assert growth["formula"] == "revenue / revenue FY-1 - 1"
    margin = kpi(card, "net_margin")
    # The misread net income is rejected: it does not count until corrected.
    assert (margin["status"], margin["reason"]) == ("missing", "Missing: Net income FY2025")


def test_a_checked_input_computes_the_kpi_from_the_facts_it_names(client, extracted, driver):
    """#27 AC1: a KPI value links to the Facts it used and the rule version."""
    review(client, rows_of(queue(client))[1])  # revenue FY2025
    review(client, rows_of(queue(client))[2])  # revenue FY2024
    growth = kpi(scorecard(client), "revenue_growth")
    assert (growth["status"], growth["value"], growth["reason"]) == (
        "computed",
        "-0.000490477",  # 36 681 / 36 699 - 1
        "",
    )
    assert [p["fiscal_year"] for p in growth["history"]] == [2024, 2025]
    assert growth["applies"] == "non_financial"
    records, _, _ = driver.execute_query(
        "MATCH (k:KpiValue {kpi: 'revenue_growth', fiscal_year: 2025})-[:COMPUTED_FROM]->(f) "
        "WHERE k.superseded IS NULL "
        "MATCH (k)-[:PRODUCED_BY]->(r:Run {step: 'compute'}) "
        "RETURN k.rule_version AS version, collect(f.id) AS facts, r.config AS config"
    )
    [record] = records
    assert record["version"] == "v1"
    assert sorted(record["facts"]) == sorted([extracted["36 681"], extracted["36 699"]])
    assert '"kpi_rules": "v1"' in record["config"]


def test_a_correction_supersedes_only_the_kpi_values_that_read_the_figure(
    client, store, extracted, driver
):
    """#27 AC3: a corrected figure recomputes only the affected KPI values; the old ones are
    kept, superseded."""
    review(client, rows_of(queue(client))[1])  # revenue FY2025
    review(client, rows_of(queue(client))[2])  # revenue FY2024
    misread = rows_of(queue(client))[0]  # net income FY2025, 7 121 for 7 112
    [_, right] = client.get(f"/api/figures/{misread['figure_ids'][0]}/candidates").json()
    review(client, misread, "corrected", cell_id=right["cell_id"])

    margin = kpi(scorecard(client), "net_margin")
    assert (margin["status"], margin["value"]) == ("computed", "0.193887844")  # 7 112 / 36 681
    assert kpi_values(driver, "net_margin") == [(None, True), ("0.193887844", False)]
    # Revenue growth reads no net income: its value is the one computed before.
    assert kpi_values(driver, "revenue_growth") == [(None, True), ("-0.000490477", False)]

    review(client, rows_of(queue(client))[1], "corrected", value_as_written="36 680")
    assert kpi(scorecard(client), "net_margin")["value"] == "0.193893130"  # 7 112 / 36 680
    assert kpi_values(driver, "net_margin")[-2:] == [
        ("0.193887844", True),
        ("0.193893130", False),
    ]
    assert kpi_values(driver, "revenue_growth")[-1] == ("-0.000517725", False)
    # Each check wrote the values computed with it applied: a recompute finds nothing to change.
    label_map = config.label_map()
    unchanged = compute_kpis("MA0000011488", store, label_map, config.kpi_rules(label_map))
    assert unchanged == Computed(None, 0, 0)


def test_a_failed_kpi_recompute_after_an_extract_says_the_extract_is_kept(
    client, document_id, monkeypatch, capsys
):
    """The recompute ending `bloomberg facts` fails on its own line: what was extracted stays."""
    monkeypatch.setenv("NEO4J_URI", os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7688"))
    monkeypatch.setenv("NEO4J_PASSWORD", os.environ.get("NEO4J_TEST_PASSWORD", "test-password"))
    monkeypatch.setattr(bootstrap, "fact_extraction", lambda settings: None)
    monkeypatch.setattr(bootstrap, "parser", lambda settings: None)
    monkeypatch.setattr(cli, "extract_facts", lambda *args: ExtractedFacts("run-1", 3, 4, 0))
    monkeypatch.setattr(cli, "link_names", lambda *args: Linked("run-2", 2, 0))

    def fail(isin, *args):
        raise LookupError(f"no issuer {isin}")

    monkeypatch.setattr(cli, "compute_kpis", fail)
    assert cli.main(["facts", document_id]) == 1
    out = capsys.readouterr()
    assert "extracted 4 other facts from 3 pages" in out.out
    assert "; KPI values not recomputed; " in out.out
    assert out.err.strip() == (
        "KPI values not recomputed: no issuer MA0000011488; "
        "run `bloomberg kpis --isin MA0000011488`"
    )


def test_bloomberg_kpis_carries_on_past_an_issuer_that_fails(
    client, store, meta, parsed, extracted, monkeypatch, capsys
):
    monkeypatch.setenv("NEO4J_URI", os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7688"))
    monkeypatch.setenv("NEO4J_PASSWORD", os.environ.get("NEO4J_TEST_PASSWORD", "test-password"))
    other = meta.issuer.model_copy(update={"isin": "MA0000000001", "name": "Other"})
    store.record_parse(meta.model_copy(update={"issuer": other}), parsed, make_run(), "1" * 64)

    def compute(isin, *args):
        if isin == "MA0000000001":
            raise LookupError("no issuer MA0000000001")
        return compute_kpis(isin, *args)

    monkeypatch.setattr(cli, "compute_kpis", compute)
    assert cli.main(["kpis"]) == 1
    out = capsys.readouterr()
    assert "MA0000000001: no issuer MA0000000001" in out.err
    assert "MA0000011488: " in out.out
    assert store.kpi_values("MA0000011488") != []


def test_reopening_a_check_takes_the_kpi_value_back_to_a_dash(client, extracted, driver):
    revenue = rows_of(queue(client))[1]
    review(client, revenue)
    review(client, rows_of(queue(client))[2])
    kept = kpi_values(driver, "roe")
    review(client, revenue, "reopened")
    growth = kpi(scorecard(client), "revenue_growth")
    assert (growth["status"], growth["reason"]) == (
        "unchecked",
        "Waiting for check: Revenue FY2025",
    )
    assert kpi_values(driver, "revenue_growth")[-2:] == [
        ("-0.000490477", True),
        (None, False),
    ]
    # ROE reads no revenue: it is not written again.
    assert kpi_values(driver, "roe") == kept


def test_the_scorecard_shows_the_fiscal_year_selected(client, extracted):
    """#7: the value for the selected year, each year with values selectable."""
    review(client, rows_of(queue(client))[1])  # revenue FY2025
    review(client, rows_of(queue(client))[2])  # revenue FY2024
    card = scorecard(client)
    assert (card["fiscal_year"], card["years"]) == (2025, [2024, 2025])
    earlier = client.get("/api/companies/MA0000011488/kpis?fiscal_year=2024").json()
    assert earlier["fiscal_year"] == 2024
    growth = kpi(earlier, "revenue_growth")
    assert (growth["status"], growth["reason"]) == ("missing", "Missing: Revenue FY2023")
    missing = client.get("/api/companies/MA0000011488/kpis?fiscal_year=2019")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "no KPI values of MA0000011488 for FY2019"


def test_the_kpis_page_is_generated_from_the_rules_that_compute_them(client):
    """#27 AC4."""
    page = client.get("/api/kpis").json()
    assert (page["version"], page["since"]) == ("v1", "2026-10-29")
    assert [t["title"] for t in page["themes"]][:3] == ["Growth", "Profitability", "Returns"]
    assert len(page["kpis"]) == 18
    nde = next(k for k in page["kpis"] if k["name"] == "net_debt_to_ebitda")
    assert nde == {
        "name": "net_debt_to_ebitda",
        "title": "Net debt / EBITDA",
        "theme": "leverage",
        "means": "How many years of operating profit it would take to repay net debt.",
        "formula": "(long-term debt + short-term debt - cash and cash equivalents) / EBITDA",
        "inputs": ["Long-term debt", "Short-term debt", "Cash and cash equivalents", "EBITDA"],
        "read": (
            "below 2 comfortable; compare with the sector median; debt includes lease liabilities"
        ),
        "applies": "non_financial",
        "format": "multiple",
        "band": ["0", "2"],
        "tests": [],
    }
    score = next(k for k in page["kpis"] if k["name"] == "f_score")
    assert score["formula"] == "sum of 9 pass/fail tests"
    assert score["tests"][0] == {
        "name": "roa_positive",
        "title": "Positive ROA",
        "formula": "net income / total assets FY-1 > 0",
    }


def test_an_unknown_company_has_no_scorecard(client):
    assert client.get("/api/companies/MA0000000000/kpis").status_code == 404


def test_a_kpi_is_compared_with_its_sector_median_from_three_peers(
    client, store, meta, parsed, extracted
):
    """#7: a sector median needs three other companies of the sector, else too few peers."""
    # The fourth was computed under other rules: it does not count until recomputed.
    peers = {
        "MA0000000001": "0.10",
        "MA0000000002": "0.30",
        "MA0000000003": "0.20",
        "MA0000000004": "0.90",
    }
    rules = config.kpi_rules(config.label_map())
    shares = [ListedShare("IAM", "ITISSALAT AL-MAGHRIB", "Télécommunications", "Principal A")]
    for n, (isin, value) in enumerate(peers.items(), start=1):
        issuer = meta.issuer.model_copy(update={"isin": isin, "name": f"Peer {n}"})
        store.record_parse(
            meta.model_copy(update={"issuer": issuer}), parsed, make_run(), f"{n:064d}"
        )
        result = KpiResult("net_margin", 2025, KpiStatus.computed, Decimal(value), "", (), ())
        run = make_run().model_copy(update={"step": RunStep.compute, "output": None})
        sha256 = rules.sha256 if n < 4 else "a" * 64
        store.record_kpi_values(KpiChange(isin, (result,), (), run, "v1", sha256, "v1", 0))
        shares.append(ListedShare(f"P{n}", f"PEER {n}", "Télécommunications", "Principal A"))
    isins = {"IAM": "MA0000011488"} | {f"P{n}": isin for n, isin in enumerate(peers, start=1)}
    store.upsert_listings(XCAS, shares[:3], isins, datetime.now(UTC))
    review(client, rows_of(queue(client))[1])  # revenue FY2025: the scorecard has FY2025

    card = scorecard(client)
    assert card["sector"] == "Télécommunications"
    margin = kpi(card, "net_margin")
    assert (margin["peers"], margin["sector_median"]) == (2, None)  # too few peers
    store.upsert_listings(XCAS, shares, isins, datetime.now(UTC))
    margin = kpi(scorecard(client), "net_margin")
    assert (margin["peers"], margin["sector_median"]) == (3, "0.20")


DIVIDEND = SourceParagraph(
    2,
    "Le Conseil proposera un dividende de 4,00 dirhams par action au titre de l'exercice 2025.",
    ((2, 50.0, 400.0, 540.0, 420.0),),
)


def test_a_declared_dividend_is_checked_in_the_inspector_and_feeds_the_payout(
    client, store, extracted, document_id
):
    """#27: the payout ratio reads the dividend declared for the year, once a person checks it."""
    dividend = {
        "company": {"written": "Le Conseil", "name": "Maroc Telecom", "kind": "company"},
        "measure": "per_share",
        "amount": "4,00",
        "unit": "MAD",
        "status": "proposed",
        "fiscal_year": 2025,
        "source_id": "p2.0",
        "quote": "un dividende de 4,00 dirhams par action au titre de l'exercice 2025",
    }
    response = {k.value: [dividend] if k == FactKind.dividend else [] for k in FactKind}
    run = make_run(20).model_copy(update={"step": RunStep.extract_facts, "output": None})
    store.record_fact_extraction(
        document_id, fact_drafts(response, page_sources(2, [DIVIDEND], [])), run
    )
    link_names(document_id, store)
    [fact], _ = store.facts("MA0000011488")
    assert client.get(f"/api/facts/{fact.id}").json()["feeds"] == ["Payout ratio"]

    review(client, rows_of(queue(client))[1])  # revenue FY2025: the scorecard has FY2025
    declared = next(
        i
        for i in kpi(scorecard(client), "payout_ratio")["inputs"]
        if i["name"] == "declared_dividend_per_share"
    )
    assert (declared["status"], declared["value_as_written"]) == ("unchecked", "4,00")

    # CHECKS lists it with the figures, counted, until a person keeps it in the inspector.
    before = queue(client)
    [row] = before["dividends"]
    assert (row["company"]["name"], row["fiscal_year"]) == ("Maroc Telecom", 2025)
    # The company filter is the declaring company's.
    assert queue(client, isin="MA0000011488")["dividends"] == before["dividends"]
    assert (row["fact"]["id"], row["status"], row["feeds"]) == (
        fact.id,
        "to_check",
        ["Payout ratio"],
    )
    kept = client.post(f"/api/facts/{fact.id}/reviews", json={"verdict": "accepted"})
    assert kept.status_code == 201
    after = queue(client)
    assert after["dividends"][0]["status"] == "accepted"
    assert after["counts"]["to_check"] == before["counts"]["to_check"] - 1
    assert after["counts"]["done"] == before["counts"]["done"] + 1
    declared = next(
        i
        for i in kpi(scorecard(client), "payout_ratio")["inputs"]
        if i["name"] == "declared_dividend_per_share"
    )
    assert (declared["status"], declared["checked_by"]) == ("checked", "Z. Bajjou")
