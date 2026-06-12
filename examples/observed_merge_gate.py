"""Inject a logging observer into the merge-gate engine.

The engine has no logging of its own — you inject an ``OutcomeObserver``.
``LoggingObserver`` logs every evaluation, and loudly (WARNING) when a PR falls
through to ``@Default``. Watch "security wrong case": its ``["SECURITY"]`` label
misses the case-sensitive ``security`` rule and falls through, so it's flagged.

Run it:  python examples/observed_merge_gate.py
"""

import logging
from enum import StrEnum
from typing import Literal

from airules import (
    Default,
    Fact,
    Field,
    KnowledgeEngine,
    ListField,
    LoggingObserver,
    NumberField,
    Outcome,
    OutcomeObserver,
    Rule,
    StringField,
)

Author = Literal["member", "contributor", "first_timer"]


class Verdict(StrEnum):
    BLOCK = "block"
    SECURITY_REVIEW = "security-review"
    AUTO_MERGE = "auto-merge"
    NEEDS_REVIEW = "needs-review"


Labels = Literal["security", "dependencies"]


class PullRequest(Fact):
    """An incoming pull request."""

    title: StringField
    additions: NumberField[int]
    author: Field[Author]
    labels: ListField[Labels] = ListField(default=None)


class CountingObserver(OutcomeObserver[PullRequest, Verdict]):
    """A stateful observer: logs via LoggingObserver *and* records every outcome.

    Typed to this engine's Fact/result, so the protocol pins down exactly what
    ``observe`` receives. This is what the old wrapper "service" collapses into —
    categorization and aggregation live in an injected observer, not a layer.
    """

    def __init__(self) -> None:
        self._logging = LoggingObserver()
        self.outcomes: list[Outcome[PullRequest, Verdict]] = []

    def observe(
        self,
        outcome: Outcome[PullRequest, Verdict],
        engine: KnowledgeEngine[PullRequest, Verdict],
    ) -> None:
        self._logging.observe(outcome, engine)
        self.outcomes.append(outcome)


class MergeGate(KnowledgeEngine[PullRequest, Verdict]):
    """Decides what to do with a PR. Title matching is case-insensitive."""

    @Rule(
        PullRequest.title.startswith("wip", case_insensitive=True)
        | PullRequest.title.contains("do not merge", case_insensitive=True)
    )
    def block(self, pr: PullRequest) -> Verdict:
        return Verdict.BLOCK

    @Rule(PullRequest.labels.contains("security"))
    def security(self, pr: PullRequest) -> Verdict:
        # A security label always wins over auto-merge, even for a tiny diff.
        return Verdict.SECURITY_REVIEW

    @Rule(
        PullRequest.author.eq("member")
        & PullRequest.additions.le(50)
        & PullRequest.labels.contains("dependencies")
    )
    def auto_merge(self, pr: PullRequest) -> Verdict:
        return Verdict.AUTO_MERGE

    @Default
    def needs_review(self, pr: PullRequest) -> Verdict:
        return Verdict.NEEDS_REVIEW


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    observer = CountingObserver()
    gate = MergeGate(observer=observer)

    prs: dict[str, PullRequest] = {
        "work in progress": PullRequest(
            title="WIP: refactor auth", additions=120, author="member"
        ),
        "security fix": PullRequest(
            title="Bump lodash to patch CVE",
            additions=8,
            author="member",
            labels=["security", "dependencies"],
        ),
        "routine dep bump": PullRequest(
            title="Bump pytest to 8.2",
            additions=6,
            author="member",
            labels=["dependencies"],
        ),
        "large feature": PullRequest(
            title="Add billing report export", additions=640, author="contributor"
        ),
        "security wrong case": PullRequest(
            title="Bump lodash to patch CVE",
            additions=8,
            author="member",
            labels=["SECURITY"],
        ),
    }

    for _label, pr in prs.items():
        gate.run(pr)  # logging happens inside the engine, every call


if __name__ == "__main__":
    main()
