---
paths:
  - "**/*.py"
---

# Python - Types and Data

## Choosing a Representation

- **Give every value its narrowest honest type, except an override's parameter, which keeps its parent's type.** A wider type is a runtime check owed later, where nobody writes it; `Any` stops checking at the first subscript, where `Json` keeps every level a union to narrow.

| Instead of | Use |
|---|---|
| `dict[str, Any]` inbound | a validating boundary model |
| `dict` keyed by data | `Mapping[TargetId, Exposure]` |
| `Any` for free-form JSON | `type Json = str \| int \| float \| bool \| None \| list[Json] \| dict[str, Json]` |
| `tuple[Any, ...]` | a frozen dataclass, never `NamedTuple` |
| several `bool` fields | one `Enum` state |

- **Name a type the reader must decode, in the simplest shape that names its parts.** A nested type spelled at five call sites drifts. Take the first shape that fits: a pair keyed by its first part is a `Mapping`, an unordered set a `frozenset`, a nested generic a `type` alias named for what it holds, and only a record of three or more parts that mean different things a frozen dataclass; a tuple whose order is the concept, like `(x, y)`, stays a tuple.
- **Type a parameter with the narrowest `collections.abc` type, and a return concretely.** `Mapping` in accepts every mapping, `dict` out tells the caller what it can do: iterate once, `Iterable`; index, `Sequence`; membership, `Set`; mutate, `MutableMapping`; a stream, `typing.IO[bytes]`.
- **Hide a return's container only on purpose.** An `Iterator` from a generator says "read once", where `Iterable` invites a second loop that sees nothing.
- **Type a read-only field as a `Sequence` or a `Mapping` too, and write a contract of your own only when no ABC names the capability.**
- **Never mutate an argument, and return a result instead of writing into a parameter.** The caller's object changes under it; a function whose job is the mutation is named for it and takes a `MutableSequence`.
- **Never hand out internal state.** Keep what is fixed as a `tuple`, a `frozenset` or a `MappingProxyType`, copied in and handed out as such.

## Dataclasses and Value Objects

- **Default to `@dataclass(frozen=True, slots=True, kw_only=True)`.** `kw_only` is the one forgotten: positional, two ids of one type swap and it type-checks. Construct positionally only where the order is the concept, like `Point(x, y)`, and make it mutable only for a genuine aggregate root that says so in its name, like `Cart`, with copies through `replace()`.
- **Make a primitive with rules a frozen value object, valid by construction.** A rule checked at the call sites is checked at some of them; validate in `__post_init__` with the package's own error, and never re-validate it after.
- **Keep a value with no rules a plain `str`, `int` or `Decimal`, and an identity-only value a `NewType`.** A `type` alias accepts any `str`; a `NewType` that grows a rule becomes a value object everywhere.
- **Make a value object compare by value, hash, and carry no I/O.**
- **Carry the unit of a quantity that crosses a signature in its type as well as its name.** With plain floats, degrees pass where radians are expected; arithmetic on a `NewType` returns the base type, so the check holds at signatures only, and the name keeps the unit too (`naming.md`).
- **Keep secrets out of `repr` with `field(repr=False)`, and ids and timestamps out of equality with `field(compare=False)`.** The generated `repr` prints a secret into the first log line that formats the object, and an `issued_at` in `__eq__` makes two copies of one credential unequal; define `__hash__` beside a hand-written `__eq__`, or the first use as a set member raises `TypeError`.

## Dict Shapes and Constraints

- **Type dict-shaped data that stays a dict as a `TypedDict`, and turn it into a domain object where it enters.** A JSON payload you don't own, a `**kwargs` bundle or a file read back gets named keys at no runtime cost, and a file mostly counted is not worth converting row by row; never make a `TypedDict` a domain type.
- **Mark keys `NotRequired[...]` or `Required[...]`, never `total=False`.** Mark keys consumers must not change `ReadOnly[...]`, and type a forwarded `**kwargs` with `Unpack[...]`.
- **Express a constraint the type cannot hold as an `Annotated` alias, named once.** Bounds or a pattern are read at runtime by whatever validates the boundary; the same bounds in five models are five places to get one wrong, and a bound restated in a service body means the boundary leaked.

## Closed Sets

- **Type a closed set as a `Literal` in one or two signatures, and as an `Enum` once reused.** The checker rejects a wrong value at the call site, where a `str` raises at runtime; promote at three users, or earlier for behaviour or a wire value that may diverge, and a `StrEnum` serializes as its value.
- **Make a string used twice a constant, and compare a member to a member.** A repeated literal drifts into two spellings, and a comparison with a raw literal turns silently false once the value is renamed; a `Final` constant still passes where the `Literal` is expected.
- **Give each state its own variant when a field belongs to one state.** A status beside optional fields lets impossible combinations exist; narrow a variant with a class pattern in `match`, closed with `assert_never` (`control-flow.md`), and a union of `TypedDict`s on a `Literal` field.
- **Return a batch whose normal output mixes successes and failures as a union of variants, never a generic `Result` wrapper.** Any other failure is an exception.
- **Mark absence with a one-member `Enum` sentinel when `None` is a legal value.** In a PATCH-style update `None` cannot tell "not provided" from "cleared"; make a public `NotGiven` enum with a `NOT_GIVEN: Final` alias for its member, since `is NOT_GIVEN` narrows an enum member in every branch and a plain-class instance only in the `if`.

## Narrowing

- **Check with `isinstance` or a `TypeIs` predicate, and keep `cast()` only with a one-line reason the checker cannot see.** A `cast` checks nothing, so a wrong claim fails far from where it was made.
- **Turn a narrowing needed twice into a `TypeIs` predicate, named like any boolean.** `TypeIs` is in `typing` from 3.13, and in `typing_extensions` below.
- **Ask the ABC at runtime, never `hasattr`, a concrete type or a runtime-checkable `Protocol`.** A concrete type refuses a `MappingProxyType`, `hasattr` accepts anything with that one attribute, and a `Protocol` check compares names, not signatures; guard `str` or `bytes` first, since both are sequences.

## Classes, Generics and Callables

- **Put `@override` on every override, `@final` where subclassing is not meant, `Final` on constants, and `-> Never` on a function that always raises.** `@override` turns a renamed parent method into an error instead of an orphan, `@final` on an implementation of a contract or an exported class keeps subclasses out, and `Final` rejects reassignment and infers the literal type.
- **Declare a type parameter in the signature that uses it, and bound it when the body relies on it.** A module-level `TypeVar` is shared by accident, and an unbounded parameter whose body reads an attribute promises more than it keeps.
- **Let `requires-python` decide the spelling.** `typing_extensions.override` below 3.12, `TypeIs` below 3.13, a type parameter default from 3.13; below 3.12, `TypeVar` and `Generic` are no lapse.
- **Name a type parameter for its meaning: `T`, `K` and `V`, `P` and `R`, spelled out at three or more.** Name a `TypeVar` with an underscore and its variance, like `_T` or `_FrameT_co`.
- **Keep the wrapped signature through a decorator with `ParamSpec`.** `Callable[..., Any]` erases the parameters and return type of every function it touches; type one that supplies the first argument itself with `Concatenate`.
- **Type a callable with two or more parameters, or any keyword, as a calling protocol.** A list of types names no argument and cannot express a keyword; one parameter and an obvious return stay a `Callable`.
