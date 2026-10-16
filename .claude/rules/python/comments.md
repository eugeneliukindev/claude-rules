---
paths:
  - "**/*.py"
---

# Python - Comments and Docstrings

- **Write a comment as one line, in one of four forms.** A caption ending in a colon, indexing the lines below; a reason, why *this* value, never what the line does; a `TODO` naming the condition that removes it, or `shortcut: <the limit>, <when to upgrade>` for a known limit taken on purpose; a `NOTE` for a coupling the code cannot express. Anything else restates the code and goes stale with the first change, and a name a comment explains is a name to fix.
- **Delete commented-out code, banners, stamps and change logs.** They are history git keeps.
- **Write a paragraph only for enumerated cases, a rejected alternative or an honest limitation.**
- **Describe only the comment's own block, and in a docstring only the contract it is attached to.** A caller, a collaborator or an ordering named in prose rots the moment the other side changes, unless it is a `NOTE` for a coupling between artefacts that cannot import each other.
- **Apply the relocation test: paste the block into another module.** A comment that becomes wrong there was leaking.
