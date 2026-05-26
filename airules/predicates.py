from abc import ABC, abstractmethod
from typing import Any


def _read_path(fact: Any, path: str) -> Any:
    for part in path.split("."):
        if fact is None:
            return None
        fact = getattr(fact, part)
    return fact


class Predicate(ABC):
    @abstractmethod
    def evaluate(self, fact: Any) -> bool: ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]: ...

    def __call__(self, fact: Any) -> bool:
        return self.evaluate(fact)

    def __or__(self, other: "Predicate") -> "Predicate":
        return Or(self, other)

    def __and__(self, other: "Predicate") -> "Predicate":
        return And(self, other)

    def __invert__(self) -> "Predicate":
        return Not(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Predicate":
        kind = data["type"]
        if kind == "Always":
            return Always()
        if kind in _FIELD_OP_CLASSES:
            cls = _FIELD_OP_CLASSES[kind]
            kwargs: dict[str, Any] = {}
            if "case_insensitive" in data:
                kwargs["case_insensitive"] = data["case_insensitive"]
            return cls(data["field"], data["value"], **kwargs)
        if kind == "Or":
            return Or(
                Predicate.from_dict(data["left"]),
                Predicate.from_dict(data["right"]),
            )
        if kind == "And":
            return And(
                Predicate.from_dict(data["left"]),
                Predicate.from_dict(data["right"]),
            )
        if kind == "Not":
            return Not(Predicate.from_dict(data["inner"]))
        raise ValueError(f"Unknown predicate type: {kind}")


class Always(Predicate):
    def evaluate(self, fact: Any) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Always"}


class _FieldOp(Predicate):
    """Base for predicates that read a field and apply an operator against a value.

    An absent field (None anywhere along the dotted path) fails the test by default.
    Subclasses override `_test`; `Eq` overrides `evaluate` because `None == None`
    is a meaningful comparison.
    """

    def __init__(self, field_name: str, value: Any) -> None:
        self.field_name = field_name
        self.value = value

    def evaluate(self, fact: Any) -> bool:
        target = _read_path(fact, self.field_name)
        if target is None:
            return False
        return self._test(target)

    def _test(self, target: Any) -> bool:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": type(self).__name__,
            "field": self.field_name,
            "value": self.value,
        }


class _CaseFoldingOp(_FieldOp):
    """A field op whose string comparison can optionally ignore case.

    The flag is part of the predicate's definition, so it is serialized (when
    set) and restored, keeping Replay faithful. It is emitted only when True so
    existing serialized predicates remain byte-compatible.
    """

    def __init__(
        self, field_name: str, value: Any, *, case_insensitive: bool = False
    ) -> None:
        super().__init__(field_name, value)
        self.case_insensitive = case_insensitive

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        if self.case_insensitive:
            data["case_insensitive"] = True
        return data


class Eq(_CaseFoldingOp):
    def evaluate(self, fact: Any) -> bool:
        target = _read_path(fact, self.field_name)
        if (
            self.case_insensitive
            and isinstance(target, str)
            and isinstance(self.value, str)
        ):
            return target.lower() == self.value.lower()
        return target == self.value


class Gt(_FieldOp):
    def _test(self, target: Any) -> bool:
        return target > self.value


class Ge(_FieldOp):
    def _test(self, target: Any) -> bool:
        return target >= self.value


class Lt(_FieldOp):
    def _test(self, target: Any) -> bool:
        return target < self.value


class Le(_FieldOp):
    def _test(self, target: Any) -> bool:
        return target <= self.value


class _StringOp(_CaseFoldingOp):
    """Base for string-shape predicates that can optionally fold case."""

    def _fold(self, target: str) -> tuple[str, str]:
        if self.case_insensitive:
            return target.lower(), self.value.lower()
        return target, self.value


class Contains(_StringOp):
    """`value in fact.field` — substring (str) or element membership (list/set).

    `case_insensitive` folds case for substring matches only; list/set
    membership is always exact.
    """

    def _test(self, target: Any) -> bool:
        if (
            self.case_insensitive
            and isinstance(target, str)
            and isinstance(self.value, str)
        ):
            return self.value.lower() in target.lower()
        return self.value in target


class StartsWith(_StringOp):
    def _test(self, target: Any) -> bool:
        target, prefix = self._fold(target)
        return target.startswith(prefix)


class EndsWith(_StringOp):
    def _test(self, target: Any) -> bool:
        target, suffix = self._fold(target)
        return target.endswith(suffix)


_FIELD_OP_CLASSES: dict[str, type[_FieldOp]] = {
    cls.__name__: cls for cls in (Eq, Gt, Ge, Lt, Le, Contains, StartsWith, EndsWith)
}


class Or(Predicate):
    def __init__(self, left: Predicate, right: Predicate) -> None:
        self.left = left
        self.right = right

    def evaluate(self, fact: Any) -> bool:
        return self.left.evaluate(fact) or self.right.evaluate(fact)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "Or",
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }


class And(Predicate):
    def __init__(self, left: Predicate, right: Predicate) -> None:
        self.left = left
        self.right = right

    def evaluate(self, fact: Any) -> bool:
        return self.left.evaluate(fact) and self.right.evaluate(fact)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "And",
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }


class Not(Predicate):
    def __init__(self, inner: Predicate) -> None:
        self.inner = inner

    def evaluate(self, fact: Any) -> bool:
        return not self.inner.evaluate(fact)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Not", "inner": self.inner.to_dict()}
