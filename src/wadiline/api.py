"""HTTP endpoints for the booking service."""
import sqlite3
from contextlib import closing
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from wadiline import db
from wadiline.clock import Clock, SystemClock, cairo
from wadiline.models import (
    AlreadyCancelled,
    BadLeg,
    BookingNotFound,
    PassengerType,
    TripNotFound,
    UnknownStop,
)
from wadiline.money import format_egp
from wadiline.seats import seat_free, seat_map

app = FastAPI(title="Wadiline booking API", version="1.4.0")


def get_db():
    with closing(db.connect(db.db_path())) as conn:
        yield conn


def get_clock() -> Clock:
    return SystemClock()


Connection = Annotated[sqlite3.Connection, Depends(get_db)]
RequestClock = Annotated[Clock, Depends(get_clock)]
From = Annotated[str, Query(alias="from")]
To = Annotated[str, Query(alias="to")]
OptionalFrom = Annotated[str | None, Query(alias="from")]
OptionalTo = Annotated[str | None, Query(alias="to")]


class Passenger(BaseModel):
    name: str = Field(min_length=1)
    type: PassengerType


class BookingBody(BaseModel):
    seat: int
    from_stop: str = Field(alias="from")
    to_stop: str = Field(alias="to")
    passenger: Passenger
    email: str | None = None


def error(status, code, message):
    return HTTPException(status, detail={"code": code, "message": message})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={
        "detail": {"code": "bad_request", "message": exc.errors()[0]["msg"]},
    })


def trip_payload(trip):
    return {
        "code": trip.code, "date": trip.service_date.isoformat(), "route": trip.route_code,
        "stops": [{"name": stop.stop.name, "time": cairo(stop.time).isoformat()} for stop in trip.stops],
    }


def ticket_payload(trip, ticket):
    return {
        "trip": trip.code, "date": trip.service_date.isoformat(), "seat": ticket.seat,
        "from": trip.stop_name(ticket.leg.board), "to": trip.stop_name(ticket.leg.alight),
        "passenger": {"name": ticket.passenger_name, "type": ticket.passenger_type},
        "price_piastres": ticket.price_piastres, "price": format_egp(ticket.price_piastres),
    }


def find_trip(conn, code, day=None):
    try:
        return db.get_trip(conn, code, day)
    except TripNotFound as exc:
        raise error(404, "trip_not_found", str(exc)) from exc


def find_leg(trip, start, end):
    try:
        return trip.leg(start, end)
    except UnknownStop as exc:
        raise error(422, "unknown_stop", str(exc)) from exc
    except BadLeg as exc:
        raise error(422, "bad_leg", str(exc)) from exc


@app.get("/trips")
def trips(conn: Connection, from_stop: OptionalFrom = None, to_stop: OptionalTo = None, date: date | None = None):
    return [trip_payload(trip) for trip in db.list_trips(conn, from_stop, to_stop, date)]


@app.get("/trips/{trip_code}")
def trip_details(trip_code: str, conn: Connection, date: date | None = None):
    return trip_payload(find_trip(conn, trip_code, date))


@app.get("/trips/{trip_code}/seats")
def seats(trip_code: str, from_stop: From, to_stop: To, conn: Connection, date: date | None = None):
    trip = find_trip(conn, trip_code, date)
    leg = find_leg(trip, from_stop, to_stop)
    slots = seat_map(trip, db.live_tickets(conn, trip), leg)
    return {
        "trip": trip.code, "date": trip.service_date.isoformat(),
        "from": trip.stop_name(leg.board), "to": trip.stop_name(leg.alight),
        "free": [seat for seat in slots if slots[seat]],
        "taken": [seat for seat in slots if not slots[seat]],
    }


@app.post("/trips/{trip_code}/bookings", status_code=201)
def book(trip_code: str, body: BookingBody, conn: Connection, clock: RequestClock):
    with conn:
        db.reserve_writer(conn)
        trip = find_trip(conn, trip_code)
        leg = find_leg(trip, body.from_stop, body.to_stop)
        if not 1 <= body.seat <= trip.seats:
            raise error(422, "bad_request", f"Seat {body.seat} is not on {trip.code}.")
        if not seat_free(trip, db.live_tickets(conn, trip), body.seat, leg):
            start, end = trip.stop_name(leg.board), trip.stop_name(leg.alight)
            raise error(409, "seat_taken", f"Seat {body.seat} is taken for part of {start} to {end}.")
        booking = db.create_booking(conn, trip, body.seat, leg, body.passenger.name,
                                    body.passenger.type, channel="counter", email=body.email,
                                    now=clock.now())
    return {"ref": booking.ref, **ticket_payload(trip, booking.tickets[0])}


@app.get("/bookings/{ref}")
def booking_details(ref: str, conn: Connection):
    try:
        booking = db.get_booking(conn, ref)
    except BookingNotFound as exc:
        raise error(404, "booking_not_found", str(exc)) from exc
    tickets = []
    for ticket in booking.tickets:
        trip = db.trip_by_id(conn, ticket.trip_id)
        tickets.append({
            **ticket_payload(trip, ticket), "status": ticket.status,
            "cancelled_at": cairo(ticket.cancelled_at).isoformat() if ticket.cancelled_at else None,
            "refund_piastres": ticket.refund_piastres,
        })
    return {"ref": booking.ref, "sold_at": cairo(booking.sold_at).isoformat(),
            "channel": booking.channel, "total_piastres": booking.total_piastres, "tickets": tickets}


@app.post("/bookings/{ref}/cancel")
def cancel(ref: str, conn: Connection, clock: RequestClock):
    try:
        with conn:
            share, amount = db.cancel_booking(conn, ref, clock.now())
    except BookingNotFound as exc:
        raise error(404, "booking_not_found", str(exc)) from exc
    except AlreadyCancelled as exc:
        raise error(409, "already_cancelled", str(exc)) from exc
    return {"ref": ref, "share": share, "refund_piastres": amount, "refund": format_egp(amount)}
