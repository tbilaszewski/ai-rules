"""Entity resolution with airules.

Two customer records are reduced to a set of similarity *signals*; the engine
decides whether they refer to the same real-world person.  The rules are ordered
by evidence strength: a definitive signal (exact email) fires first; weaker
combinations fire later; ``@Default`` is the safe fallback.

Run it:  python examples/entity_resolution.py
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Literal

from airules import Default, Fact, Field, KnowledgeEngine, NumberField, Rule


# ---------------------------------------------------------------------------
# Domain: comparison signals
# ---------------------------------------------------------------------------

EmailSignal = Literal["exact", "domain_only", "none"]
PhoneSignal = Literal["exact", "none"]


class CustomerSignals(Fact):
    """Similarity signals derived from comparing two customer records."""

    name_similarity: NumberField[float]   # 0.0–1.0
    email: Field[EmailSignal]
    address_similarity: NumberField[float]  # 0.0–1.0
    phone: Field[PhoneSignal]


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

class Resolution(StrEnum):
    MATCH = "match"
    POSSIBLE_MATCH = "possible-match"
    NO_MATCH = "no-match"


class EntityResolver(KnowledgeEngine[CustomerSignals, Resolution]):
    """Resolves whether two customer records refer to the same entity."""

    @Rule(CustomerSignals.email.eq("exact"))
    def exact_email(self, signals: CustomerSignals) -> Resolution:
        # Exact email is a definitive identifier on its own.
        return Resolution.MATCH

    @Rule(
        CustomerSignals.name_similarity.ge(0.90)
        & CustomerSignals.address_similarity.ge(0.85)
    )
    def strong_name_and_address(self, signals: CustomerSignals) -> Resolution:
        return Resolution.MATCH

    @Rule(
        CustomerSignals.name_similarity.ge(0.80) & CustomerSignals.phone.eq("exact")
    )
    def name_and_phone(self, signals: CustomerSignals) -> Resolution:
        return Resolution.MATCH

    @Rule(
        CustomerSignals.name_similarity.ge(0.70)
        & CustomerSignals.email.eq("domain_only")
        & CustomerSignals.address_similarity.ge(0.70)
    )
    def weak_signals_corroborate(self, signals: CustomerSignals) -> Resolution:
        return Resolution.POSSIBLE_MATCH

    @Default
    def insufficient_evidence(self, signals: CustomerSignals) -> Resolution:
        return Resolution.NO_MATCH


# ---------------------------------------------------------------------------
# Signal computation (infrastructure — outside the domain/engine)
# ---------------------------------------------------------------------------

@dataclass
class CustomerRecord:
    name: str
    email: str
    address: str
    phone: str


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _email_signal(a: str, b: str) -> EmailSignal:
    if a.lower() == b.lower():
        return "exact"
    if a.split("@")[-1].lower() == b.split("@")[-1].lower():
        return "domain_only"
    return "none"


def _phone_signal(a: str, b: str) -> PhoneSignal:
    normalised = lambda p: "".join(c for c in p if c.isdigit())
    na, nb = normalised(a), normalised(b)
    return "exact" if na and nb and na == nb else "none"


def compare(a: CustomerRecord, b: CustomerRecord) -> CustomerSignals:
    return CustomerSignals(
        name_similarity=round(_similarity(a.name, b.name), 3),
        email=_email_signal(a.email, b.email),
        address_similarity=round(_similarity(a.address, b.address), 3),
        phone=_phone_signal(a.phone, b.phone),
    )


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main() -> None:
    resolver = EntityResolver()

    pairs: list[tuple[str, CustomerRecord, CustomerRecord]] = [
        (
            "same email, slightly different name (typo)",
            CustomerRecord("John Smith", "john@example.com", "12 Baker St", "555-0100"),
            CustomerRecord("Jon Smith",  "john@example.com", "12 Baker St", "555-0100"),
        ),
        (
            "same name and address, no email/phone overlap",
            CustomerRecord("Maria Garcia", "m.garcia@corp.com", "5 Oak Ave, Boston", ""),
            CustomerRecord("Maria Garcia", "garcia.m@personal.io", "5 Oak Ave, Boston", ""),
        ),
        (
            "name + phone match, different address",
            CustomerRecord("David Lee", "dlee@work.com", "Old address", "555-0200"),
            CustomerRecord("David Lee", "d.lee@home.net", "New address", "555-0200"),
        ),
        (
            "same company domain, similar name and address",
            CustomerRecord("Sophie Brown", "s.brown@acme.com",  "7 Elm Rd, Chicago", ""),
            CustomerRecord("S. Brown",     "sbrown@acme.com",   "7 Elm Road, Chicago", ""),
        ),
        (
            "completely different people",
            CustomerRecord("Alice Wong", "alice@x.com", "1 Main St", "555-0300"),
            CustomerRecord("Bob Müller", "bob@y.com",   "99 Side Rd", "555-0400"),
        ),
    ]

    for label, rec_a, rec_b in pairs:
        signals = compare(rec_a, rec_b)
        result = resolver.run(signals)
        print(
            f"{label!r}\n"
            f"  signals : name={signals.name_similarity:.2f}  "
            f"email={signals.email}  "
            f"addr={signals.address_similarity:.2f}  "
            f"phone={signals.phone}\n"
            f"  decision: {result}\n"
        )


if __name__ == "__main__":
    main()
