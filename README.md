# airules

A small, typed, declarative **rules engine** for Python.

You describe the shape of your input as a `Fact`, write rules as predicates over
that fact, and let the `KnowledgeEngine` pick the first matching rule and run
its action. Predicates are plain Python objects — they can be composed with
`& | ~`, serialized to dictionaries, and reloaded — which makes the rule set
easy to store, audit, and visualize.

The library is **fully typed**: every public API carries type hints, the
engine is `Generic[FactType, ReturnType]`, field accessors and predicates
preserve element types end-to-end, and the project is checked under `pyright`
in strict-friendly mode. Your editor and type checker will catch a misspelled
field name, a wrong comparison type, or a mismatched return value before you
ever run the engine.

> Status: experimental (0.0.1). The API is small and stable in spirit, but
> details may still change.

## Why

Most "if/elif" decision code in production systems is really a rule set in
disguise: a list of conditions, each with an associated action, evaluated in
priority order. Once that list grows past a handful of branches it gets hard
to read, test, and reason about.

This library gives that pattern first-class structure:

- **Facts** describe the input schema once, with types.
- **Predicates** are reusable, composable, introspectable expressions over a
  fact's fields.
- **Rules** are decorated methods on a `KnowledgeEngine`; the engine picks the
  first one whose predicate matches.
- **`describe()`** dumps the whole rule set as a dict — useful for docs,
  diffing, or feeding into an external UI.

## Install

The project uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Python 3.11+ is required. The only runtime dependency is `typing_extensions`.

## A minimal example

```python
from airules import Fact, KnowledgeEngine, NumberField, Rule, Default

class Order(Fact):
    total: NumberField[int]

class Discount(KnowledgeEngine[Order, str]):
    @Rule(Order.total.ge(100))
    def big(self):
        return "10% off"

    @Default
    def small(self):
        return "no discount"

Discount().run(Order(total=120))   # -> "10% off"
Discount().run(Order(total=20))    # -> "no discount"
```

The engine is `Generic[FactType, ReturnType]`, so your editor and type checker
know that `run` returns `str | None` here.

## Facts and fields

A `Fact` is a typed record. Annotate its attributes with one of the field
types and the metaclass machinery wires up storage, defaults, validation, and
predicate builders.

```python
from typing import Literal
from airules import Fact, Field, ListField, NumberField, StringField

Color = Literal["green", "red", "yellow"]

class Light(Fact):
    color: Field[Color]
    remaining_time: NumberField[int]

class User(Fact):
    name: StringField
    tags: ListField[str] = ListField(default=None)
```

- `Field[T]` — generic field; exposes `.eq(...)`.
- `NumberField[T]` — adds `.gt / .ge / .lt / .le`.
- `StringField` — adds `.startswith / .endswith / .contains`.
- `ListField[E]` — adds `.contains(element)`.

The string comparisons (`.eq`, `.startswith`, `.endswith`, `.contains`) accept
a keyword-only `case_insensitive=True` to fold case (see
[Case-insensitive matching](#case-insensitive-matching)).

Fields without an explicit default are required at construction time; passing
unknown fields raises `TypeError`. `Optional[...]` annotations are inferred as
having a default of `None`.

### Embedded facts (dotted paths)

A `Fact` can hold another `Fact` and you can build predicates over nested
fields with the same syntax you'd use at the top level:

```python
from airules import EmbeddedField, Fact, NumberField, StringField

class Sensor(Fact):
    temperature: NumberField[int] = NumberField(default=0)

class Car(Fact):
    plate: StringField
    sensor: EmbeddedField[Sensor] = EmbeddedField(Sensor, default=None)

Car.sensor.temperature.ge(10)   # predicate over the path "sensor.temperature"
```

If any segment along the path is `None`, the predicate evaluates to `False`
(the `Eq` predicate is the one exception — it compares `None == value`
honestly, so `field.eq(None)` works).

## Predicates

Predicates are first-class objects:

```python
from airules import Predicate

p = Light.color.eq("yellow") & Light.remaining_time.gt(5)

p.evaluate(Light(color="yellow", remaining_time=10))   # True
p(Light(color="yellow", remaining_time=2))             # False — same thing

# Compose with &, |, ~
either = Light.color.eq("red") | Light.color.eq("yellow")
not_green = ~Light.color.eq("green")

# Serialize / deserialize
data = p.to_dict()
restored = Predicate.from_dict(data)
```

Available operators: `Eq`, `Gt`, `Ge`, `Lt`, `Le`, `Contains`, `StartsWith`,
`EndsWith`, plus boolean combinators `And`, `Or`, `Not`, and the trivial
`Always`.

### Case-insensitive matching

`eq`, `startswith`, `endswith`, and `contains` take an opt-in, keyword-only
`case_insensitive` flag (default `False`):

```python
User.name.eq("alice", case_insensitive=True)         # matches "Alice", "ALICE"
User.name.startswith("dr.", case_insensitive=True)    # matches "Dr. Strange"
User.name.contains("smith", case_insensitive=True)    # matches "John SMITH"
```

The fold applies only to string comparisons:

- `eq` ignores case only when **both** the field value and the expected value
  are strings; otherwise it compares exactly (numbers, `None`, enums are
  unaffected).
- `contains` folds case for **substring** matches only — list/set membership
  stays exact, so `tags.contains("urgent", case_insensitive=True)` still
  requires an exact element.

The flag is part of the predicate's definition, so it survives
`to_dict()` / `from_dict()`. It is written to the dict only when `True`, so
predicates serialized before this flag existed load unchanged.

## The engine

A `KnowledgeEngine` collects `@Rule(...)` methods on the class and evaluates
them top-to-bottom against an input fact. The **first** matching rule wins; its
method is called and its return value is returned from `run(...)`.

```python
from airules import KnowledgeEngine, Rule, Default

class TrafficAdvice(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def green(self):
        return "go"

    @Rule(Light.color.eq("yellow") & Light.remaining_time.gt(5))
    def yellow_safe(self):
        return "still time"

    @Rule(Light.color.eq("yellow") | Light.color.eq("red"))
    def stop(self):
        return "stop"

    @Default
    def fallback(self):
        return "unknown signal"
```

### Priority

Rules are ordered by an explicit `priority=` argument when provided, otherwise
by declaration order (earlier declarations win). `@Default`-decorated methods
are always tried last, after every regular rule has failed, regardless of
declaration order.

```python
@Rule(some_predicate, priority=100)   # checked before priority=10
def high_priority(self): ...
```

If no rule matches and there is no `@Default`, `run` returns `None`.

### Union fact types

The engine type parameter accepts a union, which is useful when several fact
shapes can be fed to the same rule set:

```python
class MyEngine(KnowledgeEngine[Light | Car, str]):
    ...
```

## Introspection

`describe()` dumps the active rule set and the fact schemas as plain data:

```python
TrafficAdvice.describe()
# {
#   "facts": [{"name": "Light", "fields": {...}}],
#   "rules": [
#     {"name": "green", "predicate": {"type": "Eq", "field": "color", "value": "green"},
#      "priority": 3, "is_default": False},
#     ...
#   ],
# }
```

This is the canonical way to render a rule set in an external tool, diff two
versions, or persist them to a store. Combined with `Predicate.from_dict`,
predicates round-trip cleanly.

## A larger example

See [`examples/traffic_lights.py`](./examples/traffic_lights.py) for an
end-to-end example — a pedestrian-crossing advisor that combines an embedded
fact, a list field, optional/None-tolerant fields, boolean composition,
priority ordering, and a `@Default`.

## Project layout

```
airules/
├── facts.py         # Fact base class, EmbeddedField, path proxy
├── fields.py        # Field, NumberField, StringField, ListField
├── predicates.py    # Predicate algebra (Eq, Gt, And, Or, Not, ...)
├── rules.py         # @Rule / @Default decorators
└── engine.py        # KnowledgeEngine
```

## Development

```bash
uv sync
uv run pytest          # tests
uv run ruff check .    # lint
uv run pyright         # type-check
```

## License

TBD.
