"""The Bourse de Casablanca's own site as a price source (#15).

- Closes: `/api/boursenova/stock-historical`, one share and date range per request, JSON.
- Shares and holidays: the issuer list and holiday pages carry them in their Drupal settings JSON.

None of it is documented, and the site changed once already, so an answer in an unknown shape
stops the run with the address named. Every answer is kept as returned in a `RawArchive`, so the
stored closes can be rebuilt without asking again: the site keeps only three years.
"""

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from bloomberg_invest.adapters.prices import PriceArchive, PriceSource, PriceSourceError
from bloomberg_invest.domain.prices import XCAS, Close, Holiday, ListedShare

SITE = "https://www.casablanca-bourse.com"
SOURCE = "bourse-casablanca"
SETTINGS = re.compile(
    r'<script type="application/json" data-drupal-selector="drupal-settings-json">(.*?)</script>',
    re.DOTALL,
)
STAMP = "%Y%m%dT%H%M%S%fZ"

Fetch = Callable[[str], bytes]


def tls_context() -> ssl.SSLContext:
    """The system's trusted roots plus the intermediate the Bourse's server leaves out of its
    chain: the certificate is still checked in full, hostname included."""
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=_MISSING_INTERMEDIATE)
    return context


_MISSING_INTERMEDIATE = (files(__package__) / "sectigo-dv-r36.pem").read_text()
_TLS = tls_context()


def http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "bloomberg-invest daily closes"})
    with urllib.request.urlopen(request, timeout=30, context=_TLS) as response:
        return response.read()


class RawArchive(PriceArchive):
    """Every answer as the source gave it, under `root`: `<ticker>/<fetched at>_<start>_<end>_p<page>.json`
    for closes, `listings/` and `holidays/` for the pages."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, name: str, fetched_at: datetime, body: bytes) -> None:
        path = self.root / name.replace("{at}", fetched_at.strftime(STAMP))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def closes(self) -> Iterator[tuple[str, datetime, list[Close]]]:
        """Every archived answer for closes, oldest fetch first: ticker, when, sessions."""
        files = [
            (datetime.strptime(f.name.split("_")[0], STAMP).replace(tzinfo=UTC), f)
            for f in self.root.glob("*/*.json")
            if f.parent.name not in ("listings", "holidays")
        ]
        for fetched_at, f in sorted(files):
            sessions = parse_closes(f.read_bytes(), str(f))[0]
            yield f.parent.name, fetched_at, sorted(sessions, key=lambda c: c.session)

    def listings(self) -> list[ListedShare]:
        pages = sorted((self.root / "listings").glob("*.html"))
        if not pages:
            raise PriceSourceError(f"no listings archived under {self.root}")
        latest: dict[str, ListedShare] = {}
        for page in pages:  # oldest first, so a later page wins
            latest |= {s.ticker: s for s in parse_listings(page.read_bytes(), str(page))}
        return [latest[t] for t in sorted(latest)]


@dataclass
class BourseCasablanca(PriceSource):
    fetch: Fetch = http_get
    archive: RawArchive | None = None
    pause: float = 1.0  # seconds between requests, to stay a light visitor
    page_size: int = 1000
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    sleep: Callable[[float], None] = time.sleep

    mic = XCAS
    source = SOURCE
    currency = "MAD"

    def __post_init__(self) -> None:
        self._last: float | None = None

    def listings(self) -> list[ListedShare]:
        url = f"{SITE}/emetteurs/liste-emetteurs"
        return parse_listings(self._get(url, "listings/{at}.html"), url)

    def holidays(self) -> list[Holiday]:
        url = f"{SITE}/market-data/jours-feries"
        return parse_holidays(self._get(url, "holidays/{at}.html"), url)

    def closes(self, ticker: str, start: date, end: date) -> list[Close]:
        out: list[Close] = []
        page = 1
        while True:
            query = urllib.parse.urlencode(
                {
                    "instrument": ticker,
                    "market": "comptant",
                    "type": "actions",
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "pageNumber": page,
                    "pageSize": self.page_size,
                }
            )
            url = f"{SITE}/api/boursenova/stock-historical?{query}"
            body = self._get(url, f"{ticker}/{{at}}_{start}_{end}_p{page}.json")
            sessions, total = parse_closes(body, url)
            out += sessions
            if not sessions or len(out) >= total:
                return sorted(out, key=lambda c: c.session)
            page += 1

    def _get(self, url: str, name: str) -> bytes:
        if self._last is not None:
            self.sleep(max(0.0, self.pause - (time.monotonic() - self._last)))
        try:
            body = self.fetch(url)
        except OSError as error:
            raise PriceSourceError(f"{url}: {error}") from error
        finally:
            self._last = time.monotonic()
        if self.archive:
            self.archive.save(name, self.clock(), body)
        return body


def parse_closes(body: bytes, url: str) -> tuple[list[Close], int]:
    """The sessions in a `stock-historical` answer, and how many the range holds in all."""
    try:
        answer = json.loads(body)
        sessions = [
            Close(
                session=datetime.strptime(item["seance"], "%d/%m/%Y").date(),
                close=None if item["dernierCours"] is None else Decimal(str(item["dernierCours"])),
            )
            for item in answer["items"]
        ]
        return sessions, int(answer["totalCount"])
    except (ValueError, KeyError, TypeError) as error:
        raise PriceSourceError(f"{url} answered in a shape we don't know: {error!r}") from error


def _settings(body: bytes, url: str) -> dict:
    match = SETTINGS.search(body.decode("utf-8", errors="replace"))
    if not match:
        raise PriceSourceError(f"{url} has no Drupal settings JSON any more")
    try:
        return json.loads(match.group(1))["boursenova"]
    except (ValueError, KeyError) as error:
        raise PriceSourceError(f"{url}: its settings hold no boursenova data") from error


def parse_listings(body: bytes, url: str) -> list[ListedShare]:
    """The shares of the issuer list, with their issuer's sector; bonds and rights are left out."""
    try:
        return sorted(
            (
                ListedShare(
                    ticker=instrument["symbol"].strip(),
                    name=instrument["label"]["fr"].strip(),
                    sector=issuer["sector"]["fr"].strip(),
                    compartment=instrument["compartment"]["fr"].strip(),
                )
                for issuer in _settings(body, url)["emetteurs"]
                for instrument in issuer["instruments"]
                if instrument["type"]["en"].strip() == "Stock"
            ),
            key=lambda s: s.ticker,
        )
    except (KeyError, TypeError, AttributeError) as error:
        raise PriceSourceError(f"{url}: the issuer list changed shape: {error!r}") from error


def parse_holidays(body: bytes, url: str) -> list[Holiday]:
    try:
        return [
            Holiday(day=date.fromisoformat(h["date"]), confirmed=bool(h["is_confirmed"]))
            for h in _settings(body, url)["holidays"]
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise PriceSourceError(f"{url}: the holiday list changed shape: {error!r}") from error
