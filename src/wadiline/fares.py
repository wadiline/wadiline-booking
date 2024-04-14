"""Fare rules. Amounts are always whole piastres."""
from collections.abc import Mapping

from wadiline.models import Leg, NoFare, PassengerType, Trip


def adult_fare(fares: Mapping[tuple[str, str], int], trip: Trip, leg: Leg) -> int:
    start = trip.stops[leg.board].stop.code
    end = trip.stops[leg.alight].stop.code
    try:
        return fares[start, end]
    except KeyError:
        raise NoFare(f"No fare from {start} to {end} on {trip.route_code}.") from None


def price(adult_piastres: int, passenger_type: PassengerType) -> int:
    return adult_piastres
