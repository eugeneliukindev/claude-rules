# Python: change the least, keep the structure

Write the least design that fully solves the task, and finish the whole change: everything that refers to what you changed, wherever it is written.

Where the codebase has decided, follow it; it has decided when it does one thing the same way in more than one place. When the task is to change such a decision, these rules decide, and the change reaches every place the old decision lives. Where the codebase has not decided, or decided two ways, follow these rules and name the conflict in your reply. Linters and type checkers decide form: when one rejects what a rule asks, keep the rule's intent in a form it accepts. Apply each rule to every case its check covers. Nothing here overrides the project's layer rules, validation at trust boundaries, error handling that prevents data loss, the public API others import, or what the user asked for.

## 1. Read first

Read the code the task touches: who owns the data, who calls it, what the package exports, which layer imports which. Keep that structure; add no layer. Use the words its siblings use; one word, one meaning. Decide whether this is a library others install; *lib* rules apply only then.
Check: could a reader tell your code from its neighbours?

## 2. Depend on what you decide, not on how it gets done

Code that makes a decision depends on an abstract base class it declares, not on the way the work gets done; the way is passed in through the constructor, even if there is only one, and the deciding module never imports it. A way of doing the work is anything that could be swapped for another without changing a decision. Logic that makes the decision is used directly, however slow. A way with one operation is a callable parameter. Your classes used interchangeably in one place share one base class.
Check: could you swap each thing this code calls for another way of doing the same job without editing this code?

## 3. Add the least

Prefer no new code to a new name, a private name to a public one, a public name in the package that owns its data to a new module. Add a dependency only when asked. Add no option, layer or wrapper nobody asked for, no stateless class with one method, no module named for no single thing, no settings object for one or two values, no base class with one implementation except in front of a way of doing the work (section 2).
Check: can you delete this name and still solve the task?

## 4. Name a thing for what it is

A function is a verb, a resource's own verb for a resource; a cheap read is a noun or property. A class ends with its role; its methods do not repeat its name. A boolean asks a question or says what happened or what it turns on. A format or mode goes in the name, not a flag. A collection is the plural of its items; a dict is named for its values, with the key only to tell two such dicts apart. A unit goes in the type. Renaming a public name, change every importer; *lib* keep the old name as a warning alias for one minor version.
Check: read each new name without its body; do you know what it is?

## 5. Let the caller set behaviour

A value a caller might want different is a keyword argument with its default in the signature; a way of doing the work takes the values that tune it through its constructor. Three or more on one object become one immutable settings object. A value no caller would change stays inline; data the module exists to hold is a module constant. Name a value used twice. Move a value; never change what it does.
Check: for each literal you wrote, name the caller who would set it and why; if you cannot, it stays.

## 6. Shape objects so the next change lands in one place

- Data with meaning is an immutable record, not a dict or tuple. Parameters after the second are keyword-only. A type the task or a caller states stays that type.
- A constructor only assigns fields; building, loading, parsing or connecting is a named alternative constructor.
- A query changes nothing. A command changes state, says so in its name and returns nothing. A conversion returns a new object and leaves its input alone.
- A base class declares only what its caller calls. An implementation accepts all it accepts and raises only what it names; a method it cannot implement means the base class is wrong.
- A new variant is new code, not an edit: pick an implementation by kind through one mapping built at the entry point, raise on an unknown kind, never branch on a kind in shared code. Behaviour all implementations share is a wrapper, not a flag in each.
- Split a module by who asks for its changes and by the decision it hides.
Check: name the next likely change; does it touch one place?

## 7. Raise your own errors, close your own resources

Validate at trust boundaries into typed objects; inside, trust the types. Put package errors under one root, misuse apart from failure, and convert a library's errors into yours once, where you call it. Re-raise what you cannot handle; log an error once, where it is handled. Close what you create; leave open what you were given. Keep nothing at module level that changes after import or holds a resource, unless a framework needs it. Run concurrent work in a group that waits for all of it; never swallow cancellation.
Check: can every caller catch what you raise by one type of yours?

## 8. Test through the contract

Pass a fake of the same contract through the constructor or a parameter; patch only what cannot be passed in, and say why in one line. Test public behaviour, one idea per test; parametrize the variants. A test for a bug fails before the fix. Never edit a test to make it pass; report one that contradicts the task. Where the project has no tests, prove the change by running the changed behaviour before and after, show both results, and name the test that should exist.
Check: would it pass after a rewrite that keeps the behaviour?

## 9. Finish and prove it

Run the tests, linter and type checker; fix what you broke. Fix a fault where it comes from, and fix or name it wherever it repeats. Change only the behaviour asked for and only the code it needs; mention anything else that should change. Comment only why, in one line. Claim only what a tool's output showed. End with two lines: new public names and modules (or "none"), and what you did not check.
Check: what output shows each claim in your reply?
