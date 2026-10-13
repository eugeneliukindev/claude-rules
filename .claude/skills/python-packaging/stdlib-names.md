# A Module Named Like the Standard Library

### A module that reaches `sys.path` directly never takes a stdlib name

**Why:** a top-level module of a distribution, a loose script or a scheduler DAG file named `json`,
`types`, `logging`, `io` or `abc` is what `import json` anywhere in the process then gets. Nested
inside a package the name is only ever `mypackage.json`, so nothing is shadowed, and the module is
named after its contents. ruff `A005` agrees by default — it compares the full dotted path, so it
fires on a top-level `src/json.py` and not on `atlas/_internal/json.py` (measured on ruff 0.17);
`flake8-builtins.strict-checking` stays off, or it reports every nested module and the package
needs a suppression it has no reason for.
