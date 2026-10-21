# Code design: change the least, keep the structure

Write the least design that fully solves the task. Finish the whole change: everything that refers to what you changed.

Where the codebase has decided, follow it: it has decided when it does one thing the same way in several places. Where its decision breaks section 3 or 4, your change follows those sections and your reply names the breach. When the task is to change such a decision, or the codebase has decided two ways or not at all, follow these rules and name the conflict. Linters decide form; keep a rule's intent in a form they accept. Never override the project's layer rules, validation at trust boundaries, error handling that prevents data loss, the public API, or what the user asked for.

## 1. Read first

Read the code the task touches and keep its structure. Use the words its neighbours use, one word for one meaning. Decide whether this is a library others install; *lib* rules apply only then.

## 2. Add the least

Prefer no new code to a new name, a private name to a public one, a new name to a new module. Add no option, layer, wrapper or dependency nobody asked for, no stateless class with one method, no settings object for one or two values.
Check: can you delete this name and still solve the task?

## 3. Dependencies point toward business logic

Business logic is what the program decides and computes. A detail is how a piece of work gets done: doing it another way would change no business logic. A framework is a detail like any other.
- Source code dependencies point only toward business logic: it names nothing outside itself.
- Business logic declares an abstract type for each detail it needs; each implementation names that type as its parent and comes in through the constructor, even if there is only one. A one-operation detail is a function parameter.
- Data that crosses into business logic is a plain record it owns, never an object of a detail.
- Build every implementation at the entry point and pass it inward; nothing inside builds its own.
- Code that touches a detail stays too thin to need a test; every decision moves out of it into code that has one.
- Call business logic directly, however slow.
Check: done another way, would any business logic change? If not, it is a detail.

## 4. Shape

- Data with meaning is an immutable record, not a map or tuple. A type the task states stays that type. A constructor does no I/O and nothing that can fail on outside state; connecting, loading or parsing is a named alternative constructor that owns what it opens. Arguments after the second are passed by name.
- A query changes nothing; a command says so in its name and returns nothing.
- A module or class answers to one actor: split it where two actors would ask for different changes.
- A new variant is new code: pick an implementation by kind from one mapping built at the entry point; shared code never branches on a kind. Shared behaviour is a wrapper, not a flag.
- An implementation accepts all its abstract type accepts and raises only what it names.
- An abstract type declares only what its caller uses.
- What changes together lives together; modules never depend on each other in a cycle.
- Depend toward what changes less; what many modules depend on is abstract.

## 5. Values

A value a caller might set differently is a named argument with its default in the signature; a detail takes its tuning values through its constructor. Three or more become one immutable settings object. Move a value; never change what it does.
Check: for each literal you wrote, which caller would set it to something else?

## 6. Names

- Use the words people who work in the domain use in English. A translation from another language is not a name.
- One concept has one word everywhere: code, storage, wire format and docs.
- Packages and modules are named for what the program does, not for the tools it uses or the role a layer plays.
- A function is a verb phrase saying what it does to what, with the most precise verb that fits. A preposition alone, or a verb that fits anything, says nothing. A cheap read is a noun.
- A class is a noun phrase saying what the thing is, its role last; no word that only says it is code. A record's state is a participle before its concept.
- A boolean asks a question. A collection is the plural of its items; a map is named for its values, with the key only to tell two apart. A unit goes in the type. No abbreviation the domain does not use.
- The wider a name is visible, the fuller and more precise it is.
- Renaming a public name, change every user of it; *lib* keep the old name as a deprecated alias that warns, for one minor version.
Check: read each call aloud without its body; does it say what happens, in words a native speaker of the domain would use?

## 7. Errors and resources

Validate at trust boundaries into typed objects; inside, trust the types. Put package errors under one root and convert a library's errors once, where you call it. Log an error once, where it is handled. Close what you create; leave open what you were given; keep no resource or changing state at module level. Run concurrent work in a group that waits for all of it.

## 8. Tests

Pass fakes through the constructor; patch only what cannot be passed in. Never edit a test to make it pass; report one that contradicts the task. Without tests, show the changed behaviour before and after.

## 9. Finish

Run the tests, linter and type checker; fix what you broke. Fix a fault where it comes from, and wherever it repeats. Change only what was asked; mention the rest. Comment only why. Claim only what output showed. End with two lines: new public names and modules (or "none"), and what you did not check.
