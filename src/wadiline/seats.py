"""Seat checks. A ticket covers one leg, from the stop where its passenger boards to the stop
where they get off. Stops are numbered along the route from 0; see docs/rules/seats.md."""

from collections.abc import Iterable

from wadiline.models import Leg, Ticket, Trip


def legs_overlap(a: Leg, b: Leg) -> bool:
    """True when the two legs share any part of the road. Legs that only meet at a stop do not."""
    return a.board < b.alight and b.board < a.alight


def seat_free(trip: Trip, tickets: Iterable[Ticket], seat: int, leg: Leg) -> bool:
    """True when `seat` can be sold for `leg`: no sold ticket on that seat shares road with it."""
    if not 1 <= seat <= trip.seats:
        raise ValueError(f"Seat {seat} is not on {trip.code}.")
    return not any(
        legs_overlap(leg, ticket.leg)
        for ticket in tickets
        if ticket.trip_id == trip.id and ticket.seat == seat and ticket.status == "sold"
    )


def seat_map(trip: Trip, tickets: Iterable[Ticket], leg: Leg) -> dict[int, bool]:
    """Every seat on the trip, in order, mapped to True when it is free for `leg`."""
    tickets = list(tickets)
    return {seat: seat_free(trip, tickets, seat, leg) for seat in range(1, trip.seats + 1)}
