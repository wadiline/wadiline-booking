"""Station commands for the booking service."""
import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import date
from itertools import groupby
from pathlib import Path

from wadiline import db, timetable
from wadiline.clock import cairo
from wadiline.models import BookingNotFound, SeedError, TimetableError, TripNotFound
from wadiline.money import format_egp
from wadiline.seats import seat_free, seat_map

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def local_time(value):
    stamp = cairo(value)
    return f"{stamp.day} {MONTHS[stamp.month - 1]} {stamp:%H:%M}"


def header(trip):
    last = len(trip.stops) - 1
    return (f"{trip.code}  {trip.stop_name(0)} {local_time(trip.time_at(0))} -> "
            f"{trip.stop_name(last)} {local_time(trip.time_at(last))}")


def compact(seats):
    ranges = []
    for _, group in groupby(enumerate(seats), key=lambda pair: pair[1] - pair[0]):
        values = [seat for _, seat in group]
        ranges.append(str(values[0]) if len(values) == 1 else f"{values[0]}-{values[-1]}")
    return ", ".join(ranges) or "none"


def show_trips(conn, args):
    for trip in db.list_trips(conn, args.from_stop, args.to_stop, args.date):
        stops = " -> ".join(stop.stop.name for stop in trip.stops)
        print(f"{trip.code}  {local_time(trip.time_at(0))}  {stops}")


def show_seats(conn, args):
    trip = db.get_trip(conn, args.trip, args.date)
    leg = trip.leg(args.from_stop, args.to_stop)
    tickets = db.live_tickets(conn, trip)
    route = f"{trip.stop_name(leg.board)} -> {trip.stop_name(leg.alight)}"
    if args.seat is not None:
        free = seat_free(trip, tickets, args.seat, leg)
        print(f"Seat {args.seat} is {'free' if free else 'taken'} for {route}.")
        return
    slots = seat_map(trip, tickets, leg)
    free = [seat for seat in slots if slots[seat]]
    taken = [seat for seat in slots if not slots[seat]]
    print(header(trip))
    print(f"Seats for {route}")
    print(f"Free ({len(free)}): {compact(free)}")
    print(f"Taken ({len(taken)}): {compact(taken)}")


def ticket_line(trip, ticket):
    start, end = ticket.leg.board, ticket.leg.alight
    return (f"{ticket.booking_ref}  {trip.stop_name(start)} {local_time(trip.time_at(start))} -> "
            f"{trip.stop_name(end)} {local_time(trip.time_at(end))}  "
            f"{ticket.passenger_type}  {format_egp(ticket.price_piastres)}  {ticket.passenger_name}")


def show_tickets(conn, args):
    trip = db.get_trip(conn, args.trip, args.date)
    if args.seat is not None and not 1 <= args.seat <= trip.seats:
        raise ValueError(f"Seat {args.seat} is not on {trip.code}.")
    tickets = db.live_tickets(conn, trip, args.seat)
    print(header(trip))
    prefix = f"Seat {args.seat}: " if args.seat is not None else ""
    print(f"{prefix}{len(tickets)} {'ticket' if len(tickets) == 1 else 'tickets'}")
    for ticket in tickets:
        print(ticket_line(trip, ticket))


def show_booking(conn, args):
    booking = db.get_booking(conn, args.ref)
    print(f"{booking.ref}  sold {local_time(booking.sold_at)}  {booking.channel}  "
          f"{format_egp(booking.total_piastres)}")
    for ticket in booking.tickets:
        print(ticket_line(db.trip_by_id(conn, ticket.trip_id), ticket))


def import_timetable(conn, args):
    count = timetable.import_trips(conn, timetable.load_export(args.path))
    print(f"Imported {count} {'trip' if count == 1 else 'trips'} from {args.path}.")


def parser():
    result = argparse.ArgumentParser(prog="python -m wadiline")
    result.add_argument("--db", metavar="PATH")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("seed").add_argument("--force", action="store_true")
    trips = commands.add_parser("trips")
    trips.add_argument("--from", dest="from_stop")
    trips.add_argument("--to", dest="to_stop")
    trips.add_argument("--date", type=date.fromisoformat)
    seats = commands.add_parser("seats")
    seats.add_argument("--from", dest="from_stop", required=True)
    seats.add_argument("--to", dest="to_stop", required=True)
    tickets = commands.add_parser("tickets")
    for command in (seats, tickets):
        command.add_argument("trip")
        command.add_argument("--seat", type=int)
        command.add_argument("--date", type=date.fromisoformat)
    commands.add_parser("booking").add_argument("ref")
    commands.add_parser("import-timetable").add_argument("path")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    path = Path(args.db) if args.db is not None else db.db_path()
    try:
        if args.command == "seed":
            path.parent.mkdir(parents=True, exist_ok=True)
            with closing(db.connect(path)) as conn:
                sizes = db.seed(conn, force=args.force)
            counts = ", ".join(f"{count} {name}" for name, count in sizes.items())
            shown = args.db if args.db is not None else path.as_posix()
            print(f"Seeded {shown}: {counts}.")
            return 0
        if not path.is_file():
            print(f"No database at {path.as_posix()}. Run seed first.", file=sys.stderr)
            return 4
        with closing(db.connect(path)) as conn:
            try:
                db.meta(conn, "service_date")
            except (sqlite3.OperationalError, LookupError):
                print("The database is not seeded. Run seed first.", file=sys.stderr)
                return 4
            command = {"trips": show_trips, "seats": show_seats, "tickets": show_tickets,
                       "booking": show_booking, "import-timetable": import_timetable}
            command[args.command](conn, args)
    except TimetableError as exc:
        print(f"Import stopped: {exc}", file=sys.stderr)
        return 1
    except (TripNotFound, BookingNotFound) as exc:
        print(exc, file=sys.stderr)
        return 3
    except (ValueError, SeedError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0
