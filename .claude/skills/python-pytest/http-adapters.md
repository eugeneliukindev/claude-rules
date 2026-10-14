# HTTP Adapters

The service behind an adapter is tested with a fake of the contract (`testing.md`); the adapter
itself — the request it builds, the errors it translates, its timeouts — is tested against HTTP.

### An adapter is tested against a real local server, never a patched client method

**Why:** a patched `get` proves the code calls `get`, not that the adapter turns a real `404` into
the domain's error. `pytest-httpserver` runs a real server on localhost, so the adapter goes through
its real client, session and error translation, whichever library that is. `respx` patches `httpx`
and `httpcore` only — not `niquests` — so an adapter on anything else is tested against
`pytest-httpserver`.

**Example:**
```python
# WRONG — the adapter's own request method is patched: no 404 is ever translated
def test_fetch_shared_deck_translates_unknown_code(mocker: MockerFixture) -> None:
    mocker.patch.object(
        DeckExchangeClient, "_get_json", side_effect=SharedDeckNotFoundError(_SHARE_CODE)
    )
    client = DeckExchangeClient(base_url=_EXCHANGE_URL)

    with pytest.raises(SharedDeckNotFoundError, match=_SHARE_CODE):
        client.fetch_shared_deck(_SHARE_CODE)


# CORRECT — a real server answers 404, through the adapter's real session and error translation
def test_fetch_shared_deck_translates_unknown_code(httpserver: HTTPServer) -> None:
    httpserver.expect_oneshot_request(f"/shared-decks/{_SHARE_CODE}").respond_with_json(
        {"detail": "not found"}, status=HTTPStatus.NOT_FOUND
    )
    client = DeckExchangeClient(base_url=httpserver.url_for("/"))

    with pytest.raises(SharedDeckNotFoundError, match=_SHARE_CODE):
        client.fetch_shared_deck(_SHARE_CODE)
```

### A test that expects a server error ends with `httpserver.check_assertions()`

**Why:** a request no handler matches — a typo in the path, a missing query parameter — gets
pytest-httpserver's own `500`, and an adapter that translates `5xx` into its outage error passes a
test of that translation without ever sending the right request. `check_assertions()` raises for
every unmatched request; nothing calls it for you.

**Example:**
```python
# WRONG — had the adapter requested the wrong path, the server's own 500 would pass this test
def test_fetch_shared_deck_reports_outage(httpserver: HTTPServer) -> None:
    httpserver.expect_oneshot_request(f"/shared-decks/{_SHARE_CODE}").respond_with_data(
        "", status=HTTPStatus.SERVICE_UNAVAILABLE
    )
    client = DeckExchangeClient(base_url=httpserver.url_for("/"))

    with pytest.raises(DeckExchangeUnavailableError, match=_SHARE_CODE):
        client.fetch_shared_deck(_SHARE_CODE)


# CORRECT — the test fails unless the 503 came from the handler it set up
def test_fetch_shared_deck_reports_outage(httpserver: HTTPServer) -> None:
    httpserver.expect_oneshot_request(f"/shared-decks/{_SHARE_CODE}").respond_with_data(
        "", status=HTTPStatus.SERVICE_UNAVAILABLE
    )
    client = DeckExchangeClient(base_url=httpserver.url_for("/"))

    with pytest.raises(DeckExchangeUnavailableError, match=_SHARE_CODE):
        client.fetch_shared_deck(_SHARE_CODE)

    httpserver.check_assertions()
```
