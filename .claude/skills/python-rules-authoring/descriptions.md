# Descriptions

### A description is what the skill does, `ALWAYS invoke this skill when` and the signals, then `Do not … directly`

**Why:** the `description` is all the model sees of a skill until it decides to load it, and a
skill it judges optional it skips — it writes the code itself. In a 650-trial test of descriptions,
the directive form — what the skill does, then "ALWAYS invoke this skill when …" with the signals,
then "Do not … directly" — was the one that activated every time; a passive "Use when …" left the
choice to the model
([source](https://medium.com/@ivan.seleznov1/why-claude-code-skills-dont-activate-and-how-to-fix-it-86f679409af1)).
The signals are words a task actually contains — "one-off", "Authorization header", "environment
variables", "in-memory one for the tests" — never the rules the skill holds, which no task names.
`scripts/check_rules.py` holds every description to 400 characters and an `ALWAYS invoke`
clause; the listing every session pays for is capped at 1% of the context window.

**Example:**
```yaml
# WRONG — a table of contents, a passive trigger, and the signals are the skill's own words
description: >-
  Covers composition roots, scopes, resource lifetime, settings and constants. Use when relevant
  to construction.

# CORRECT — what it does, the signals a task contains, and the instruction not to go around it
description: >-
  Designs construction and configuration: one composition root, resource lifetime, settings.
  ALWAYS invoke this skill when a task writes an entry point or main(), opens a pool or a client,
  or reads environment variables. Do not wire objects directly.
```

### Neighbouring descriptions are told apart in their own words

**Why:** the listing is read as a whole, and a description that matches better than the right one
wins — on a public benchmark, wrong selection grew with the size of the library and caused most of
the loss. Two skills whose descriptions both match the same work load the same text twice. Each
names the signals only it should answer — an outbound call for boundaries, an `Authorization`
header for security, a script run once for scripts — and where a neighbour still matches the same
words, a closing `Not for … (python-x).` names it for the near miss.
