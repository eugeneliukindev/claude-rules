"""Client for the weather service."""

from weather.client import current_temperature
from weather.errors import WeatherError

__all__ = ["WeatherError", "current_temperature"]
