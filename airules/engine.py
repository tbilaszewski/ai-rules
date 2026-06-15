import inspect
from dataclasses import dataclass
from types import UnionType
from typing import (
    Any,
    ClassVar,
    Generic,
    Protocol,
    Union,
    get_args,
    get_origin,
    runtime_checkable,
)

from typing_extensions import TypeVar

from .facts import Fact
from .rules import RuleEntry, RuleSpec

T = TypeVar("T", bound=Fact)
R = TypeVar("R", default=Any)


@dataclass(frozen=True)
class Outcome(Generic[T, R]):
    """The result of evaluating a Fact: which rule matched and what it returned.

    `rule` is the matched ``RuleEntry``, or ``None`` when no rule (not even a
    default) matched. ``result`` is that rule's return value, or ``None`` when
    nothing matched. Use the helpers below rather than reaching into ``rule``.
    """

    fact: T
    rule: RuleEntry | None
    result: R | None

    @property
    def matched(self) -> bool:
        """Whether any rule fired (default rules count as a match)."""
        return self.rule is not None

    @property
    def is_default(self) -> bool:
        """Whether the rule that fired was a ``@Default`` fall-through."""
        return self.rule is not None and self.rule.is_default

    @property
    def rule_name(self) -> str | None:
        """Name of the matched rule's method, or ``None`` if nothing matched."""
        return self.rule.method.__name__ if self.rule is not None else None


@runtime_checkable
class OutcomeObserver(Protocol[T, R]):
    """A port notified of every evaluation. Inject one to observe Decisioning.

    Generic over the Fact type ``T`` and result type ``R`` so an observer can be
    typed to the engine it watches — ``OutcomeObserver[Order, Verdict]`` — or
    left general with ``OutcomeObserver[Any, Any]`` to watch any engine.

    Implementations decide what to do with each ``Outcome`` — log it, count
    fall-throughs, aggregate insights. The engine stays free of those concerns;
    it only calls :meth:`observe`, handing over the ``Outcome`` together with the
    ``engine`` that produced it (so observers can reach ``engine.describe()``,
    its rules, etc. without being constructed against a specific instance).
    """

    def observe(
        self, outcome: "Outcome[T, R]", engine: "KnowledgeEngine[T, R]"
    ) -> None: ...


class KnowledgeEngine(Generic[T, R]):
    rules: ClassVar[list[RuleEntry]]
    _observer: "OutcomeObserver[T, R] | None" = None

    def __init__(self, observer: "OutcomeObserver[T, R] | None" = None) -> None:
        if observer is not None:
            self._observer = observer

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        specs = [a for a in vars(cls).values() if isinstance(a, RuleSpec)]
        regular = [s for s in specs if not s.is_default]
        auto_priority = {id(s): len(regular) - i for i, s in enumerate(regular)}
        entries = [
            RuleEntry(
                predicate=s.predicate,
                method=s.method,
                priority=s.priority
                if s.priority is not None
                else auto_priority.get(id(s), 0),
                is_default=s.is_default,
            )
            for s in specs
        ]
        cls.rules = sorted(entries, key=lambda e: (e.is_default, -e.priority))

    def evaluate(self, value: T) -> "Outcome[T, R]":
        """Evaluate ``value`` and return the full ``Outcome``.

        Unlike :meth:`run`, this preserves *which* rule matched, so callers can
        distinguish a deliberate result from a ``@Default`` fall-through or no
        match at all.
        """
        outcome: Outcome[T, R] = Outcome(fact=value, rule=None, result=None)
        for entry in self.rules:
            if entry.predicate(value):
                outcome = Outcome(
                    fact=value, rule=entry, result=entry.method(self, value)
                )
                break
        if self._observer is not None:
            self._observer.observe(outcome, self)
        return outcome

    def run(self, value: T) -> "R | None":
        return self.evaluate(value).result

    async def evaluate_async(self, value: T) -> "Outcome[T, R]":
        """Async variant of :meth:`evaluate` — awaits rule methods that are coroutines."""
        outcome: Outcome[T, R] = Outcome(fact=value, rule=None, result=None)
        for entry in self.rules:
            if entry.predicate(value):
                result = entry.method(self, value)
                if inspect.isawaitable(result):
                    result = await result
                outcome = Outcome(fact=value, rule=entry, result=result)
                break
        if self._observer is not None:
            self._observer.observe(outcome, self)
        return outcome

    async def run_async(self, value: T) -> "R | None":
        """Async variant of :meth:`run` — awaits rule methods that are coroutines."""
        return (await self.evaluate_async(value)).result

    @classmethod
    def _fact_types(cls) -> tuple[type[Fact], ...]:
        for base in getattr(cls, "__orig_bases__", ()):
            if get_origin(base) is KnowledgeEngine:
                param = get_args(base)[0]
                if get_origin(param) in (Union, UnionType):
                    return get_args(param)
                return (param,)
        return ()

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "facts": [ft.schema() for ft in cls._fact_types()],
            "rules": [
                {
                    "name": entry.method.__name__,
                    "predicate": entry.predicate.to_dict(),
                    "priority": entry.priority,
                    "is_default": entry.is_default,
                }
                for entry in cls.rules
            ],
        }
