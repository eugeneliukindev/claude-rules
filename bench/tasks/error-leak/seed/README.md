# weather

Client for the weather service. Every failure of this package, whether the network, the service or
its answer, raises `weather.WeatherError`, so callers catch one exception.
