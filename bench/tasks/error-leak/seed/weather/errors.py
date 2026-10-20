"""The one exception this package raises."""


class WeatherError(Exception):
    """The weather service could not be reached, refused, or answered something unreadable."""
