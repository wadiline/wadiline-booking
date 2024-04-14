from datetime import UTC, date, datetime

import pytest

from wadiline import fares
from wadiline.models import Leg, NoFare, PassengerType, Stop, Trip, TripStop


def test_adult_fare_keeps_the_piastres():
    day = date(2024, 4, 14)
    board = TripStop(0, Stop("CAI", "Cairo"), datetime(2024, 4, 14, 5, tzinfo=UTC))
    alight = TripStop(1, Stop("ALX", "Alexandria"), datetime(2024, 4, 14, 8, tzinfo=UTC))
    trip = Trip(1, "ALX-0700", day, "ALEX", 49, (board, alight))
    published = {("CAI", "ALX"): 26000}

    adult = fares.adult_fare(published, trip, Leg(0, 1))
    assert fares.price(adult, PassengerType.ADULT) == 26000

    return_trip = Trip(2, "CAI-0700", day, "ALEX", 49,
                       (TripStop(0, alight.stop, board.time), TripStop(1, board.stop, alight.time)))
    with pytest.raises(NoFare, match="No fare from ALX to CAI"):
        fares.adult_fare(published, return_trip, Leg(0, 1))
