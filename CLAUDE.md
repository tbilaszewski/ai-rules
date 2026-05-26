# Project Guidelines

This is a Python application built using **Domain-Driven Design (DDD)**.

## Core Principles

### 1. Domain First, Always
Before implementing any task, **always start by understanding the domain**:
- Identify the **bounded context** the task belongs to
- Clarify the relevant **entities, value objects, aggregates, and domain events**
- Confirm the **invariants** and business rules involved
- Ask the user clarifying questions if the domain model is ambiguous — do not guess
- Only after the domain is clear, propose an implementation

If a task description is purely technical (e.g. "add a field to this class"), still pause to consider: *what does this mean in the domain?* Is the field a value object? Does it belong on this aggregate?

### 2. Ubiquitous Language
- Use the **same terms** in code that the domain experts use
- Class names, function names, variables, modules, and packages must reflect domain vocabulary
- Avoid technical jargon (`Manager`, `Helper`, `Util`, `Data`, `Info`) in domain code — they signal missing domain concepts
- If a concept doesn't have a name yet, **ask the user what to call it** rather than inventing one
- Keep a glossary in this file (see "Glossary" section below) and update it as the language evolves

### 3. Bounded Contexts
- Each bounded context is its own top-level package
- Contexts communicate through **explicit contracts** (domain events, anti-corruption layers), never by reaching into each other's internals
- A term may mean different things in different contexts — that's expected; don't unify prematurely

## Architecture

Package layout, with one-way dependency flow (outer depends on inner, never the reverse):

```
src/
├── domain/          # entities, value objects, aggregates, domain services, domain events
├── application/     # use cases, ports (Protocols/ABCs) — orchestrates the domain
├── infrastructure/  # adapters: persistence, HTTP clients, message brokers (impls of ports)
└── presentation/    # FastAPI/Flask/CLI entry points
```

Rules:
- `domain` has **no dependencies** on other application packages and avoids framework dependencies (no `sqlalchemy`, `pydantic`, `fastapi`, `httpx` imports in domain code)
- `application` depends only on `domain`
- `infrastructure` depends on `application` and `domain` (implements ports)
- `presentation` depends on `application`; it should not import `domain` types directly except where unavoidable (DTOs/Pydantic models are preferred at the edge)

## Modeling Rules of Thumb

- **Make illegal states unrepresentable.** Use value object classes with validation in `__init__` / `__post_init__`, and `Enum` for closed sets of states. A `ValidatedEmail` should only be constructible via a factory/constructor that enforces the rule.
- **Value objects are immutable** and compared by value. Use `@dataclass(frozen=True)` (or Pydantic with `model_config = ConfigDict(frozen=True)`).
- **Entities have identity.** Equality is by ID, not by attributes — override `__eq__` and `__hash__` accordingly.
- **Aggregates enforce invariants.** Mutate aggregate state only through methods on the aggregate root. Use `_private` attributes and expose behavior, not data. No public setters on aggregates.
- **Reference other aggregates by ID, not by direct reference.** This respects aggregate boundaries and keeps loading/persistence simple.
- **Domain events are past-tense facts** (`OrderPlaced`, not `PlaceOrder`). Model them as frozen dataclasses.
- **Repositories return aggregates, not rows.** Define repository interfaces as `Protocol` or `ABC` in the domain/application layer. Mapping between persistence and domain lives in `infrastructure`.
- **Use cases (application services) are thin.** They load aggregates, call domain methods, persist, and emit events. Business logic lives in the domain.
- **Type hints are mandatory** in domain and application layers — they're our primary tool for making the model legible.

## Workflow For Each Task

1. **Restate the task in domain terms.** "You're asking me to add the ability for a `Customer` to `cancel` an `Order` before it has been `Shipped`."
2. **Identify affected bounded context(s) and aggregate(s).**
3. **List the invariants** that must be preserved or added.
4. **Confirm the ubiquitous language** — if a new term appears, ask whether it's the right name and add it to the glossary.
5. **Propose the change at the domain layer first**, then application, then infrastructure/presentation.
6. **Implement** following the architecture rules above.

If at any point the domain feels unclear or contradictory, **stop and ask** rather than picking a plausible-sounding interpretation.

## Glossary

`airules` is a typed, declarative **rules engine**: it evaluates input against a
set of deterministic rules and runs the action of the first matching rule.

### Bounded contexts
- **Rule Authoring** — defining and versioning rules.
- **Decisioning** — evaluating input against the active rule set; produces an `Outcome`.

### Core terms
- **Fact** — the typed input record a rule set evaluates. Fields are declared as typed descriptors that double as predicate builders.
- **Rule** — `Predicate → Action` with a priority. The first matching rule wins.
- **Predicate** — a boolean expression over a Fact's fields, composable with `& | ~` and serializable to/from a dict (`to_dict` / `from_dict`).
- **Action** — what a matched rule does; in the engine, the decorated method's return value.
- **Schema** — the typed shape of a Fact (`Fact.schema()` / `KnowledgeEngine.describe()`), usable to validate predicates statically.
- **Engine** (`KnowledgeEngine`) — collects `@Rule` methods and evaluates an input, returning the matched rule's result.
- **Outcome** — the result of an evaluation: which rule matched and what it returned.

## Anti-Patterns to Avoid

- Anemic domain models (data classes + service classes that mutate them)
- Leaking persistence concerns (DB IDs, ORM models, SQL, SQLAlchemy sessions) into the domain layer
- Smart UI / dumb backend — keep domain logic in the domain package, not in route handlers or view functions
- "Util" or "Helper" modules in the domain layer — they almost always indicate a missing concept
- CRUD-shaped use cases (`create_order`, `update_order`, `delete_order`) when the domain actually has richer verbs (`place_order`, `cancel_order`, `ship_order`)
- Using Pydantic models as domain entities — Pydantic is great for I/O validation at the boundary, but couples the domain to a framework. Prefer plain dataclasses for domain types.
