# Constants

The composition root and resource lifetime are in `SKILL.md`.

### A constant lives next to its single user

**Why:** a constant shared by several modules lives in the module that owns the concept; a global
grab-bag of constants is a module every other module imports and nobody owns.
