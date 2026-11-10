"""The label map v1 and the extraction prompt, as the extractor loads them."""

import csv
from pathlib import Path

import pytest

from bloomberg_invest import config
from bloomberg_invest.domain.label_map import LabelMap, LineItem

GOLDEN = Path(__file__).parents[3] / "golden" / "maroc-telecom-rfa-2025" / "figures.csv"


@pytest.fixture(scope="module")
def label_map() -> LabelMap:
    return config.label_map()


def golden_rows() -> list[dict[str, str]]:
    with GOLDEN.open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_every_golden_line_item_is_in_the_map(label_map):
    assert {r["line_item"] for r in golden_rows()} <= set(label_map.items)


def test_flows_and_stocks_agree_with_how_golden_dates_them(label_map):
    # Golden dates a flow by its fiscal year (FY2025) and a stock by its day (2025-12-31).
    kinds: dict[str, set[str]] = {}
    for r in golden_rows():
        kinds.setdefault(r["line_item"], set()).add("flow" if r["period"][:2] == "FY" else "stock")
    # Golden dates the reported net debt by fiscal year on one page; it is a balance.
    assert kinds.pop("net_debt") == {"flow", "stock"}
    assert {name: {label_map.items[name].kind} for name in kinds} == kinds


def test_the_map_is_versioned_and_hashed(label_map):
    assert label_map.version == "v1"
    assert len(label_map.sha256) == 64
    assert next(iter(label_map.statements)) == "income_statement"


def test_a_line_item_must_name_a_known_statement():
    item = LineItem("revenue", "Revenue", "Revenue", statement="notes", kind="flow")
    with pytest.raises(ValueError, match="revenue"):
        LabelMap("v0", "", {"income_statement": "Income statement"}, {"revenue": item})


def test_the_prompt_is_the_bake_off_s_and_ends_where_the_line_items_go():
    prompt = config.extract_prompt()
    assert (prompt.name, prompt.version) == ("extract-figures", "v1")
    assert prompt.text.startswith("You extract financial figures from one page")
    assert prompt.text.endswith("Line items:\n")
