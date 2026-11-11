"""The price source interface (#19 R11): where daily closes come from, one per exchange."""

from collections.abc import Iterator
from datetime import date, datetime
from typing import Protocol

from bloomberg_invest.domain.prices import Close, Holiday, ListedShare


class PriceSourceError(Exception):
    """The source could not be read, or answered in a shape we don't know."""


class PriceSource(Protocol):
    mic: str  # the exchange it covers (ISO 10383)
    source: str  # what a Price from it records as its source
    currency: str  # the currency its closes are in

    def listings(self) -> list[ListedShare]:
        """Every share the exchange lists."""

    def holidays(self) -> list[Holiday]:
        """The days the exchange is closed, as far as it publishes them."""

    def closes(self, ticker: str, start: date, end: date) -> list[Close]:
        """A share's sessions from `start` to `end`, oldest first. Ask for one year or less:
        a longer range, or one starting before the source's history, may answer nothing."""


class PriceArchive(Protocol):
    """The answers a source gave, kept as returned, so closes can be rebuilt without asking."""

    def latest_listings(self) -> list[ListedShare]:
        """The shares of the latest listing archived."""

    def closes(self) -> Iterator[tuple[str, datetime, list[Close]]]:
        """Every archived answer for closes, oldest fetch first: ticker, when, sessions."""
