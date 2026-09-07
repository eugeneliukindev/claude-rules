# niquests

Not loaded automatically — open it when the code imports `niquests`. The API is `requests`-shaped,
so the habits below transfer to `httpx` almost unchanged; what does not transfer is called out.

## One Session, Owned by the Composition Root

- **Never a module-level call.** `niquests.get(url)` opens a connection, uses it once and throws it
  away — no pooling, no shared configuration, and nothing to close on shutdown.
- **Build one `AsyncSession` (or `Session`) per application**, in the composition root, and pass it
  down. Connection reuse is most of the performance difference, and one session is also the one
  place headers, timeouts and TLS settings are configured.
- **Close it deterministically** — an exit stack or the framework's lifespan hook, never `atexit`.

## Timeouts

- **A timeout on every request.** There is no useful default: a call without one turns the other
  side's outage into an unbounded wait in your process.
- **Set it on the session** and override per call only with a named constant. A literal `30` at a
  call site is a number nobody can change safely.
- Distinguish connect from read where the client allows it. A slow handshake and a slow body are
  different failures with different budgets.

## Responses Are Checked, Not Assumed

- **`raise_for_status()`, or an explicit status check.** A `404` has a body and a truthy response
  object; code that goes straight to `.json()` will parse the error page and carry on.
- **Translate at the adapter.** The rest of the codebase must never see a library exception: convert
  transport errors and status errors into your own transient and permanent types, and let the retry
  policy key on those.
- **`.json()` gives you a shape, not a contract.** Validate it at the boundary before it travels
  inward.

## Redirects and TLS

- **Decide about redirects deliberately.** Following them is the default; for anything where the
  final URL matters — an API that signals with `301`, a preview page that redirects when access is
  refused — turn it off and read the status.
- **TLS verification stays on.** Never disable it to make something work; if a certificate is
  genuinely private, supply the CA bundle.
- **Re-validate a redirect target** when the original URL came from a user, or the allowlist you
  checked before the request is worthless.

## Retries

- Retries are a policy decision and belong beside the call, not buried in transport configuration —
  see `tenacity.md`. Retry transient failures only, bounded, jittered, and at one layer.

## What Differs From `httpx`

- **`niquests` is a drop-in for `requests`**, so `session.get(...)` returns a response with
  `.status_code`, `.text`, `.json()`; `httpx` matches this closely but names some keywords
  differently — notably `allow_redirects` here versus `follow_redirects` there.
- Both support HTTP/2 and async. Pick one per codebase and do not mix: two HTTP stacks mean two
  places to configure timeouts, and one of them will be forgotten.
