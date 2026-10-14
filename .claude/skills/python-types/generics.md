# Generics, Decorators and Dispatch

## Contents

- Type parameters: PEP 695 on the floor that has it, names, bounds and variance
- Decorators and methods: `ParamSpec`, `@overload`
- Dispatch: `singledispatch` for an open set of types

## Type Parameters

### PEP 695 syntax on a 3.12 floor, a parameter one capital letter; `TypeVar` and `Generic` below it, a `TypeVar` private and suffixed, and neither is a lapse

**Why:** a PEP 695 parameter belongs to its signature, so nothing module-level is declared and
nothing is reused by accident; below 3.12 the syntax does not exist. The same floor decides the
names that came with it — `typing_extensions.override` until 3.12, `typing_extensions.TypeIs` until
3.13 — and a parameter default (PEP 696, `class Catalogue[T = Star]`), which is a syntax error on
3.12 that mypy reports against `python_version`. A project states its floor once, in
`requires-python`, and every one of these choices follows from it rather than being argued per file.
The bound carries the meaning (`[T: Frame]`), so the letter need not — `T`, `K` and `V`, `P` and `R`
for `ParamSpec` and return; only a generic with three or more parameters spells them out. A
`TypeVar` is a module-level name, so it is private and takes the PEP 484 suffix — `_T`, `_KT`,
`_VT`, `_P`, `_R`; where several share a module, the role goes in front of the suffix — `_FrameT`,
`_TargetT` — and variance after it, `_FrameT_co`, which ruff's `PLC0105` checks.

**Example:**
```python
# WRONG — on a 3.12 floor, a module-level TypeVar for one function
FrameT = TypeVar("FrameT", bound=Frame)


def load_frames(frame_type: type[FrameT], blobs: Iterable[bytes]) -> list[FrameT]:
    return [frame_type.from_bytes(blob) for blob in blobs]


# CORRECT — the parameter is declared in the signature that uses it
def load_frames[T: Frame](frame_type: type[T], blobs: Iterable[bytes]) -> list[T]:
    return [frame_type.from_bytes(blob) for blob in blobs]
```

### A type parameter the body relies on is bounded, and a parameter takes a read-only collection

**Why:** an unbounded parameter whose body reads an attribute promises callers more than it can
keep, and the checker says so. `Sequence` and `Mapping` in parameters, concrete types in returns,
handle variance without ever writing `covariant=`: a `list[T]` parameter refuses a tuple and a
`list` of a subtype.

## Decorators and Methods

### A decorator keeps the signature it wraps, through `ParamSpec`

**Why:** a decorator returning `Callable[..., Any]` erases the parameters and the return type of
every function it touches, and no call through it is checked again. `Concatenate[Telescope, P]`
types one that supplies the first argument itself.

**Example:**
```python
# WRONG — every decorated function now accepts anything and returns Any
def reduction_step(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.debug("reduction step starts", extra={"step": func.__qualname__})
        return func(*args, **kwargs)

    return wrapper


# CORRECT — the wrapper has exactly the parameters and the return of what it wraps
def reduction_step[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logger.debug("reduction step starts", extra={"step": func.__qualname__})
        return func(*args, **kwargs)

    return wrapper
```

### `@overload` is for one function with several signatures, never for two functions

**Why:** overloads selected by a `Literal[True]` flag are two behaviours behind one name with extra
syntax (`functions.md`); the honest form is two functions. An overload earns its place when one
behaviour has return types that depend on the arguments — a lookup that returns `V | None`, or `V`
once a default is passed.

**Example:**
```python
# WRONG — a flag picks the behaviour, and overloads dress it up
@overload
def read_observing_log(path: Path, *, as_text: Literal[True]) -> str: ...
@overload
def read_observing_log(path: Path, *, as_text: Literal[False]) -> bytes: ...
def read_observing_log(path: Path, *, as_text: bool) -> str | bytes:
    return path.read_text(encoding="utf-8") if as_text else path.read_bytes()


# CORRECT — two behaviours, two names
def read_observing_log_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_observing_log_bytes(path: Path) -> bytes:
    return path.read_bytes()
```

## Dispatch

### Behaviour that varies by an argument's type over an open set is `singledispatch`

**Why:** an `isinstance` ladder over an open hierarchy is edited for every new kind, by whoever adds
it; a registered implementation sits beside its kind. For a closed set, `match` on a tagged union
(`SKILL.md`) is exhaustive where dispatch cannot be.

**Example:**
```python
# WRONG — every new kind of body edits this function
def catalogue_label(body: CelestialBody) -> str:
    if isinstance(body, Star):
        return f"{body.designation} ({body.spectral_class})"
    if isinstance(body, Galaxy):
        return f"{body.designation}, Hubble type {body.morphology}"
    raise UnsupportedBodyError(type(body).__name__)


# CORRECT — each kind registers its own label
@singledispatch
def catalogue_label(body: CelestialBody) -> str:
    raise UnsupportedBodyError(type(body).__name__)


@catalogue_label.register
def _(body: Star) -> str:
    return f"{body.designation} ({body.spectral_class})"


@catalogue_label.register
def _(body: Galaxy) -> str:
    return f"{body.designation}, Hubble type {body.morphology}"
```
