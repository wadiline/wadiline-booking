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
