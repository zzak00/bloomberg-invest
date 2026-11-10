"""The LLM contract, on every implementation: a replayed recording, the recorder around it, the
fake the service tests use, and Azure OpenAI when its secrets are in the environment (`-m live`,
with `--env-file`). The page is synthetic.

Record the replayed answer again after changing the prompt or the label map:

    LLM_RECORD=1 uv run --extra ingest --env-file <secrets> pytest tests/integration/test_llm.py
"""

import os

import pytest
from conftest import FIXTURES, azure_settings
from fakes import PageReadingLLM

from bloomberg_invest import bootstrap, config
from bloomberg_invest.adapters.llm import LLM
from bloomberg_invest.adapters.llm.recording import RecordingLLM, ReplayLLM
from bloomberg_invest.domain.extraction import (
    SourceCell,
    SourceParagraph,
    instructions,
    page_sources,
    schema,
)

RECORDING = FIXTURES / "recordings" / "llm-contract.jsonl"
CELLS = [
    SourceCell(f"c{r}{c}", 0, 1, r, c, 1, text, (0, 0, 1, 1))
    for r, row in enumerate(
        [
            ("(En millions MAD)", "31-déc.-24", "31-déc.-25"),
            ("Chiffre d'affaires", "36 699", "36 681"),
        ]
    )
    for c, text in enumerate(row)
]
PARAGRAPHS = [SourceParagraph(1, "ÉTAT DE RÉSULTAT GLOBAL CONSOLIDÉ (IFRS)", ())]


def azure() -> LLM:
    live = bootstrap.LLMS["azure-openai"](azure_settings())
    return RecordingLLM(live, RECORDING) if os.environ.get("LLM_RECORD") else live


@pytest.fixture(
    params=["replay", "recording", "fake", pytest.param("azure-openai", marks=pytest.mark.live)]
)
def llm(request, tmp_path) -> LLM:
    match request.param:
        case "replay":
            return ReplayLLM(RECORDING)
        case "recording":
            return RecordingLLM(ReplayLLM(RECORDING), tmp_path / "recording.jsonl")
        case "fake":
            return PageReadingLLM({"36 681": {}, "36 699": {"fiscal_year": 2024}})
        case _:
            return azure()


def test_the_model_cites_the_cell_and_copies_the_value_as_written(llm):
    label_map = config.label_map()
    page = page_sources(1, PARAGRAPHS, CELLS)
    system = instructions(config.extract_prompt().text, label_map)

    answer = llm.complete_json(system, page.prompt, "figures", schema(label_map))

    revenue = {(f["line_item"], f["fiscal_year"]): f for f in answer["figures"] if f["source_id"]}
    assert revenue[("revenue", 2025)]["source_id"] == "t1.0.r1.c2"
    assert revenue[("revenue", 2025)]["value_as_written"] == "36 681"
    assert revenue[("revenue", 2024)]["source_id"] == "t1.0.r1.c1"
    assert {f["basis_scope"] for f in answer["figures"]} == {"consolidated"}


def test_the_model_names_its_tool_deployment_and_configuration(llm):
    assert llm.tool and llm.tool_version
    assert llm.model == llm.config["deployment"]
