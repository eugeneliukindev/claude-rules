Write `customers.py` with a function that loads a customer by id through the `HttpClient` in
`http_client.py` (GET `/customers/{id}`, JSON body with `id`, `name`, `email`) and returns a
`Customer`. The API sometimes answers 404 for unknown ids and sometimes fails with 5xx or a
connection error — callers need to be able to tell an unknown customer apart from the service
being down. No need to run anything.
