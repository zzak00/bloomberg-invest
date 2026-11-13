"""Versioned configuration shipped with the package: the label map, the extraction prompt, the
KPI rules and the listings' ISINs; the facts prompt.

A released version never changes; a new one is a new file. Runs record each version with the
SHA-256 of its file (#19 R3, R14).
"""

import hashlib
import re
import tomllib
from dataclasses import dataclass, replace
from decimal import Decimal
from importlib.resources import files

from bloomberg_invest.domain.kpis import (
    Declared,
    Formula,
    Input,
    Kpi,
    KpiRules,
    Source,
    Test,
    inputs_of,
)
from bloomberg_invest.domain.label_map import LabelMap, LineItem

LABEL_MAP = "v1"
EXTRACT_PROMPT = "v1"
FACTS_PROMPT = "v1"
KPI_RULES = "v1"
LISTINGS = "v1"
ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")

_HERE = files(__name__)


def label_map(version: str = LABEL_MAP) -> LabelMap:
    raw = (_HERE / "line_items" / f"{version}.toml").read_bytes()
    data = tomllib.loads(raw.decode())
    if data["version"] != version:
        raise ValueError(f"line_items/{version}.toml says it is {data['version']}")
    return LabelMap(
        version=version,
        sha256=hashlib.sha256(raw).hexdigest(),
        statements=data["statements"],
        items={name: LineItem(name=name, **item) for name, item in data["line_items"].items()},
    )


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    sha256: str
    text: str


def extract_prompt(version: str = EXTRACT_PROMPT) -> Prompt:
    raw = (_HERE / "prompts" / f"extract_figures_{version}.md").read_bytes()
    return Prompt("extract-figures", version, hashlib.sha256(raw).hexdigest(), raw.decode())


def facts_prompt(version: str = FACTS_PROMPT) -> Prompt:
    """What the LLM is told when it extracts the eight other kinds of Fact (#24)."""
    raw = (_HERE / "prompts" / f"extract_facts_{version}.md").read_bytes()
    return Prompt("extract-facts", version, hashlib.sha256(raw).hexdigest(), raw.decode())


def kpi_rules(against: LabelMap, version: str = KPI_RULES) -> KpiRules:
    """The KPI rules, checked against the label map in force: every input names a line item,
    and every formula reads only what the rules define."""
    raw = (_HERE / "kpis" / f"{version}.toml").read_bytes()
    data = tomllib.loads(raw.decode())
    if data["version"] != version:
        raise ValueError(f"kpis/{version}.toml says it is {data['version']}")
    sources: dict[str, Source] = {
        name: Declared(source["declared"]) for name, source in data.get("sources", {}).items()
    }
    titles = {name: item.title for name, item in against.items.items()} | data.get("titles", {})
    base = KpiRules(
        version=version,
        sha256=hashlib.sha256(raw).hexdigest(),
        kpis=(),
        since=data.get("since"),
        financial_sectors=tuple(data.get("financial_sectors", ())),
        sources=sources,
        not_reported=data.get("not_reported", {}),
        titles=titles,
        themes=data.get("themes", {}),
    )
    rules = replace(base, kpis=tuple(_kpi(name, kpi, base) for name, kpi in data["kpis"].items()))
    rules.check_against(against)
    return rules


def _kpi(name: str, kpi: dict, rules: KpiRules) -> Kpi:
    band = kpi.get("band")
    read = Kpi(
        name=name,
        title=kpi["title"],
        inputs=tuple(Input(i) if isinstance(i, str) else Input(**i) for i in kpi.get("inputs", ())),
        theme=kpi.get("theme", ""),
        means=kpi.get("means", ""),
        read=kpi.get("read", ""),
        format=kpi.get("format", "percent"),
        band=(Decimal(str(band[0])), Decimal(str(band[1]))) if band else None,
        applies=kpi.get("applies", "all"),
        formula=Formula.parse(kpi["formula"]) if "formula" in kpi else None,
        when=Formula.parse(kpi["when"]) if "when" in kpi else None,
        tests=tuple(
            Test(test_name, test["title"], Formula.parse(test["formula"]))
            for test_name, test in kpi.get("tests", {}).items()
        ),
    )
    if not read.formulas:
        return read
    if "inputs" in kpi:
        raise ValueError(f"KPI {name!r}: a computed KPI's inputs are read from its formulas")
    return replace(read, inputs=inputs_of(read.formulas, rules))


def listing_isins(mic: str, version: str = LISTINGS) -> dict[str, str]:
    """The ISIN of each ticker on the exchange `mic` whose company we ingest filings for."""
    data = tomllib.loads((_HERE / "listings" / f"{version}.toml").read_text())
    if data["version"] != version:
        raise ValueError(f"listings/{version}.toml says it is {data['version']}")
    isins = data.get(mic, {})
    for ticker, isin in isins.items():
        if not ISIN.fullmatch(isin):
            raise ValueError(f"listings/{version}.toml: {ticker} = {isin!r} is not an ISIN")
    return isins
