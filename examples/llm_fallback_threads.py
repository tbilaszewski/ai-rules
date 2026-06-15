"""
Support-ticket router — deterministic rules first, LLM fallback.

Known routing patterns are handled by @Rule methods at zero API cost.
The @Default fires only when no rule matches, calling the LLM to classify
the unusual case that nobody anticipated at design time.

The LLM receives the engine's full rule schema via describe(), so it knows
exactly which patterns are already handled and can reason about what's left.

Multiple tickets are evaluated in parallel using a ThreadPoolExecutor —
rule hits resolve instantly in their thread, LLM calls block their thread
but run concurrently with each other.

Install PydanticAI with the OpenAI provider before running:
    uv add "pydantic-ai[openai]"
"""

import json
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

from pydantic_ai import Agent

from airules import Default, Fact, KnowledgeEngine, Rule, StringField


class Team(Enum):
    BILLING = "billing"
    AUTH = "auth"
    SHIPPING = "shipping"
    RETURNS = "returns"
    GENERAL = "general"


class Ticket(Fact):
    subject: StringField
    body: StringField


class TicketRouter(KnowledgeEngine[Ticket, Team]):
    """Routes support tickets to the right team.

    High-volume, well-understood patterns are handled by rules — cheap and
    instant. Only tickets that fall outside every rule reach the LLM, so
    the API is called only when it genuinely adds value.
    """

    @Rule(
        Ticket.subject.contains("billing", case_insensitive=True)
        | Ticket.body.contains("invoice", case_insensitive=True)
        | Ticket.body.contains("charge", case_insensitive=True)
    )
    def billing(self, ticket: Ticket) -> Team:
        return Team.BILLING

    @Rule(
        Ticket.subject.contains("password", case_insensitive=True)
        | Ticket.subject.contains("login", case_insensitive=True)
        | Ticket.subject.contains("account", case_insensitive=True)
    )
    def auth(self, ticket: Ticket) -> Team:
        return Team.AUTH

    @Rule(
        Ticket.subject.contains("shipping", case_insensitive=True)
        | Ticket.subject.contains("delivery", case_insensitive=True)
        | Ticket.body.contains("tracking number", case_insensitive=True)
    )
    def shipping(self, ticket: Ticket) -> Team:
        return Team.SHIPPING

    @Rule(
        Ticket.subject.contains("return", case_insensitive=True)
        | Ticket.subject.contains("refund", case_insensitive=True)
    )
    def returns(self, ticket: Ticket) -> Team:
        return Team.RETURNS

    @Default
    def llm_fallback(self, ticket: Ticket) -> Team:
        """Called only when no deterministic rule matches.

        agent.run_sync() blocks the calling thread — the caller is responsible
        for running tickets in parallel (see main()).
        """
        team_values = ", ".join(t.value for t in Team)
        rules_schema = json.dumps(type(self).describe(), indent=2)
        agent = Agent(
            "openai-chat:gpt-5.4-mini",
            output_type=Team,
            system_prompt=(
                f"You are a support ticket classifier. Classify tickets into one of: {team_values}.\n\n"
                "The following rules already handle common cases deterministically. "
                "You only receive tickets that matched none of them — your job is to decide "
                "the best team for these edge cases.\n\n"
                f"Existing rules:\n{rules_schema}"
            ),
        )
        result = agent.run_sync(f"Subject: {ticket.subject}\n\n{ticket.body}")
        return result.output


def main() -> None:
    router = TicketRouter()

    tickets: list[tuple[str, Ticket]] = [
        (
            "rule hit — billing",
            Ticket(subject="Question about my invoice", body="I was charged twice."),
        ),
        (
            "rule hit — auth",
            Ticket(subject="Can't login", body="I forgot my password."),
        ),
        (
            "rule hit — shipping",
            Ticket(subject="Where is my order?", body="I need the tracking number."),
        ),
        (
            "rule hit — returns",
            Ticket(subject="Return request", body="I want to send this back."),
        ),
        (
            "LLM fallback — billing, no keyword match",
            Ticket(
                subject="Unexpected $9.99 on my statement",
                body="There's an extra deduction on my bank statement this month that I don't recognise.",
            ),
        ),
        (
            "LLM fallback — auth, no keyword match",
            Ticket(
                subject="Locked out",
                body="I can no longer get into my profile, it just says access denied.",
            ),
        ),
    ]

    # Rule hits resolve instantly; LLM calls block their thread but run in
    # parallel — total wall time is the slowest single LLM call, not their sum.
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(router.run, ticket) for _, ticket in tickets]
        results = [f.result() for f in futures]

    print("Ticket routing")
    print("--------------")
    for (label, ticket), team in zip(tickets, results):
        print(f"  [{label}]")
        print(f"    subject : {ticket.subject}")
        print(f"    → {team.value if team else None}")


if __name__ == "__main__":
    main()
