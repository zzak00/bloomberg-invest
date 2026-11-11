"""Listings and daily closes (#26): market data, kept beside the graph (ADR 0003).

A share has one current close per session and source. A re-run that reads the same close writes
nothing; a newer answer with a different close supersedes the stored one, which is kept (#19 R4).
"""

from datetime import datetime
from decimal import Decimal

from neo4j import ManagedTransaction

from bloomberg_invest.domain.prices import Close, ListedShare, StoredClose, listing_key
from bloomberg_invest.views import Listing

# Uniqueness over several properties, which Neo4j Community enforces too. "One current close per
# session and source" needs a partial constraint Community lacks: `_add_prices` keeps it, in the
# share's transaction.
PRICE_CONSTRAINTS = [
    # Before supersession, a Price was unique on (listing, date, source).
    "DROP CONSTRAINT price_key IF EXISTS",
    "CREATE CONSTRAINT listing_ticker IF NOT EXISTS FOR (n:Listing) REQUIRE (n.mic, n.ticker) IS UNIQUE",
    "CREATE CONSTRAINT listing_key IF NOT EXISTS FOR (n:Listing) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT price_fetch IF NOT EXISTS FOR (n:Price) REQUIRE (n.listing, n.date, n.source, n.fetched_at) IS UNIQUE",
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
    """Store the closes that are new, or that differ from the current one and come from a later
    answer; return how many were written. Replaying older answers never undoes a newer one."""
    # Lock the share first: two runs at once (the schedule and a manual daily) take turns, so
    # neither reads a current close the other is replacing.
    tx.run("MATCH (l:Listing {key: $key}) SET l.prices_written_at = $at", key=key, at=fetched_at)
    record = tx.run(
        """
        MATCH (l:Listing {key: $key})
        UNWIND $closes AS c
        OPTIONAL MATCH (old:Price {listing: $key, date: c.session, source: $source})
        WHERE NOT coalesce(old.superseded, false)
        WITH l, c, old
        WHERE (old IS NULL OR (old.close <> c.close AND old.fetched_at < $at))
          AND NOT EXISTS {
            MATCH (:Price {listing: $key, date: c.session, source: $source, fetched_at: $at})
          }
        CREATE (p:Price {listing: $key, date: c.session, source: $source, close: c.close,
                         currency: $currency, fetched_at: $at})
        CREATE (l)-[:HAS_PRICE]->(p)
        FOREACH (_ IN CASE WHEN old IS NULL THEN [] ELSE [1] END |
            SET old.superseded = true
            CREATE (old)-[:SUPERSEDED_BY]->(p))
        RETURN count(p) AS written
        """,
        key=key,
        source=source,
        currency=currency,
        at=fetched_at,
        closes=[
            {"session": c.session, "close": decimal_text(c.close)}
            for c in closes
            if c.close is not None
        ],
    ).single()
    return record["written"] if record else 0


def decimal_text(value: Decimal) -> str:
    """One way to write a close, so `88.90` and `88.9` are the same: no trailing zeros."""
    return format(value.normalize(), "f")


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
