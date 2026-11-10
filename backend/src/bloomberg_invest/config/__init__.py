"""Versioned configuration shipped with the package: the label map, the extraction prompt and the
KPI rules.

A released version never changes; a new one is a new file. Runs record each version with the
SHA-256 of its file (#19 R3, R14).
"""

import hashlib
import tomllib
from dataclasses import dataclass
from importlib.resources import files

from bloomberg_invest.domain.kpis import Input, Kpi, KpiRules
from bloomberg_invest.domain.label_map import LabelMap, LineItem

LABEL_MAP = "v1"
EXTRACT_PROMPT = "v1"
KPI_RULES = "v1"

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


def kpi_rules(version: str = KPI_RULES, against: LabelMap | None = None) -> KpiRules:
    """The KPI rules, checked against the label map in force: every input names a line item."""
    raw = (_HERE / "kpis" / f"{version}.toml").read_bytes()
    data = tomllib.loads(raw.decode())
    if data["version"] != version:
        raise ValueError(f"kpis/{version}.toml says it is {data['version']}")
    rules = KpiRules(
        version=version,
        sha256=hashlib.sha256(raw).hexdigest(),
        kpis={
            name: Kpi(
                name=name,
                title=kpi["title"],
                inputs=tuple(Input(i) if isinstance(i, str) else Input(**i) for i in kpi["inputs"]),
            )
            for name, kpi in data["kpis"].items()
        },
    )
    rules.check_against(against or label_map())
    return rules
