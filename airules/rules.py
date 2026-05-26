from typing import Any, Callable, Generic, NamedTuple, TypeVar, overload

from .predicates import Always, Predicate

F = TypeVar("F", bound=Callable[..., Any])


class RuleSpec(Generic[F]):
    def __init__(
        self,
        method: F,
        predicate: Predicate,
        priority: int | None = None,
        is_default: bool = False,
    ) -> None:
        self.method: F = method
        self.predicate = predicate
        self.priority = priority
        self.is_default = is_default

    @overload
    def __get__(self, instance: None, owner: type) -> "RuleSpec[F]": ...
    @overload
    def __get__(self, instance: object, owner: type) -> Callable[..., Any]: ...
    def __get__(self, instance: object | None, owner: type) -> Any:
        if instance is None:
            return self
        return self.method.__get__(instance, owner)


class RuleEntry(NamedTuple):
    predicate: Predicate
    method: Callable[..., Any]
    priority: int
    is_default: bool = False


def Rule(
    predicate: Predicate, priority: int | None = None
) -> Callable[[F], RuleSpec[F]]:
    def inner(fn: F) -> RuleSpec[F]:
        return RuleSpec(method=fn, predicate=predicate, priority=priority)

    return inner


def Default(fn: F) -> RuleSpec[F]:
    return RuleSpec(method=fn, predicate=Always(), is_default=True)
