import pytest
from fastapi.routing import APIRoute

from wadiline import db
from wadiline.api import app
from wadiline.models import PassengerType

BASE_ROUTES = frozenset({
    ("GET", "/trips"), ("GET", "/trips/{trip_code}"), ("GET", "/trips/{trip_code}/seats"),
    ("POST", "/trips/{trip_code}/bookings"), ("GET", "/bookings/{ref}"),
    ("POST", "/bookings/{ref}/cancel"),
})
# Run as soon as a route joins the six, so missing or misnamed functions fail.
if {(method, route.path) for route in app.routes if isinstance(route, APIRoute)
        for method in route.methods} == BASE_ROUTES:
    pytest.skip("The holds API is not built yet.", allow_module_level=True)

HOLD = {"seat": 45, "from": "Luxor", "to": "Aswan", "holder": "app-7f3a"}
EXPECTED = {"hold_id": "H-000001", "trip": "ASW-0700", "date": "2026-11-11", "seat": 45,
            "from": "Luxor", "to": "Aswan", "expires_at": "2026-11-11T12:10:00+02:00"}


def place(client, trip="ASW-0700", **changes):
    return client.post(f"/trips/{trip}/holds", json={**HOLD, **changes})


def release(client, hold_id="H-000001", holder="app-7f3a"):
    return client.post(f"/holds/{hold_id}/release", json={"holder": holder})


def code(response, status, error):
    assert response.status_code == status
    assert response.json()["detail"]["code"] == error


def sell(client):
    return client.post("/trips/ASW-0700/bookings", json={
        "seat": 45, "from": "Luxor", "to": "Aswan",
        "passenger": {"name": "Adham Gabr", "type": "adult"}, "email": None})


def seat_map(client):
    response = client.get("/trips/ASW-0700/seats", params={"from": "Luxor", "to": "Aswan"})
    assert response.status_code == 200
    return response.json()


def test_created_body(client):
    result = place(client)
    assert result.status_code == 201 and result.json() == EXPECTED


def test_repeat_body(client, clock):
    first = place(client)
    clock.advance(minutes=5)
    second = place(client)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json() == second.json() == EXPECTED


def test_sold_conflict(client, conn, clock):
    trip = db.get_trip(conn, "ASW-0700")
    with conn:
        db.create_booking(conn, trip, 45, trip.leg("AST", "ASW"), "Adham Gabr",
                          PassengerType.ADULT, "counter", None, clock.now())
    code(place(client), 409, "seat_taken")


def test_held_conflict(client):
    assert place(client).status_code == 201
    code(place(client, holder="second"), 409, "seat_held")


def test_trip_missing(client):
    code(place(client, "MISSING"), 404, "trip_not_found")


def test_unknown_stop(client):
    code(place(client, **{"from": "Suez"}), 422, "bad_request")


def test_seat_50(client):
    code(place(client, seat=50), 422, "bad_request")


def test_missing_holder(client):
    body = {key: value for key, value in HOLD.items() if key != "holder"}
    code(client.post("/trips/ASW-0700/holds", json=body), 422, "bad_request")


def test_release_then_other_holder(client):
    assert place(client).status_code == 201
    released = release(client)
    assert released.status_code == 204 and released.content == b""
    assert place(client, holder="second").status_code == 201


def test_second_release(client):
    assert place(client).status_code == 201
    assert release(client).status_code == 204
    assert release(client).status_code == 204


def test_wrong_holder_404(client):
    assert place(client).status_code == 201
    code(release(client, holder="second"), 404, "hold_not_found")


def test_unknown_id_404(client):
    assert place(client, holder="first").status_code == 201
    second = place(client, seat=46)
    assert second.status_code == 201 and second.json()["hold_id"] == "H-000002"
    for hold_id in ("H-999999", "H-0000002", "H-9223372036854775808"):
        code(release(client, hold_id), 404, "hold_not_found")
    repeat = place(client, seat=46)
    assert repeat.status_code == 200 and repeat.json() == second.json()


@pytest.fixture
def sold_seat(conn, clock):
    trip = db.get_trip(conn, "ASW-0700")
    with conn:
        conn.execute("DELETE FROM tickets WHERE trip_id=?", (trip.id,))
        db.create_booking(conn, trip, 46, trip.leg("LXR", "ASW"), "Adham Gabr",
                          PassengerType.ADULT, "counter", None, clock.now())
    return 46


def test_map_held(client, sold_seat):
    assert place(client).status_code == 201
    body = seat_map(client)
    assert body["held"] == [45] and body["taken"] == [sold_seat]
    assert body["free"] == [seat for seat in range(1, 50) if seat not in (45, sold_seat)]


def test_map_free_at_expiry(client, clock, sold_seat):
    assert place(client).status_code == 201
    clock.advance(minutes=10)
    body = seat_map(client)
    assert body["held"] == [] and body["taken"] == [sold_seat]
    assert body["free"] == [seat for seat in range(1, 50) if seat != sold_seat]


def test_counter_held(client):
    assert place(client).status_code == 201
    response = sell(client)
    code(response, 409, "seat_held")
    assert response.json()["detail"]["message"] == "Seat 45 is held for part of Luxor to Aswan."


def test_counter_after_expiry(client, clock):
    assert place(client).status_code == 201
    clock.advance(minutes=10)
    assert sell(client).status_code == 201


def test_counter_touching_hold(client):
    assert place(client, **{"from": "Cairo", "to": "Luxor"}).status_code == 201
    assert sell(client).status_code == 201
