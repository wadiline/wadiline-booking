"""Value objects used by the booking service."""
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class WadilineError(Exception):
    """An operation the booking service could not complete."""


class UnknownStop(WadilineError, ValueError):
    """A stop is not on the trip."""


class BadLeg(WadilineError, ValueError):
    """A journey must travel forward between different stops."""


class TripNotFound(WadilineError, LookupError):
    """No trip matches the code and service date."""


class BookingNotFound(WadilineError, LookupError):
    """No booking matches the reference."""


class NoFare(WadilineError, LookupError):
    """The requested leg has no fare."""


class SeedError(WadilineError):
    """The sample could not be loaded."""


class AlreadyCancelled(WadilineError):
    """Every ticket on the booking has already been cancelled."""


@dataclass(frozen=True, slots=True)
class Stop:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class Leg:
    board: int
    alight: int

    def __post_init__(self):
        if not 0 <= self.board < self.alight:
            raise BadLeg("A leg must travel forward between different stops.")


@dataclass(frozen=True, slots=True)
class TripStop:
    number: int
    stop: Stop
    time: datetime


@dataclass(frozen=True, slots=True)
class Trip:
    id: int
    code: str
    service_date: date
    route_code: str
    seats: int
    stops: tuple[TripStop, ...]

    def stop_number(self, name_or_code: str) -> int:
        key = name_or_code.casefold()
        for item in self.stops:
            if key in (item.stop.name.casefold(), item.stop.code.casefold()):
                return item.number
        raise UnknownStop(f"{name_or_code} is not a stop on {self.code}.")

    def leg(self, from_stop, to_stop) -> Leg:
        return Leg(self.stop_number(from_stop), self.stop_number(to_stop))

    def time_at(self, number: int) -> datetime:
        return self.stops[number].time

    def stop_name(self, number: int) -> str:
        return self.stops[number].stop.name


class PassengerType(StrEnum):
    ADULT = "adult"
    CHILD = "child"
    STUDENT = "student"


@dataclass(frozen=True, slots=True)
class Ticket:
    id: int
    booking_ref: str
    trip_id: int
    seat: int
    leg: Leg
    passenger_name: str
    passenger_type: PassengerType
    price_piastres: int
    status: str
    cancelled_at: datetime | None
    refund_piastres: int | None


@dataclass(frozen=True, slots=True)
class Booking:
    ref: str
    sold_at: datetime
    channel: str
    email: str | None
    tickets: tuple[Ticket, ...]

    @property
    def total_piastres(self) -> int:
        return sum(ticket.price_piastres for ticket in self.tickets if ticket.status == "sold")
