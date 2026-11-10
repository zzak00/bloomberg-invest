"""The KPI rules: for now, the figures each KPI and screen reads (#7, #19 R10, R14). Loaded from
the versioned configuration in `bloomberg_invest/config/kpis/`."""

from dataclasses import dataclass

from bloomberg_invest.domain.label_map import LabelMap


@dataclass(frozen=True)
class Input:
    line_item: str
    breakdown: str = ""  # empty for the line item itself


@dataclass(frozen=True)
class Kpi:
    name: str
    title: str
    inputs: tuple[Input, ...]


@dataclass(frozen=True)
class KpiRules:
    version: str
    sha256: str  # of the configuration file
    kpis: dict[str, Kpi]

    def feeds(self, line_item: str, breakdown: str) -> list[str]:
        """The titles of the KPIs and screens that read this line item and breakdown."""
        wanted = Input(line_item, breakdown)
        return [kpi.title for kpi in self.kpis.values() if wanted in kpi.inputs]

    def check_against(self, label_map: LabelMap) -> None:
        """Fail when an input names a line item the label map does not have."""
        for kpi in self.kpis.values():
            for i in kpi.inputs:
                if i.line_item not in label_map.items:
                    raise ValueError(
                        f"KPI {kpi.name!r} reads {i.line_item!r}, which label map "
                        f"{label_map.version} does not have"
                    )
