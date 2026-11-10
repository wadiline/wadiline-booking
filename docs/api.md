# HTTP API

Times in replies are Cairo times with their UTC offset. Use a stop's name or code in any
case. If you omit `date`, the service uses the sample service date. Errors have a
`detail` object with `code` and `message`. Invalid request fields return 422
`bad_request` and the first validation error.

| Method and path | Response |
| --- | --- |
| `GET /trips?from=&to=&date=` | 200, trips with `code`, `date`, `route` and `stops` (each with `name` and `time`) |
| `GET /trips/{trip_code}?date=` | 200, one trip in the same shape, or 404 `trip_not_found` |
| `GET /trips/{trip_code}/seats?from=&to=&date=` | 200, `trip`, `date`, `from`, `to`, `free` and `taken`, or 404 `trip_not_found` or 422 `unknown_stop` or `bad_leg` |
| `POST /trips/{trip_code}/bookings` | 201, `ref`, `trip`, `date`, `seat`, `from`, `to`, `passenger`, `price_piastres` and `price`, or 409 `seat_taken`, 404 or 422 |
| `GET /bookings/{ref}` | 200, `ref`, `sold_at`, `channel`, `total_piastres` and `tickets`, or 404 `booking_not_found` |
| `POST /bookings/{ref}/cancel` | 200, `ref`, `share`, `refund_piastres` and `refund`, or 404 `booking_not_found` or 409 `already_cancelled` |

A counter booking takes a body of this shape.

```json
{"seat": 14, "from": "Cairo", "to": "Alexandria", "passenger": {"name": "Adham Gabr", "type": "adult"}, "email": null}
```

The service checks availability and saves the sale in one transaction. If the seat is
already sold on part of the leg, it returns a 409 with a message such as
`Seat 14 is taken for part of Cairo to Alexandria.` A cancellation uses the current clock
time and each ticket's timetabled departure.

## Holds (BK-63, not built yet)

Send `POST /trips/{trip_code}/holds`. For example, send this body for ALX-1500.

```json
{"seat": 45, "from": "Cairo", "to": "Alexandria", "holder": "app-7f3a"}
```

A new hold returns 201. It takes the next ID SQLite assigns, so the first hold in an
empty table is `H-000001`.

```json
{"hold_id": "H-000001", "trip": "ALX-1500", "date": "2024-09-15", "seat": 45, "from": "Cairo", "to": "Alexandria", "expires_at": "2024-09-15T12:10:00+03:00"}
```

The same holder, seat and leg return 200 and the same body while the hold is active.
A sold seat returns 409 `seat_taken`. An active hold that shares road returns 409
`seat_held`. An unknown trip returns 404 `trip_not_found`. A bad stop, a seat that is
not on the bus, or a holder outside 1 to 64 characters returns 422 `bad_request`.

Send `POST /holds/{hold_id}/release` with `{"holder": "app-7f3a"}`. The holder gets an
empty 204, even if the hold has ended or was released. An unknown ID or another holder
gets 404 `hold_not_found`. Use the hold ID exactly as it was issued.
A hold ID in any other form is unknown: 404 `hold_not_found`.

The seat map gains `"held": [...]` for seats with an active hold sharing road and no
such sold ticket. Each seat appears in exactly one of `free`, `taken` and `held`.
A counter sale gets 409 `seat_held` while that hold shares road, for example
`Seat 45 is held for part of Cairo to Alexandria.`
