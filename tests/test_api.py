from zoneinfo import ZoneInfo

import pytest

from wadiline import db

ORDER = ["ALX-0700", "ASW-0700", "LXR-0800", "HRG-0830", "ALX-1500", "ALX-1900", "ASW-2200", "SSH-2300"]
BOOKING = {"seat": 45, "from": "Luxor", "to": "Aswan",
           "passenger": {"name": "Adham Gabr", "type": "adult"}, "email": None}


@pytest.mark.parametrize(("params", "expected"), [
    ({}, ORDER), ({"date": "2026-11-12"}, []), ({"from": "Hurghada"}, ["LXR-0800", "HRG-0830"]),
    ({"to": "Luxor"}, ["ASW-0700", "LXR-0800", "ASW-2200"]),
    ({"from": "cai", "to": "lXr"}, ["ASW-0700", "ASW-2200"]),
    ({"from": "Luxor", "to": "Cairo"}, []), ({"from": "Suez"}, []),
], ids=["all", "date", "from", "to", "pair", "reverse", "empty"])
def test_list_trips(client, params, expected):
    response = client.get("/trips", params=params)
    assert response.status_code == 200
    assert [row["code"] for row in response.json()] == expected


@pytest.mark.parametrize("case", ["body", "offsets", "unknown", "wrong-date"])
def test_trip(client, case):
    if case in ("unknown", "wrong-date"):
        path = "/trips/UNKNOWN" if case == "unknown" else "/trips/ALX-0700?date=2026-11-12"
        response = client.get(path)
        assert response.status_code == 404 and response.json()["detail"]["code"] == "trip_not_found"
    elif case == "body":
        response = client.get("/trips/ALX-0700")
        assert response.status_code == 200
        assert response.json() == {"code": "ALX-0700", "date": "2026-11-11", "route": "ALEX",
                                   "stops": [{"name": "Cairo", "time": "2026-11-11T07:00:00+02:00"},
                                             {"name": "Alexandria", "time": "2026-11-11T10:00:00+02:00"}]}
    else:
        response = client.get("/trips/SSH-2300")
        assert response.status_code == 200
        assert [s["time"] for s in response.json()["stops"]] == [
            "2026-11-11T23:00:00+02:00", "2026-11-12T06:30:00+02:00"]


@pytest.mark.parametrize(("start", "end", "code", "status", "error"), [
    ("CAI", "ALX", "ALX-0700", 200, None), ("Cairo", "Alexandria", "ALX-0700", 200, None),
    ("cAiRo", "aLx", "ALX-0700", 200, None), ("CAI", "ALX", "ALX-1500", 200, None),
    ("SUE", "ALX", "ALX-0700", 422, "unknown_stop"), ("CAI", "SUE", "ALX-0700", 422, "unknown_stop"),
    ("ALX", "CAI", "ALX-0700", 422, "bad_leg"), ("CAI", "CAI", "ALX-0700", 422, "bad_leg"),
    ("CAI", "ALX", "UNKNOWN", 404, "trip_not_found"),
], ids=["codes", "names", "mixed-case", "partition", "unknown-from", "unknown-to", "reversed", "equal", "missing-trip"])
def test_map(client, conn, start, end, code, status, error):
    response = client.get(f"/trips/{code}/seats", params={"from": start, "to": end})
    assert response.status_code == status
    body = response.json()
    if error:
        assert body["detail"]["code"] == error
        return
    trip = db.get_trip(conn, code)
    leg = trip.leg(start, end)
    taken = [ticket.seat for ticket in db.live_tickets(conn, trip)]
    seats = list(range(1, trip.seats + 1))
    expected = {"trip": code, "date": "2026-11-11", "from": trip.stop_name(leg.board),
                "to": trip.stop_name(leg.alight),
                "free": [seat for seat in seats if seat not in taken], "taken": taken}
    assert {key: body[key] for key in expected} == expected
    assert sorted(body["free"] + body["taken"] + body.get("held", [])) == seats


@pytest.mark.parametrize("case", ["body", "persistence", "adult", "child", "student", "repeat",
                                 "missing-trip", "unknown-from", "unknown-to", "reverse",
                                 "seat-zero", "seat-50", "missing-passenger", "invalid-type"])
def test_book(client, conn, clock, case):
    body = {**BOOKING, "passenger": BOOKING["passenger"].copy()}
    trip = "ASW-0700"
    start = "Luxor"
    end = "Aswan"
    ref = "WL-58264"
    adult = 24000
    body.update({"from": start, "to": end})
    path = f"/trips/{trip}/bookings"
    failure = None
    if case == "missing-trip":
        path, failure = "/trips/UNKNOWN/bookings", (404, "trip_not_found")
    elif case in ("unknown-from", "unknown-to"):
        body[case.split("-")[1]] = "Suez"
        failure = (422, "unknown_stop")
    elif case == "reverse":
        body.update({"from": end, "to": start})
        failure = (422, "bad_leg")
    elif case in ("seat-zero", "seat-50"):
        body["seat"] = 0 if case == "seat-zero" else 50
        failure = (422, "bad_request")
    elif case == "missing-passenger":
        del body["passenger"]
        failure = (422, "bad_request")
    elif case == "invalid-type":
        body["passenger"]["type"] = "missing"
        failure = (422, "bad_request")
    elif case in ("adult", "child", "student"):
        body["passenger"]["type"] = case
    response = client.post(path, json=body)
    if failure:
        assert (response.status_code, response.json()["detail"]["code"]) == failure
        return
    assert response.status_code == 201
    result = response.json()
    if case == "body":
        assert result == {"ref": ref, "trip": trip, "date": "2026-11-11", "seat": 45,
                          "from": start, "to": end, "passenger": body["passenger"],
                          "price_piastres": adult, "price": f"{adult // 100} EGP"}
    elif case == "persistence":
        stored = db.get_booking(conn, result["ref"])
        assert (stored.sold_at, stored.channel, stored.email) == (clock.now(), "counter", None)
        assert stored.tickets[0].seat == 45
    elif case == "repeat":
        repeat = client.post(path, json=body)
        assert repeat.status_code == 409 and repeat.json()["detail"]["code"] == "seat_taken"
    else:
        amount = {"adult": adult, "child": adult // 2, "student": adult * 3 // 4}[case]
        assert result["price_piastres"] == amount and result["price"] == f"{amount // 100} EGP"


@pytest.mark.parametrize("case", [
    "single", "group", "cancelled", "missing",
])
def test_booking(client, conn, case):
    if case == "missing":
        response = client.get("/bookings/WL-99999")
        assert response.status_code == 404 and response.json()["detail"]["code"] == "booking_not_found"
        return
    query = {"group": "SELECT booking_ref FROM tickets GROUP BY booking_ref HAVING count(*)=4",
             "cancelled": "SELECT booking_ref FROM tickets WHERE status='cancelled'"}
    if case == "single":
        ref = "WL-58214"
    else:
        ref = conn.execute(query[case]).fetchone()[0]
    response = client.get(f"/bookings/{ref}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ref", "sold_at", "channel", "total_piastres", "tickets"}
    sold_at = db.get_booking(conn, ref).sold_at.astimezone(ZoneInfo("Africa/Cairo"))
    assert body["ref"] == ref and body["sold_at"] == sold_at.isoformat()
    if case == "single":
        amount = 24000
        seat = 14
        assert body["total_piastres"] == amount and body["tickets"][0]["seat"] == seat
    elif case == "group":
        assert len(body["tickets"]) == 4 and body["total_piastres"] == sum(t["price_piastres"] for t in body["tickets"])
    else:
        assert body["total_piastres"] == 0 and body["tickets"][0]["status"] == "cancelled"


@pytest.mark.parametrize("case", ["full", "half", "none", "repeat", "missing"])
def test_cancel(client, clock, case):
    if case == "missing":
        response = client.post("/bookings/WL-99999/cancel")
        assert response.status_code == 404 and response.json()["detail"]["code"] == "booking_not_found"
        return
    ref = "WL-58214"
    adult = 24000
    clock.advance(**{"full": {"days": -2}, "half": {}, "none": {"hours": 20}, "repeat": {}}[case])
    response = client.post(f"/bookings/{ref}/cancel")
    if case == "repeat":
        assert response.status_code == 200
        second = client.post(f"/bookings/{ref}/cancel")
        assert second.status_code == 409 and second.json()["detail"]["code"] == "already_cancelled"
    else:
        amount = {"full": adult, "half": adult // 2, "none": 0}[case]
        assert response.status_code == 200
        assert response.json() == {"ref": ref, "share": case, "refund_piastres": amount,
                                   "refund": f"{amount // 100} EGP"}
        assert client.get(f"/bookings/{ref}").json()["total_piastres"] == 0


def test_booking_seat_14_from_cairo_to_aswan_is_a_conflict(client):
    response = client.post("/trips/ASW-2200/bookings", json={**BOOKING, "seat": 14, "from": "Cairo"})
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "seat_taken",
                                         "message": "Seat 14 is taken for part of Cairo to Aswan."}}
