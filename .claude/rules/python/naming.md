---
paths:
  - "**/*.py"
---

# Naming

## Words

- **Use one word for one concept everywhere.** `fetch` and `retrieve`, or `patient` and `client`, in one codebase make the reader wonder whether they differ.
- **Match a name to the shape of its family, and rename an outlier now.** Two names of one shape for one kind of job make the shape a rule, and a name renamed later lives on as an alias.
- **Name a collection as a plural of its elements, and a mapping `x_by_y`.** `invoice_list` repeats the annotation and `invoice_queue` names the container; `pending_invoices` says what is in it.
- **Put a quantity's unit in its name.** A wrong unit is the one mistake that produces a plausible result; a `timedelta` carries its unit in the type, and a name that follows a standard, like `timeout` in float seconds as the stdlib uses it, needs none.
- **Let the prefix tell the cost and the side effect, and the return type the failure.** `get_` is a cheap lookup, `find_` a search that may find nothing, `fetch_` and `load_` do I/O, `compute_` is CPU work, `save_`, `send_` and `publish_` write; never put I/O behind a `get_` or a property. A store contract keeps its family's verbs: a repository's `get` raises on a missing row and its `find` returns `None`, a cache's `get` returns `None` on a miss.
- **Never name a unit with a generic verb like `process` or `handle`.** It means the unit does not know what it is for.
- **Make two ids of one runtime type each a `NewType`.** Two `str` ids swap silently at a call site and still type-check; a `type` alias names what a shape means.

## The Name Fixes the Abstraction Level

- **Keep only generic logic in a generically named unit.** The name tells a reader which domain words may appear in the body; turn the variation into data, an injected strategy or a separate implementation, and keep the concrete rule in one concretely named place.
- **Never widen a name to hide a leak.** A `MultiChannelNotifier` that branches on the channel still branches.

## Names Are Local

- **Name what the thing is or does, never its history, place, caller or neighbour.** Read the name moved to another package: a history (`merged`) turns false for the next caller, a place (`data_dir`) names one repository's layout, a caller (`for_nightly_job`) breaks for a second one, and a vendor in a schema's name outlives the vendor. Name an implementation for what makes it concrete, like `SlackNotifier` or `PostgresUserRepository`.
