from typing import Any, ClassVar, Generic, Self, TypeVar, overload

from .predicates import (
    Contains,
    EndsWith,
    Eq,
    Ge,
    Gt,
    Le,
    Lt,
    StartsWith,
)

T = TypeVar("T")
E = TypeVar("E")


class _MissingType:
    """Singleton sentinel for an absent default value."""

    _instance: "_MissingType | None" = None

    def __new__(cls) -> "_MissingType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _MissingType()


class _PredicatePath:
    """A field reference by dotted path; builds predicates over that location."""

    def __init__(self, path: str) -> None:
        self._path = path

    def eq(self, value: Any, *, case_insensitive: bool = False) -> Eq:
        return Eq(self._path, value, case_insensitive=case_insensitive)


class _NumberPath(_PredicatePath):
    def gt(self, value: Any) -> Gt:
        return Gt(self._path, value)

    def ge(self, value: Any) -> Ge:
        return Ge(self._path, value)

    def lt(self, value: Any) -> Lt:
        return Lt(self._path, value)

    def le(self, value: Any) -> Le:
        return Le(self._path, value)


class _StringPath(_PredicatePath):
    def startswith(self, prefix: str, *, case_insensitive: bool = False) -> StartsWith:
        return StartsWith(self._path, prefix, case_insensitive=case_insensitive)

    def endswith(self, suffix: str, *, case_insensitive: bool = False) -> EndsWith:
        return EndsWith(self._path, suffix, case_insensitive=case_insensitive)

    def contains(self, substring: str, *, case_insensitive: bool = False) -> Contains:
        return Contains(self._path, substring, case_insensitive=case_insensitive)


class _ListPath(_PredicatePath):
    def contains(self, element: Any) -> Contains:
        return Contains(self._path, element)


class Field(Generic[T]):
    _name: str
    _default: T | None | _MissingType
    _path_cls: ClassVar[type[_PredicatePath]] = _PredicatePath

    def __init__(self, *, default: T | None | _MissingType = MISSING) -> None:
        self._default = default

    @property
    def has_default(self) -> bool:
        return self._default is not MISSING

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    @overload
    def __get__(self, instance: None, owner: type) -> Self: ...
    @overload
    def __get__(self, instance: object, owner: type) -> T: ...
    def __get__(self, instance: object | None, owner: type) -> "Field[T] | T":
        if instance is None:
            return self
        return instance.__dict__[self._name]

    def __set__(self, instance: object, value: T) -> None:
        instance.__dict__[self._name] = value

    def eq(self, expected: T, *, case_insensitive: bool = False) -> Eq:
        return Eq(self._name, expected, case_insensitive=case_insensitive)


class NumberField(Field[T]):
    _path_cls: ClassVar[type[_PredicatePath]] = _NumberPath

    def gt(self, threshold: T) -> Gt:
        return Gt(self._name, threshold)

    def ge(self, threshold: T) -> Ge:
        return Ge(self._name, threshold)

    def lt(self, threshold: T) -> Lt:
        return Lt(self._name, threshold)

    def le(self, threshold: T) -> Le:
        return Le(self._name, threshold)


class StringField(Field[str]):
    _path_cls: ClassVar[type[_PredicatePath]] = _StringPath

    def startswith(self, prefix: str, *, case_insensitive: bool = False) -> StartsWith:
        return StartsWith(self._name, prefix, case_insensitive=case_insensitive)

    def endswith(self, suffix: str, *, case_insensitive: bool = False) -> EndsWith:
        return EndsWith(self._name, suffix, case_insensitive=case_insensitive)

    def contains(self, substring: str, *, case_insensitive: bool = False) -> Contains:
        return Contains(self._name, substring, case_insensitive=case_insensitive)


class ListField(Field[list[E]], Generic[E]):
    _path_cls: ClassVar[type[_PredicatePath]] = _ListPath

    def contains(self, element: E) -> Contains:
        return Contains(self._name, element)
