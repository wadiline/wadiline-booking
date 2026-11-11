from datetime import UTC, date, datetime

import pytest

from wadiline.models import BadLeg, Leg, Stop, Trip, TripStop, UnknownStop


@pytest.fixture
def trip():
    at = datetime(2026, 11, 11, 10, tzinfo=UTC)
    stops = (Stop("CAI", "Cairo"), Stop("AST", "Assiut"), Stop("LXR", "Luxor"), Stop("ASW", "Aswan"))
    return Trip(1, "TST-0100", date(2026, 11, 11), "UPPER", 49,
                tuple(TripStop(i, stop, at) for i, stop in enumerate(stops)))


@pytest.mark.parametrize(("board", "alight"), [(0, 1), (1, 2), (0, 3)], ids=["single", "interior", "whole"])
def test_valid_leg(board, alight):
    leg = Leg(board, alight)
    assert (leg.board, leg.alight) == (board, alight)


@pytest.mark.parametrize(("board", "alight"), [(-1, 2), (1, 1), (2, 1)], ids=["negative", "equal", "reverse"])
def test_bad_leg(board, alight):
    with pytest.raises(BadLeg):
        Leg(board, alight)


@pytest.mark.parametrize(("query", "expected"), [("Cairo", 0), ("AST", 1), ("lUxOr", 2), ("Suez", None)],
                         ids=["name", "code", "mixed-case", "unknown"])
def test_stop_number(trip, query, expected):
    if expected is None:
        with pytest.raises(UnknownStop):
            trip.stop_number(query)
    else:
        assert trip.stop_number(query) == expected


@pytest.mark.parametrize(("start", "end", "outcome"), [
    ("CAI", "Luxor", Leg(0, 2)), ("ASW", "AST", BadLeg), ("CAI", "Suez", UnknownStop),
], ids=["valid", "reversed", "unknown"])
def test_trip_leg(trip, start, end, outcome):
    if isinstance(outcome, Leg):
        assert trip.leg(start, end) == outcome
    else:
        with pytest.raises(outcome):
            trip.leg(start, end)


def test_time_and_stop_name(trip):
    assert trip.time_at(1) == datetime(2026, 11, 11, 10, tzinfo=UTC)
    assert trip.stop_name(1) == "Assiut"
