import inspect
from typing import (
    Any,
    ClassVar,
    Generic,
    Literal,
    TypeVar,
    dataclass_transform,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from .fields import MISSING, Field, ListField, NumberField, StringField, _MissingType

F = TypeVar("F", bound="Fact")


def _describe_annotation(annotation: Any) -> dict[str, Any]:
    args = get_args(annotation)
    inner = args[0] if args else annotation
    if get_origin(inner) is Literal:
        return {"type": "Literal", "values": list(get_args(inner))}
    if isinstance(inner, type) and issubclass(inner, Fact):
        return {"type": "Fact", "schema": inner.schema()}
    return {"type": getattr(inner, "__name__", str(inner))}


def _resolve_field_class(annotation: Any) -> type[Field[Any]] | None:
    origin = get_origin(annotation)
    candidate = origin if origin is not None else annotation
    if isinstance(candidate, type) and issubclass(candidate, Field):
        return candidate
    return None


def _is_optional_annotation(annotation: Any) -> bool:
    args = get_args(annotation)
    if not args:
        return False
    return type(None) in get_args(args[0])


def _unwrap_optional(annotation: Any) -> Any:
    """For `Wrapper[T | None]` return `T`; otherwise return the bare inner type."""
    args = get_args(annotation)
    if not args:
        return annotation
    inner = args[0]
    inner_args = get_args(inner)
    if inner_args and type(None) in inner_args:
        non_none = [a for a in inner_args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return inner


class EmbeddedField(Field[F], Generic[F]):
    """Field holding an embedded Fact instance, enabling dotted-path predicates."""

    def __init__(
        self,
        inner_cls: type[F],
        *,
        default: F | None | _MissingType = MISSING,
    ) -> None:
        super().__init__(default=default)
        self._inner_cls = inner_cls

    @overload
    def __get__(self, instance: None, owner: type) -> type[F]: ...
    @overload
    def __get__(self, instance: object, owner: type) -> F: ...
    def __get__(self, instance: object | None, owner: type) -> Any:
        if instance is None:
            return _FactPathProxy(self._name, self._inner_cls)
        return instance.__dict__[self._name]

    def __set__(self, instance: object, value: F | dict[str, Any]) -> None:
        if isinstance(value, dict):
            value = self._inner_cls(**value)
        instance.__dict__[self._name] = value


class _FactPathProxy:
    """Class-access proxy enabling chained predicates over embedded Fact paths."""

    def __init__(self, prefix: str, target_cls: type["Fact"]) -> None:
        self._prefix = prefix
        self._target_cls = target_cls

    def __getattr__(self, name: str) -> Any:
        attr = inspect.getattr_static(self._target_cls, name, None)
        if isinstance(attr, EmbeddedField):
            return _FactPathProxy(f"{self._prefix}.{name}", attr._inner_cls)
        if isinstance(attr, Field):
            return type(attr)._path_cls(f"{self._prefix}.{name}")
        raise AttributeError(f"{self._target_cls.__name__!r} has no field {name!r}")


@dataclass_transform(
    kw_only_default=True,
    field_specifiers=(Field, NumberField, StringField, ListField, EmbeddedField),
)
class Fact:
    _fields: ClassVar[dict[str, Field[Any]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._declare_fields()
        cls._infer_optional_defaults()
        cls._inherit_fields()

    @classmethod
    def _declare_fields(cls) -> None:
        for name, annotation in inspect.get_annotations(cls, eval_str=True).items():
            if name in cls.__dict__:
                continue
            field_cls = _resolve_field_class(annotation)
            if field_cls is EmbeddedField:
                field: Field[Any] = EmbeddedField(_unwrap_optional(annotation))
            elif field_cls is not None:
                field = field_cls()
            elif isinstance(annotation, type) and issubclass(annotation, Fact):
                field = EmbeddedField(annotation)
            else:
                continue
            field.__set_name__(cls, name)
            setattr(cls, name, field)

    @classmethod
    def _infer_optional_defaults(cls) -> None:
        for name, annotation in inspect.get_annotations(cls, eval_str=True).items():
            existing = cls.__dict__.get(name)
            if (
                isinstance(existing, Field)
                and not existing.has_default
                and _is_optional_annotation(annotation)
            ):
                existing._default = None

    @classmethod
    def _inherit_fields(cls) -> None:
        fields: dict[str, Field[Any]] = {}
        for klass in reversed(cls.__mro__):
            for name, attr in vars(klass).items():
                if isinstance(attr, Field):
                    fields[name] = attr
        cls._fields = fields

    def __init__(self, **values: Any) -> None:
        fields = type(self)._fields
        missing = {
            name
            for name in fields
            if name not in values and not fields[name].has_default
        }
        if missing:
            raise TypeError(
                f"{type(self).__name__} missing required fields: {sorted(missing)}"
            )
        unknown = set(values) - set(fields)
        if unknown:
            raise TypeError(
                f"{type(self).__name__} got unexpected fields: {sorted(unknown)}"
            )
        for name, field in fields.items():
            if name in values:
                setattr(self, name, values[name])
            elif field.has_default:
                setattr(self, name, field._default)

    @classmethod
    def schema(cls) -> dict[str, Any]:
        hints = get_type_hints(cls)
        return {
            "name": cls.__name__,
            "fields": {
                name: _describe_annotation(hints.get(name)) for name in cls._fields
            },
        }
