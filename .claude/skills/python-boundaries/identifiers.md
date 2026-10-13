# Identifiers

### A public identifier is random and opaque, wrapped in a `NewType`

**Why:** a sequential public id invites enumeration — whoever holds invoice 1042 asks for 1041 —
and a `random`-derived one is predictable. `uuid.uuid4()` for opaque ids; `uuid.uuid7()` (stdlib
from 3.14) when ids must sort by creation time for index locality. An opaque id makes guessing
harder; it does not replace the check that the caller owns the resource (`python-auth`).
