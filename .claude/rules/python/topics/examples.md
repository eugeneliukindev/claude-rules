# Shipped Examples

Not loaded automatically — open it when writing an example that ships: a docstring example, a
`README` snippet, a file under `examples/`. An example is executable documentation, held to the
same standard as the code it demonstrates, plus one extra requirement — it must run.

- **Show the smallest complete thing.** One capability, with every import and object constructed
  inside it. An example that starts mid-story is unusable and unverifiable.
- **Examples are executed, not proofread.** An example nobody runs is wrong within a release or two.
- **Start from the caller's goal, not the API surface.** Order examples by frequency of use.
- **Realistic data, no filler.** Never `foo`, `bar`, `test123`. Use reserved example values
  (`example.com`, RFC 5737 addresses) so an example can never hit a real host. Never a real key,
  token, hostname or customer name, not even redacted.
- **Deterministic output.** Anything time-, id- or order-dependent is pinned: inject a fixed clock,
  use a literal UUID, sort before printing.
- **Show the outcome, not the plumbing.** Print or assert the one value that proves the point.
- **Examples follow every rule in these files.** Copy-paste is how examples are consumed: an
  example with a bare `except` teaches a bare `except` to every reader.
- **Never demonstrate an anti-pattern without marking it** `# WRONG` next to a `# CORRECT`.
- **The happy path is the example; failures get their own** — one per error scenario a caller must
  handle.
- **Keep examples versioned with the API.** A deprecated path disappears from examples in the same
  release it is deprecated in.
