import pytest

from wadiline import db, fares
from wadiline.models import NoFare, PassengerType

PRICES = [
    ("ALX-0700", "CAI", "ALX", 26000, 13000, 19500),
    ("HRG-0830", "CAI", "HRG", 64000, 32000, 48000),
    ("SSH-2300", "CAI", "SSH", 72000, 36000, 54000),
    ("LXR-0800", "HRG", "LXR", 32000, 16000, 24000),
    ("ASW-0700", "CAI", "AST", 42000, 21000, 31500),
    ("ASW-0700", "CAI", "LXR", 78000, 39000, 58500),
    ("ASW-0700", "CAI", "ASW", 92000, 46000, 69000),
    ("ASW-0700", "AST", "LXR", 38000, 19000, 28500),
    ("ASW-0700", "AST", "ASW", 56000, 28000, 42000),
    ("ASW-0700", "LXR", "ASW", 24000, 12000, 18000),
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
