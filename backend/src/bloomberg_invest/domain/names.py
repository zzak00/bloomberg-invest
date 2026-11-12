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


class EntityKind(StrEnum):
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
        return self in (EntityKind.free_float, EntityKind.treasury_shares)


AGGREGATE_NAMES = {
    EntityKind.free_float: "Free float",
    EntityKind.treasury_shares: "Treasury shares",
}


def name_key(name: str) -> str:
    """The key two names of the same Organisation or Person share: `Maroc Telecom SA` and
    `MAROC TÉLÉCOM` are `maroc telecom`. Empty for a name of only punctuation or legal forms."""
    text = _SHORT_FORM.sub(" ", name)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = _NOT_WORD.sub(" ", text)
    # `S.A` became `s a`: drop legal forms after punctuation is gone, then tidy the spaces.
    text = _LEGAL.sub(" ", f" {text} ")
    return " ".join(text.split())


def alias_key(name: str, kind: EntityKind, held_key: str = "") -> str:
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
    not_an_entity = "not_an_entity"  # no Organisation or Person: a group of people, a brand...
    reopened = "reopened"  # undoes the decision before; the name goes back to CHECKS


@dataclass(frozen=True)
class NameReviewDraft:
    verdict: NameVerdict
    reviewer: str
    reviewed_at: datetime
    entity_id: str | None = None  # same_as
    name: str | None = None  # new
    kind: EntityKind | None = None  # new

    def __post_init__(self) -> None:
        if (self.verdict == NameVerdict.same_as) != (self.entity_id is not None):
            raise ValueError("a name is the same as one entity, named by its id")
        if (self.verdict == NameVerdict.new) != (self.name is not None and self.kind is not None):
            raise ValueError("a new entity has a name and a kind")
        if self.kind is not None and self.kind.aggregate:
            raise ValueError("an aggregate is never created by hand: one comes with each company")
