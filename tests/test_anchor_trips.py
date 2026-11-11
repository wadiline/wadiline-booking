from datetime import datetime

import pytest

from wadiline import db
from wadiline.models import Leg
from wadiline.seats import seat_is_free

ROSTER = [
    ("WL-58117", "Ali Badawi", 22, Leg(0, 2), "adult", 78000, "web", "2026-11-02T09:05:00Z"),
    ("WL-58214", "Nourhan Elsayed", 14, Leg(2, 3), "adult", 24000, "app", "2026-11-08T18:14:00Z"),
    ("WL-58262", "Yasmin Hosny", 22, Leg(2, 3), "student", 18000, "app", "2026-11-11T08:52:00Z"),
]
REFS = [row[0] for row in ROSTER]


@pytest.mark.parametrize("story", ROSTER, ids=REFS)
def test_story_identity(conn, story):
    ref, name, _, _, kind, *_ = story
    booking = db.get_booking(conn, ref)
    assert booking.email == name.lower().replace(" ", ".") + "@inbox.example"
    assert len(booking.tickets) == 1
    ticket = booking.tickets[0]
    assert (ticket.passenger_name, ticket.passenger_type) == (name, kind)


@pytest.mark.parametrize("story", ROSTER, ids=REFS)
def test_story_journey(conn, story):
    ref, _, seat, leg, _, *_ = story
    ticket = db.get_booking(conn, ref).tickets[0]
    trip = db.get_trip(conn, "ASW-2200")
    assert (ticket.trip_id, ticket.seat, ticket.leg) == (trip.id, seat, leg)


@pytest.mark.parametrize("story", ROSTER, ids=REFS)
def test_story_sale(conn, story):
    ref, _, _, _, _, price, channel, at = story
    booking = db.get_booking(conn, ref)
    assert (booking.total_piastres, booking.channel, booking.sold_at) == (
        price, channel, datetime.fromisoformat(at))


@pytest.mark.parametrize("case", ["capacity", "seat-14", "seat-22", "seats-9-10",
                                 "seats-30-31", "other-43", "after-luxor"])
def test_night_layout(conn, case):
    trip = db.get_trip(conn, "ASW-2200")
    tickets = db.live_tickets(conn, trip)
    layout = {}
    for ticket in tickets:
        layout.setdefault(ticket.seat, set()).add(ticket.leg)
    if case == "capacity":
        assert trip.seats == 49 and len(tickets) == 54
    elif case == "after-luxor":
        assert {t.seat for t in tickets if 2 in range(t.leg.board, t.leg.alight)} == set(range(1, 50))
    else:
        seats, legs = {
            "seat-14": ({14}, {Leg(2, 3)}), "seat-22": ({22}, {Leg(0, 2), Leg(2, 3)}),
            "seats-9-10": ({9, 10}, {Leg(0, 1), Leg(1, 3)}),
            "seats-30-31": ({30, 31}, {Leg(0, 2), Leg(2, 3)}),
            "other-43": (set(range(1, 50)) - {9, 10, 14, 22, 30, 31}, {Leg(0, 3)}),
        }[case]
        assert all(layout[seat] == legs for seat in seats)


def test_seat_14_is_taken_from_cairo_to_aswan(conn):
    trip = db.get_trip(conn, "ASW-2200")
    assert seat_is_free(trip, db.live_tickets(conn, trip), 14, trip.leg("Cairo", "Aswan")) is False


def test_seat_22_sells_again_from_luxor(conn):
    trip = db.get_trip(conn, "ASW-2200")
    ali = db.get_booking(conn, "WL-58117").tickets[0]
    assert seat_is_free(trip, [ali], 22, trip.leg("Luxor", "Aswan")) is True
