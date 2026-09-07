---
paths:
  - "**/*.py"
---

# Standard Library First

Supplement to `core.md`. Consult it before adding a third-party dependency.

## Standard Library First

**MUST** prefer stdlib modules over manual re-implementations. Before writing custom logic, check whether a stdlib module already provides it. Third-party packages are only justified when the stdlib has a genuine gap.

### `string`

```python
import string

# WRONG
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"

# CORRECT
string.ascii_letters   # 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
string.digits          # '0123456789'
string.punctuation     # '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
string.whitespace      # ' \t\n\r\x0b\x0c'
```

### `operator`

Use `operator` functions instead of `lambda` wrappers for readability and performance.

```python
import operator
from functools import reduce

# WRONG
total = reduce(lambda a, b: a + b, values)
pairs.sort(key=lambda x: x[1])

# CORRECT
total = reduce(operator.add, values)
pairs.sort(key=operator.itemgetter(1))

# Other common uses
operator.attrgetter("name")          # replaces lambda x: x.name
operator.methodcaller("strip", "/")  # replaces lambda x: x.strip("/")
```

### `functools`

```python
import math
from functools import cached_property, lru_cache, partial, reduce, total_ordering

# lru_cache — memoize a pure function of hashable arguments, always with an explicit maxsize
@lru_cache(maxsize=1024)
def fibonacci(n: int) -> int:
    return n if n < 2 else fibonacci(n - 1) + fibonacci(n - 2)

# cached_property — compute once per instance, then store
class Circle:
    def __init__(self, radius: float) -> None:
        self.radius = radius

    @cached_property
    def area(self) -> float:
        return math.pi * self.radius ** 2

# partial — fix arguments without a lambda
sort_by_price = partial(sorted, key=operator.attrgetter("price"))

# total_ordering — define __eq__ + one comparison, get the rest for free
@total_ordering
class Version:
    def __eq__(self, other: object) -> bool: ...
    def __lt__(self, other: object) -> bool: ...
```

### `itertools`

```python
import itertools

# chain — flatten one level of nesting
flat = list(itertools.chain([1, 2], [3, 4], [5]))          # [1, 2, 3, 4, 5]

# chain.from_iterable — flatten an iterable of iterables
flat = list(itertools.chain.from_iterable([[1, 2], [3, 4]])) # [1, 2, 3, 4]

# islice — lazy slice of any iterator (no materializing the whole sequence)
first_ten = list(itertools.islice(big_generator(), 10))

# groupby — consecutive runs sharing a key (sort first!)
rows.sort(key=operator.attrgetter("department"))
for department, members in itertools.groupby(rows, key=operator.attrgetter("department")):
    aggregate_department(department, list(members))

# batched (Python >= 3.12) — chunk an iterable into fixed-size tuples
for batch in itertools.batched(records, 100):
    insert_batch(batch)

# combinations / permutations / product
pairs = list(itertools.combinations(candidates, 2))
grid = list(itertools.product(range(3), range(3)))

# takewhile / dropwhile
positives = list(itertools.takewhile(is_positive, values))
```

### `collections`

```python
from collections import Counter, defaultdict, deque

# Counter — frequency map in one call
word_counts = Counter(words)
most_frequent = word_counts.most_common(5)

# defaultdict — no KeyError on first access
neighbours_by_node: defaultdict[str, list[str]] = defaultdict(list)
neighbours_by_node["a"].append("b")

# deque — O(1) appends and pops from both ends
pending: deque[int] = deque(maxlen=1000)
pending.appendleft(item)
pending.pop()

# Records are frozen dataclasses, never namedtuple — see Immutability and Data (typing.md)
```

### `contextlib`

```python
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress

# contextmanager — turn a generator into a context manager
@contextmanager
def acquired_lock(path: Path) -> Iterator[Path]:
    path.touch(exist_ok=False)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)

# suppress — silence specific exceptions instead of try/except/pass
with suppress(FileNotFoundError):
    Path("temp.txt").unlink()

# asynccontextmanager — async variant
@asynccontextmanager
async def managed_connection(url: str) -> AsyncIterator[Connection]:
    connection = await connect(url)
    try:
        yield connection
    finally:
        await connection.aclose()
```

### `pathlib`

**MUST** use `pathlib.Path` for all filesystem operations. Never use `os.path`, `open(str)`, or string concatenation for paths.

```python
from pathlib import Path

config = Path("config") / "settings.toml"     # CORRECT path joining
text = config.read_text(encoding="utf-8")     # CORRECT file reading
config.write_text(content, encoding="utf-8")

# Glob, existence, mkdir
for csv_file in Path("data").glob("**/*.csv"):
    process(csv_file)

output = Path("output")
output.mkdir(parents=True, exist_ok=True)
```

- `dataclasses` usage is specified in Immutability and Data (typing.md).
