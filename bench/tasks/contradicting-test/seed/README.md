# durations

`parse_duration` turns a human duration into seconds. Units are `h`, `m` and `s`, and they combine:
`1h30m` is 5400. A bare number has no unit and means minutes, because the booking form asks for
minutes: `90` is 5400.
