from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from wadiline.models import Leg, PassengerType, Stop, Ticket, Trip, TripStop
from wadiline.seats import seat_free, seat_map


@pytest.fixture
def trip():
    start = datetime(2024, 2, 18, 1, tzinfo=UTC)
    stops = [Stop("CAI", "Cairo"), Stop("AST", "Assiut"), Stop("LXR", "Luxor"), Stop("ASW", "Aswan")]
    return Trip(1, "TST-0100", date(2024, 2, 18), "UPPER", 49, tuple(
        TripStop(i, stop, start + timedelta(hours=i)) for i, stop in enumerate(stops)))


def sold(trip, leg):
    return Ticket(1, "WL-58001", trip.id, 5, leg, "Adham Gabr", PassengerType.ADULT, 24000,
                  "sold", None, None)


@pytest.mark.parametrize(("old", "new", "clash"), [
    ((0, 3), (2, 3), True), ((0, 2), (1, 3), True), ((1, 3), (1, 2), True),
    ((2, 3), (0, 3), True), ((1, 3), (0, 2), True), ((2, 3), (1, 3), True),
    ((0, 2), (2, 3), False), ((2, 3), (0, 2), False), ((0, 1), (1, 3), False),
    ((0, 3), (0, 3), True), ((0, 1), (2, 3), False), ((2, 3), (0, 1), False),
], ids="A1 A2 A3 B1 B2 B3 C1 C2 C3 D1 E1 E2".split())
def test_seat_case(trip, old, new, clash):
    assert seat_free(trip, [sold(trip, Leg(*old))], 5, Leg(*new)) is not clash


@pytest.mark.parametrize("seat", [-1, 0, 50, 99])
def test_invalid_seat(trip, seat):
    with pytest.raises(ValueError, match=f"Seat {seat} is not on TST-0100."):
        seat_free(trip, [], seat, Leg(0, 1))


@pytest.mark.parametrize("seat", [1, 49])
def test_valid_edge(trip, seat):
    assert seat_free(trip, [], seat, Leg(0, 1))


@pytest.mark.parametrize("override", [{"status": "cancelled"}, {"seat": 6}, {"trip_id": 2}],
                         ids=["cancelled", "other-seat", "other-trip"])
def test_ignored_ticket(trip, override):
    leg = Leg(0, 2)
    assert seat_free(trip, [replace(sold(trip, leg), **override)], 5, leg)


@pytest.mark.parametrize("part", ["order", "size", "free", "taken"])
def test_map_contract(trip, part):
    leg = Leg(0, 1)
    slots = seat_map(trip, [sold(trip, leg)], leg)
    if part == "order":
        assert list(slots) == list(range(1, 50))
    elif part == "size":
        assert len(slots) == 49
    elif part == "free":
        assert slots[6] is True
    else:
        assert slots[5] is False


@pytest.mark.parametrize("kind", ["empty", "iterator"])
def test_ticket_input(trip, kind):
    leg = Leg(0, 1)
    records = [] if kind == "empty" else iter([sold(trip, leg)])
    assert seat_free(trip, records, 5, leg) is (kind == "empty")


@pytest.mark.parametrize(("old_end", "new_end"), [(2, 2), (1, 2), (2, 1)],
                         ids=["equal", "old-shorter", "new-shorter"])
def test_same_board(trip, old_end, new_end):
    assert seat_free(trip, [sold(trip, Leg(0, old_end))], 5, Leg(0, new_end)) is False
