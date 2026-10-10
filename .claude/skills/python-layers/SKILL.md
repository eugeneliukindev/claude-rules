---
name: python-layers
description: >-
  Python layer boundaries enforced by import-linter: layers contracts per package with an internal
  order, peers declared on one line, independence contracts for the implementations behind one
  contract, forbidden contracts keeping an optional dependency in its own module, banned APIs at the
  linter, and fixing a violation by moving code rather than allowlisting it. Use when adding an
  import-linter contract, arguing about which layer code belongs to, or when a domain module imports
  a framework, a driver or a sibling implementation.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Layers

**Dependency direction is enforced by tooling, not by review vigilance.** Contracts live next to
the type-checker configuration and run beside it. Three kinds do the work, and most codebases stop
after the first:

**`layers` — what may depend on what.** Higher layers depend on lower ones; the domain depends on
nothing in the package.

- **One contract per package that has an order, not one for the repository.** A top-level contract
  says how the application is stacked; a subpackage with its own internal order gets its own
  contract, and the two are checked independently. Without that, everything below the top layer is
  a free-for-all the moment it has more than three modules.
- **Peers are declared, not silently allowed.** Two modules at the same height that must not import
  each other are written on one line — `headers | cookies`, `renderer | stream`. Leaving them on
  separate lines invents an order nobody meant and that the next edit will violate for no reason.

```ini
# WRONG — three lines are three heights: headers may now import cookies, and nothing objects
[importlinter:contract:http-layers]
name = HTTP client layers
type = layers
containers =
  myapp.http
layers =
  client
  headers
  cookies

# CORRECT — peers on one line: both sit below client, and neither may import the other
[importlinter:contract:http-layers]
name = HTTP client layers
type = layers
containers =
  myapp.http
layers =
  client
  headers | cookies
```

**`independence` — siblings behind a contract do not know each other.** This is the check that
makes "adding the tenth costs what the second cost" true instead of aspirational: every
implementation of a contract, every plugin, every handler in a registry is independent of the rest,
and the *only* permitted edge among them is to their shared base.

```ini
[importlinter:contract:notifier-independence]
name = Notifier implementations must not know about each other
type = independence
modules =
  myapp.notifications.*
ignore_imports =
  # The one edge that is allowed: every implementation inherits the contract.
  myapp.notifications.* -> myapp.notifications.base
```

Without it, one implementation imports a helper from its sibling, and the eleventh is no longer a
new file — it is a new file plus an edit to whichever sibling it borrowed from.

**`forbidden` — a dependency that must not appear where it is not wanted.** The rule that an
optional library lives only in its own implementation module (the `python-packaging` skill) is
stated in prose everywhere and checked almost nowhere. Ban the library from the whole package
and list every permitted edge; the exception list then *is* the inventory of where the extra is
allowed, and it is reviewed whenever it grows.

```ini
[importlinter:contract:no-optional-deps]
name = Optional dependencies live only in their own implementation
type = forbidden
source_modules =
  myapp
forbidden_modules =
  redis
  boto3
ignore_imports =
  # Extra `s3`: the object-storage adapter is the one module that may use its SDK.
  myapp.storage.s3 -> boto3
  # Extra `redis`: the cache adapter is the one module that speaks the protocol.
  myapp.cache.redis -> redis
```

- A boundary violation is fixed by moving code or inverting the dependency — a contract plus an
  adapter — **never** by adding the module to an allowlist. A contract exception needs the same
  justification as a type suppression, and carries its reason on the line above it.

```python
# WRONG — invoicing imports the SMTP implementation, and the contract needs an exception to pass
from myapp.notifications.smtp import SmtpNotifier

def issue_invoice(notifier: SmtpNotifier, invoice: Invoice) -> None: ...

# CORRECT — invoicing depends on the contract; the composition root passes the SMTP one in
from myapp.notifications.base import Notifier

def issue_invoice(notifier: Notifier, invoice: Invoice) -> None: ...
```

- **Domain code imports the standard library and other domain modules only.** Frameworks, drivers
  and clients enter through adapters.
- Ban the APIs that must never be used directly at the linter level too, with a message naming the
  replacement — `flake8-tidy-imports.banned-api` states the substitution where the import happens,
  which a contract cannot.

How directories are named and nested is a project decision, not a general rule: it follows the
domain, the team and the deployment shape, and a layout copied from elsewhere is a layout nobody
owns. What is fixed is which way dependencies point, what a package promises, where construction
happens, and that a contract and its implementations share one directory (`python-contracts`).
