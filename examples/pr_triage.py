from enum import Enum
from typing import Literal

from airules import (
    Default,
    Fact,
    Field,
    KnowledgeEngine,
    ListField,
    NumberField,
    Rule,
    StringField,
)

Author = Literal["member", "contributor", "first_timer"]


class Verdict(Enum):
    BLOCK = "block"
    SECURITY_REVIEW = "security-review"
    AUTO_MERGE = "auto-merge"
    NEEDS_REVIEW = "needs-review"


class PullRequest(Fact):
    """An incoming pull request."""

    title: StringField
    additions: NumberField[int]
    author: Field[Author]
    labels: ListField[str] = ListField(default=None)


class MergeGate(KnowledgeEngine[PullRequest, Verdict]):
    """Decides what to do with a PR.

    The engine's return type is `Verdict`, not `str` — `run()` returns
    `Verdict | None`. Title matching is case-insensitive, so "WIP" and "wip"
    are treated the same.
    """

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
    gate = MergeGate()

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
    }

    print("Merge gate")
    print("----------")
    for label, pr in prs.items():
        verdict = gate.run(pr)
        print(f"  {label:18} -> {verdict.value if verdict else '(undecided)'}")


if __name__ == "__main__":
    main()
