---
paths:
  - "**/pyproject.toml"
  - "**/uv.lock"
---

# uv

Environment, dependencies, lockfile and command running — one tool for all four, so there is no
second mechanism to disagree with the first.

## The Lockfile Is the Contract

- **The lockfile is committed**, and CI verifies it is current. A lockfile that drifts from
  `pyproject.toml` means every machine resolves slightly differently and the failure surfaces on
  whichever one is unlucky.
- **`pyproject.toml` states bounds; the lockfile states versions.** Pinning an exact version in the
  dependency list duplicates the lockfile's job and makes every bump a merge conflict.
- **CI and images install frozen**, so a build cannot quietly resolve something new between the
  commit that passed review and the artefact that ships.

## Declaring Dependencies

- **Every direct dependency is declared, with a lower bound.** Never rely on something arriving
  transitively: it works until the package that pulled it in drops it, and then the failure names
  the wrong library.
- **The lower bound is the oldest version whose behaviour you rely on**, not the version that
  happened to be installed the day it was added.
- **Dependency groups are for development; extras are for consumers.** A test runner, a linter and a
  type checker belong to a group — nobody installing the package wants them. An optional runtime
  capability belongs to an extra, because a consumer must be able to ask for it.
- **Adding a dependency is a decision, not a reflex.** Check the standard library first; see
  `stdlib.md`.

## Running Things

- **Commands run through `uv run`**, so nothing depends on an activated environment. A script that
  only works after someone remembered to activate is a script that fails in CI.
- **Never install into the environment by hand.** Editing the environment without editing
  `pyproject.toml` produces a machine that works and a lockfile that does not know why.

## Workspaces

- **One lockfile for the whole workspace.** Members resolve together, so two packages cannot end up
  wanting incompatible versions of the same dependency without the resolver saying so.
- **A member depends on its siblings as workspace sources**, not by version. Otherwise a local
  change is invisible until it is published.
- **The workspace root owns the tool configuration**; members own only their own dependencies.
