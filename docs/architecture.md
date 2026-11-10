# Architecture

The HTTP API and station commands read trips and tickets through `db`. They call the same
rules to check seats, price a fare or calculate a refund, then ask `db` to save changes.
Each rule lives in one place. SQLite stores whole piastres and UTC times. The API and
commands show times in Cairo and money in EGP.

| Module | Role |
| --- | --- |
| `models` | Trips, stops, legs, tickets and bookings |
| `seats` | Whether two legs share road and which seats can sell |
| `fares`, `refunds`, `money` | Prices, refund shares and EGP display |
| `clock` | Current time for callers and fixed time for tests |
| `db`, `timetable` | SQLite storage, migrations and timetable import |
| `api`, `cli` | HTTP and station commands |
| `holds` | Seat-hold records for BK-63 |

Rules that need the time receive `now` from their caller. They never read the clock.
