"""A minimal HTTP client contract and its errors."""

from abc import ABC, abstractmethod
from collections.abc import Mapping


class HttpError(Exception):
    """The request did not produce a response."""


class HttpStatusError(HttpError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class HttpClient(ABC):
    @abstractmethod
    def get_json(self, path: str) -> Mapping[str, object]:
        """Return the decoded body; raise HttpStatusError on a non-2xx status, HttpError otherwise."""
