# Coverage

### Coverage measures branches, with a floor that only ratchets up, and is never a target

**Why:** line coverage hides an untested `else` arm. Domain and services aim near 100%, adapters
mainly through integration tests; generated code and migrations are excluded in configuration. The
floor (`--cov-fail-under`) is added when there is a suite to hold it and only rises. Coverage
detects untested code: a test written to colour lines green turns an honest unknown into false
confidence, worse than the gap it hides.

**Example:**
```toml
# WRONG — line coverage, and migrations counted as code nobody tests
[tool.coverage.run]
source = ["src"]


# CORRECT — branches measured, generated code and migrations excluded, a floor that can only rise
[tool.coverage.run]
source = ["src"]
branch = true
omit = ["src/*/migrations/*", "src/*/_generated/*"]

[tool.coverage.report]
fail_under = 87
```
