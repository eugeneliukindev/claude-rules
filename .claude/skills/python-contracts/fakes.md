# The Contract Suite

That a contract a unit test depends on has an in-memory fake in `tests/fakes.py`, inheriting the
contract, is in `testing.md`; this is the suite the fake and the real implementations pass.

### One parametrized fixture runs the contract suite against every implementation

**Why:** the tests are written once against the contract; the real implementations carry the
integration marker, so the unit run still takes the fake. A fake not held to the same tests drifts,
and the unit tests then prove the fake.

**Example:**
```python
# WRONG — the fake is tested by nothing, and the real glossary by its own separate tests
def test_in_memory_glossary_lists_added_term() -> None:
    glossary = InMemoryGlossary()
    entry = make_glossary_entry(language=LanguageCode("de"))
    glossary.add(entry)
    assert glossary.terms_in(LanguageCode("de")) == [entry]


# CORRECT — one suite, every implementation
@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("sql", id="sql", marks=pytest.mark.integration),
    ]
)
def glossary(request: pytest.FixtureRequest) -> Glossary:
    implementation: Glossary = request.getfixturevalue(f"{request.param}_glossary")
    return implementation


def test_added_term_is_listed_in_its_language(glossary: Glossary) -> None:
    entry = make_glossary_entry(language=LanguageCode("de"))

    glossary.add(entry)

    assert glossary.terms_in(LanguageCode("de")) == [entry]
```
