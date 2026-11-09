"""An issuer's dossier: its filings and how the label map groups its figures (#19 R19)."""

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.views import Company, Statement


def company(isin: str, store: GraphStore, label_map: LabelMap) -> Company | None:
    documents = store.list_documents(isin)
    if not documents:
        return None
    return Company(
        issuer=documents[0].issuer,
        documents=documents,
        statements=[
            Statement(
                key=key,
                title=title,
                line_items=[i.name for i in label_map.items.values() if i.statement == key],
            )
            for key, title in label_map.statements.items()
        ],
    )
