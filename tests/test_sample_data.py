import json
from collections import Counter
from datetime import datetime, timedelta

import pytest

from wadiline import db

DISTRIBUTION = {"ALX-0700": 41, "ALX-1500": 36, "ALX-1900": 44, "HRG-0830": 38,
                "SSH-2300": 33, "LXR-0800": 27, "ASW-0700": 40, "ASW-2200": 54}
STOPS = dict(CAI="Cairo", ALX="Alexandria", HRG="Hurghada", SSH="Sharm El Sheikh",
             AST="Assiut", LXR="Luxor", ASW="Aswan")
ROUTES = {"ALEX": "CAI ALX", "HURG": "CAI HRG", "SINAI": "CAI SSH", "REDSEA": "HRG LXR",
          "UPPER": "CAI AST LXR ASW"}
FARES = {("CAI", "ALX"): 26000, ("CAI", "HRG"): 64000, ("CAI", "SSH"): 72000,
         ("HRG", "LXR"): 32000, ("CAI", "AST"): 42000, ("CAI", "LXR"): 78000,
         ("CAI", "ASW"): 92000, ("AST", "LXR"): 38000, ("AST", "ASW"): 56000,
         ("LXR", "ASW"): 24000}
AS_OF = datetime.fromisoformat("2026-11-11T10:00:00Z")


@pytest.fixture(scope="module")
def sample():
    return {p.stem: json.loads(p.read_bytes()) for p in db.SAMPLE_DIR.glob("*.json")}


@pytest.fixture(scope="module")
def rows(sample):
    return sample["bookings"]


@pytest.fixture(scope="module")
def tickets(rows):
    return [(row, t) for row in rows for t in row["tickets"]]


@pytest.fixture(scope="module")
def departures(sample):
    return {(trip["code"], stop["stop"]): datetime.fromisoformat(stop["time"])
            for trip in sample["trips"] for stop in trip["stops"]}


def test_catalogs(sample):
    assert sample["stops"] == [dict(code=code, name=name) for code, name in STOPS.items()]
    assert sample["routes"] == [dict(code=code, stops=stops.split()) for code, stops in ROUTES.items()]
    assert len(sample["fares"]) == 10
    assert {(r["from"], r["to"]): r["adult_piastres"] for r in sample["fares"]} == FARES


def test_timetables(sample, conn):
    expected = ["11T07:00 11T10:00", "11T15:00 11T18:00", "11T19:00 11T22:00",
                "11T08:30 11T14:30", "11T23:00 12T06:30", "11T08:00 11T12:30",
                "11T07:00 11T12:30 11T16:40 11T19:50", "11T22:00 12T03:30 12T07:30 12T10:40"]
    for number, (trip, code, times) in enumerate(zip(sample["trips"], DISTRIBUTION, expected, strict=True), 1):
        assert trip["code"] == code and trip["seats"] == 49 and trip["service_date"] == "2026-11-11"
        assert [stop["stop"] for stop in trip["stops"]] == ROUTES[trip["route"]].split()
        assert [stop["time"] for stop in trip["stops"]] == [
            f"2026-11-{time}:00+02:00" for time in times.split()]
        assert db.get_trip(conn, code).id == number


def test_snapshot_and_sizes(conn, rows, tickets):
    assert db.meta(conn, "as_of") == "2026-11-11T10:00:00Z"
    assert db.meta(conn, "service_date") == "2026-11-11"
    assert (len(rows), len(tickets)) == (263, 313)


def test_trip_totals(tickets):
    assert Counter(row["trip"] for row, _ in tickets) == DISTRIBUTION


def test_booking_sizes(rows):
    assert Counter(len(row["tickets"]) for row in rows) == {1: 225, 2: 28, 3: 8, 4: 2}
    assert all(len(row["tickets"]) == 1 for row in rows if row["trip"] == "ASW-2200")


def test_group_members(rows):
    for row in rows:
        assert len({(t["from"], t["to"]) for t in row["tickets"]}) == 1
        assert len({t["seat"] for t in row["tickets"]}) == len(row["tickets"])


def test_children_accompanied(rows):
    for row in rows:
        types = {t["type"] for t in row["tickets"]}
        if "child" in types:
            assert "adult" in types


def test_types_and_prices(tickets):
    assert Counter(t["type"] for _, t in tickets) == {"adult": 250, "child": 34, "student": 29}
    for _, ticket in tickets:
        adult = FARES[ticket["from"], ticket["to"]]
        assert ticket["price_piastres"] == adult * {"adult": 4, "child": 2, "student": 3}[ticket["type"]] // 4


def test_channels_and_emails(rows):
    assert Counter(row["channel"] for row in rows) == {"app": 118, "web": 106, "counter": 39}
    for row in rows:
        email = row["tickets"][0]["name"].lower().replace(" ", ".") + "@inbox.example"
        assert row["email"] == (None if row["channel"] == "counter" else email)


def test_routes_and_legs(sample, tickets):
    routes = {trip["code"]: ROUTES[trip["route"]].split() for trip in sample["trips"]}
    for row, ticket in tickets:
        stops = routes[row["trip"]]
        assert stops.index(ticket["from"]) < stops.index(ticket["to"])


def test_sold_ranges_disjoint(sample, tickets):
    routes = {trip["code"]: ROUTES[trip["route"]].split() for trip in sample["trips"]}
    occupied = {}
    for row, ticket in tickets:
        if ticket["status"] == "sold":
            stops = routes[row["trip"]]
            road = set(range(stops.index(ticket["from"]), stops.index(ticket["to"])))
            already = occupied.setdefault((row["trip"], ticket["seat"]), set())
            assert already.isdisjoint(road)
            already.update(road)


def test_reserved_seats(tickets):
    for row, ticket in tickets:
        if row["trip"] == "ASW-0700":
            assert 1 <= ticket["seat"] <= 40
        elif row["trip"] != "ASW-2200":
            assert 1 <= ticket["seat"] <= 48


def test_day_bus_mix(tickets):
    assert Counter((t["from"], t["to"]) for r, t in tickets if r["trip"] == "ASW-0700") == {
        ("CAI", "ASW"): 24, ("CAI", "LXR"): 6, ("CAI", "AST"): 4,
        ("AST", "ASW"): 3, ("LXR", "ASW"): 3,
    }


def test_refs_and_bands(rows):
    assert [r["ref"] for r in rows] == [f"WL-{n}" for n in range(58001, 58264)]
    sales = [r["sold_at"] for r in rows]
    assert sales == sorted(set(sales))
    assert [sales.index(at) for at in ("2026-11-02T09:05:00Z", "2026-11-08T18:14:00Z",
                                       "2026-11-11T08:52:00Z")] == [116, 213, 261]


def test_sale_deadlines(tickets, departures):
    for row, ticket in tickets:
        sold = datetime.fromisoformat(row["sold_at"])
        assert datetime.fromisoformat("2026-10-12T00:00:00Z") <= sold < AS_OF
        assert departures[row["trip"], ticket["from"]] - sold >= timedelta(minutes=30)


def test_cancellation_counts_and_refunds(tickets, departures):
    shares = Counter()
    for row, ticket in tickets:
        if ticket["status"] == "sold":
            assert ticket["cancelled_at"] is None and ticket["refund_piastres"] is None
            continue
        assert ticket["status"] == "cancelled" and len(row["tickets"]) == 1
        cancelled = datetime.fromisoformat(ticket["cancelled_at"])
        assert datetime.fromisoformat(row["sold_at"]) < cancelled < AS_OF
        assert row["trip"] in ("ALX-0700", "ALX-1500", "HRG-0830", "SSH-2300")
        lead = departures[row["trip"], ticket["from"]] - cancelled
        share = 2 if lead >= timedelta(hours=24) else 1 if lead >= timedelta(hours=3) else 0
        assert ticket["refund_piastres"] == ticket["price_piastres"] * share // 2
        shares[share] += 1
    assert shares == {2: 6, 1: 4, 0: 2}


def test_story_records_exact(rows):
    expected = [
        ("WL-58117", "2026-11-02T09:05:00Z", "web", "ali.badawi@inbox.example", 22, "CAI", "LXR", "Ali Badawi", "adult", 78000),
        ("WL-58214", "2026-11-08T18:14:00Z", "app", "nourhan.elsayed@inbox.example", 14, "LXR", "ASW", "Nourhan Elsayed", "adult", 24000),
        ("WL-58262", "2026-11-11T08:52:00Z", "app", "yasmin.hosny@inbox.example", 22, "LXR", "ASW", "Yasmin Hosny", "student", 18000),
    ]
    for ref, sold, channel, email, seat, start, end, name, kind, price in expected:
        actual = rows[int(ref[3:]) - 58001]
        assert actual == {"ref": ref, "sold_at": sold, "channel": channel, "email": email,
                          "trip": "ASW-2200", "tickets": [{"seat": seat, "from": start, "to": end,
                          "name": name, "type": kind, "price_piastres": price, "status": "sold",
                          "cancelled_at": None, "refund_piastres": None}]}


def test_live_sale_absent(rows):
    assert "WL-58390" not in {row["ref"] for row in rows}
