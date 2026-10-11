# Constants

The composition root and resource lifetime are in `SKILL.md`.

### A constant lives next to its single user

**Why:** a constant shared by several modules lives in the module that owns the concept; a global
grab-bag of constants is a module every other module imports and nobody owns.

**Example:**
```python
# WRONG — constants.py: every limit of the application, imported everywhere, owned by nobody
MAX_DOCUMENT_PAGES: Final = 500
MAX_LOGIN_ATTEMPTS: Final = 5
REMINDER_LEAD_DAYS: Final = 3


# CORRECT — each constant in the module that owns its concept, next to the code that reads it
# documents/limits.py
MAX_DOCUMENT_PAGES: Final = 500


def check_page_count(document: Document) -> None:
    if document.page_count > MAX_DOCUMENT_PAGES:
        raise DocumentTooLongError(document.document_id, page_count=document.page_count)
```
