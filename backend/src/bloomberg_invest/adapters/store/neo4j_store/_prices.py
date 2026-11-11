"""Listings and daily closes (#26): market data, kept beside the graph (ADR 0003).

A Price is keyed by (listing, date, source), so a re-run writes nothing new, and a close already
stored is never overwritten.
"""

from datetime import datetime
from decimal import Decimal

from neo4j import ManagedTransaction

from bloomberg_invest.domain.prices import Close, ListedShare, StoredClose, listing_key
from bloomberg_invest.views import Listing

# Uniqueness over several properties, which Neo4j Community enforces too.
PRICE_CONSTRAINTS = [
    "CREATE CONSTRAINT listing_ticker IF NOT EXISTS FOR (n:Listing) REQUIRE (n.mic, n.ticker) IS UNIQUE",
    "CREATE CONSTRAINT listing_key IF NOT EXISTS FOR (n:Listing) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT price_key IF NOT EXISTS FOR (n:Price) REQUIRE (n.listing, n.date, n.source) IS UNIQUE",
]


def _upsert_listings(
    tx: ManagedTransaction, mic: str, shares: list[ListedShare], isins: dict[str, str], at: datetime
) -> list[str]:
    gone = tx.run(
        "MATCH (l:Listing {mic: $mic}) WHERE NOT l.ticker IN $tickers "
        "RETURN l.ticker AS ticker ORDER BY ticker",
        mic=mic,
        tickers=[s.ticker for s in shares],
    )
    delisted = [r["ticker"] for r in gone]
    tx.run(
        """
        UNWIND $shares AS s
        MERGE (l:Listing {mic: $mic, ticker: s.ticker})
        SET l.key = s.key, l.name = s.name, l.sector = s.sector, l.compartment = s.compartment,
            l.refreshed_at = $at
        WITH l, s WHERE s.isin IS NOT NULL
        MATCH (o:Organisation {isin: s.isin})
        MERGE (o)-[:LISTED_AS]->(l)
        """,
        mic=mic,
        at=at,
        shares=[
            {
                "ticker": s.ticker,
                "key": listing_key(s.ticker, mic),
                "name": s.name,
                "sector": s.sector,
                "compartment": s.compartment,
                "isin": isins.get(s.ticker),
            }
            for s in shares
        ],
    )
    return delisted


def _add_prices(
    tx: ManagedTransaction,
    key: str,
    closes: list[Close],
    source: str,
    currency: str,
    fetched_at: datetime,
) -> int:
    summary = tx.run(
        """
        MATCH (l:Listing {key: $key})
        UNWIND $closes AS c
        MERGE (p:Price {listing: $key, date: c.session, source: $source})
        ON CREATE SET p.close = c.close, p.currency = $currency, p.fetched_at = $at
        MERGE (l)-[:HAS_PRICE]->(p)
        """,
        key=key,
        source=source,
        currency=currency,
        at=fetched_at,
        closes=[
            {"session": c.session, "close": str(c.close)} for c in closes if c.close is not None
        ],
    ).consume()
    return summary.counters.nodes_created


def _stored(record) -> StoredClose:
    p = record["p"]
    return StoredClose(
        session=p["date"].to_native(),
        close=Decimal(p["close"]),
        source=p["source"],
        currency=p["currency"],
    )


def _listing(node) -> Listing:
    return Listing(
        ticker=node["ticker"],
        mic=node["mic"],
        name=node["name"],
        sector=node["sector"],
        compartment=node["compartment"],
    )
