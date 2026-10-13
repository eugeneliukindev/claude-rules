# HTTP Adapters

The service behind an adapter is tested with a fake of the contract (`testing.md`); the adapter
itself — the request it builds, the errors it translates, its timeouts — is tested against HTTP.

### An adapter is tested against a real local server, never a patched client function

**Why:** a patched `get` proves the code calls `get`, not that the adapter turns a real `404` into
the domain's error. `pytest-httpserver` runs a real server on localhost, so the adapter goes
through its real client, session and error translation, whichever library that is. `respx` patches
`httpx` and `httpcore` only — not `httpx2`, which Starlette's `TestClient` now wants, and not
`niquests` — so an adapter on those is tested against `pytest-httpserver`.

**Example:**
```python
# WRONG — the adapter's own request method is patched: no 404 is ever translated
def test_fetch_forecast_translates_unknown_city(mocker: MockerFixture) -> None:
    mocker.patch.object(ForecastClient, "_get_json", side_effect=CityNotFoundError("Atlantis"))
    client = ForecastClient(
        base_url="https://weather.example.com", timeout_seconds=_TIMEOUT_SECONDS
    )

    with pytest.raises(CityNotFoundError, match="Atlantis"):
        client.fetch_forecast("Atlantis")


# CORRECT — a real server answers 404, through the adapter's real session and error translation
def test_fetch_forecast_translates_unknown_city(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/forecasts/Atlantis").respond_with_json(
        {"detail": "not found"}, status=HTTPStatus.NOT_FOUND
    )
    client = ForecastClient(base_url=httpserver.url_for("/"), timeout_seconds=_TIMEOUT_SECONDS)

    with pytest.raises(CityNotFoundError, match="Atlantis"):
        client.fetch_forecast("Atlantis")
```
