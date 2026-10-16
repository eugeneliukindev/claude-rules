---
paths:
  - "**/*.py"
---

# Python - Modules

## Module Layout

- **Order every module the same way.** A one-line docstring, imports and `__all__`, constants and type aliases, the logger, exceptions, contracts, concrete classes, public functions high-level first, private functions after them in call order, and a `__main__` guard that only calls `main()`; split a module that will not fit, rather than reorder it.
- **Run nothing at import beyond constants, the logger and its kin.** A network call, a file read or a settings object at import makes every import slow and order-dependent, and no test can import the module without the environment it reads.

## Encapsulation

- **Prefix with an underscore every name no other module of the code uses, whatever the tests import.** Functions, methods, attributes, constants, type aliases and classes alike, constants and aliases being the ones missed; without the prefix a name reads as surface, and the first outside import makes it surface for good. Skip it in a script nobody imports, and for a name a framework reaches through a decorator, like a route or a fixture.
- **Test through the public names, and import a `_helper` with logic of its own only knowingly.** The production code decides the prefix, not the test.
- **Drop a name's prefix in the same change that makes a second module use it.** Never import another module's `_name`.
- **Re-export from a package's `__init__.py` only the main names its consumers use.** A facade of everything makes a job that needs one enum load every heavy library; put what only some need in a public `package/topic.py`, and what only siblings use in an internal `_topic.py` nobody reaches into. An application package nobody outside imports needs no facade.

## Imports

- **Declare every direct dependency, and never feature-detect one.** A package you get only through another dependency disappears when that one drops it, and `try: import x` turns a missing dependency into a code path nobody tested.
