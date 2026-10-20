"""Errors the shop raises."""


class ShopError(Exception):
    """Root of the shop's errors."""


class NotFoundError(ShopError):
    """A lookup found nothing."""
