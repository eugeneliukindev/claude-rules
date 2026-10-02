Write `signup.py` for our signup flow. It receives the raw form fields (email, password, display
name). It should check them — email looks like an email, password at least 12 characters, display
name not blank, email not already taken — and if everything is fine, hash the password and store
the user through the `UserRepository` from `users.py`. Emails should be trimmed and lower-cased
before anything else. No need to run anything.
