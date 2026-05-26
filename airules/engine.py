from types import UnionType
from typing import (
    Any,
    ClassVar,
    Generic,
    Union,
    get_args,
    get_origin,
)

from typing_extensions import TypeVar

from .facts import Fact
from .rules import RuleEntry, RuleSpec

T = TypeVar("T", bound=Fact)
R = TypeVar("R", default=Any)


class KnowledgeEngine(Generic[T, R]):
    rules: ClassVar[list[RuleEntry]]

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

    def run(self, value: T) -> R | None:
        for entry in self.rules:
            if entry.predicate(value):
                return entry.method(self, value)
        return None

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
