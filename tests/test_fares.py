import pytest

from wadiline import db, fares
from wadiline.models import NoFare, PassengerType

PRICES = [
    ("ALX-0700", "CAI", "ALX", 26000, 13000, 19500),
]


@pytest.mark.parametrize("row", PRICES, ids=[f"{a}-{b}" for _, a, b, *_ in PRICES])
@pytest.mark.parametrize("kind", list(PassengerType))
def test_published_price(conn, row, kind):
    code, start, end, *expected = row
    trip = db.get_trip(conn, code)
    prices = db.fare_table(conn, trip.route_code)
    adult = fares.adult_fare(prices, trip, trip.leg(start, end))
    assert fares.price(adult, kind) == expected[list(PassengerType).index(kind)]


def test_missing_fare(conn):
    trip = db.get_trip(conn, "ALX-0700")
    with pytest.raises(NoFare):
        fares.adult_fare({}, trip, trip.leg("CAI", "ALX"))


def test_reverse_fare(conn):
    trip = db.get_trip(conn, "ALX-0700")
    with pytest.raises(NoFare):
        fares.adult_fare({("ALX", "CAI"): 26000}, trip, trip.leg("CAI", "ALX"))
