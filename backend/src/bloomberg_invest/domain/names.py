"""Names as filings write them, and the key an Alias is matched by (#19 R7).

A filing names one Organisation many ways: `Maroc Telecom SA`, `Groupe Maroc Telecom`,
`Itissalat Al-Maghrib (IAM) S.A`. The key forgives case, accents, punctuation and legal forms,
nothing more: a name whose key matches no Organisation or Person, or more than one, goes to a
person in CHECKS, never to a guess.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

# Legal forms and group words that say nothing about which Organisation is meant, as whole words.
LEGAL_FORMS = {"sa", "s a", "sarl", "sas", "sca", "spa", "plc", "ltd", "inc", "group", "groupe"}
_LEGAL = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in sorted(LEGAL_FORMS, key=len, reverse=True)) + r")\b"
)
_NOT_WORD = re.compile(r"[^a-z0-9]+")
# A parenthesised short form: `Itissalat Al-Maghrib (IAM) S.A` is `Itissalat Al-Maghrib S.A`.
_SHORT_FORM = re.compile(r"\([^)]*\)|«[^»]*»")


class PartyKind(StrEnum):
    """What a name stands for. Organisation kinds follow the ontology (AGENTS.md); the two
    aggregates stand for a company's own holders, never for an Organisation of their own."""

    company = "company"
    holding = "holding"
    state = "state"
    pension_fund = "pension_fund"
    insurer = "insurer"
    bank = "bank"
    audit_firm = "audit_firm"
    person = "person"
    free_float = "free_float"
    treasury_shares = "treasury_shares"

    @property
    def aggregate(self) -> bool:
        return self in (PartyKind.free_float, PartyKind.treasury_shares)


AGGREGATE_NAMES = {
    PartyKind.free_float: "Free float",
    PartyKind.treasury_shares: "Treasury shares",
}


def fold(text: str) -> str:
    """Text in lower case without accents: `Télécom` is `telecom`."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def name_key(name: str) -> str:
    """The key two names of the same Organisation or Person share: `Maroc Telecom SA` and
    `MAROC TÉLÉCOM` are `maroc telecom`. Empty for a name of only punctuation or legal forms."""
    text = _NOT_WORD.sub(" ", fold(_SHORT_FORM.sub(" ", name)))
    # `S.A` became `s a`: drop legal forms after punctuation is gone, then tidy the spaces.
    text = _LEGAL.sub(" ", f" {text} ")
    return " ".join(text.split())


def alias_key(name: str, kind: PartyKind, held_key: str = "") -> str:
    """The key an Alias is stored and matched by. An aggregate is one per company, so its key
    names the company it belongs to: every filing's `Autres` of Maroc Telecom is one Alias, and
    another company's is another."""
    if kind.aggregate:
        return f"{kind.value}:{held_key}"
    return name_key(name)


class Known(Protocol):
    """An Organisation or Person and every name it is known by."""

    @property
    def id(self) -> str: ...
    @property
    def names(self) -> list[str]: ...


def matches[K: Known](key: str, known: Iterable[K]) -> list[K]:
    """The Organisations and Persons one of whose names has this key. A name links only when
    exactly one does (#19 R7): none or several go to a person."""
    return [k for k in known if any(name_key(n) == key for n in k.names)]


def similar[K: Known](key: str, known: Iterable[K], limit: int = 5) -> list[K]:
    """The Organisations and Persons a person most likely means by a name no rule linked: those
    sharing the most words with it, then by name. A misspelt `Moov Afrivca Niger` still shares
    two words with `Moov Africa Niger`."""
    words = set(key.split())
    scored = []
    for k in known:
        shared = max((len(words & set(name_key(n).split())) for n in k.names), default=0)
        if shared:
            scored.append((-shared, min(k.names), k))
    return [k for _, _, k in sorted(scored, key=lambda s: (s[0], s[1]))[:limit]]


class NameVerdict(StrEnum):
    """What a person decides a name stands for, in CHECKS Names."""

    same_as = "same_as"  # an Organisation or Person already known
    new = "new"  # one created for it
    not_a_party = "not_a_party"  # no Organisation or Person: a group of people, a brand...
    reopened = "reopened"  # undoes the decision before; the name goes back to CHECKS


@dataclass(frozen=True)
class NameReviewDraft:
    verdict: NameVerdict
    reviewer: str
    reviewed_at: datetime
    party_id: str | None = None  # same_as
    name: str | None = None  # new
    kind: PartyKind | None = None  # new

    def __post_init__(self) -> None:
        if (self.verdict == NameVerdict.same_as) != (self.party_id is not None):
            raise ValueError("a name is the same as one Organisation or Person, named by its id")
        if (self.verdict == NameVerdict.new) != (self.name is not None and self.kind is not None):
            raise ValueError("a new Organisation or Person has a name and a kind")
        if self.kind is not None and self.kind.aggregate:
            raise ValueError("an aggregate is never created by hand: one comes with each company")


@dataclass(frozen=True)
class AggregateName:
    """The Alias a company's free float or treasury shares are named by in every filing."""

    key: str
    kind: PartyKind
    name: str


def aggregates_of(company_key: str) -> list[AggregateName]:
    """The aggregate Aliases that belong to the company with this name key."""
    return [
        AggregateName(alias_key("", kind, company_key), kind, AGGREGATE_NAMES[kind])
        for kind in AGGREGATE_NAMES
    ]


def aggregate_of(key: str) -> tuple[PartyKind, str] | None:
    """For an aggregate Alias key, its kind and its company's name key; None for a name."""
    kind, sep, company = key.partition(":")
    if not sep or kind not in AGGREGATE_NAMES:
        return None
    return PartyKind(kind), company


class NameStatus(StrEnum):
    """Where a CHECKS Names row stands."""

    to_check = "to_check"
    resolved = "resolved"
    not_a_party = "not_a_party"


def name_status(resolved: bool, not_a_party: bool) -> NameStatus:
    if not_a_party:
        return NameStatus.not_a_party
    return NameStatus.resolved if resolved else NameStatus.to_check
