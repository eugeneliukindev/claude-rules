We send password-reset links that must stop working 30 minutes after they are issued.

Write `reset_tokens.py` with a small `ResetToken` type (token string, user id, expiry time), a
function that issues one for a user id, and a function that tells whether a given token has
expired. No storage, just the functions; no need to run anything.
