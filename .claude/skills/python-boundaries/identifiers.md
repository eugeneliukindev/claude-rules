# Identifiers

### A public identifier is random and opaque

**Why:** a sequential public id invites enumeration — whoever holds sailing 1042 asks for 1041 —
and a `random`-derived one is predictable. `uuid.uuid4()` for opaque ids; `uuid.uuid7()` (stdlib
from 3.14) when ids must sort by creation time for index locality; either is wrapped in its own
`NewType` (`naming.md`). An opaque id makes guessing harder; it never replaces the check that the
caller owns the resource.
