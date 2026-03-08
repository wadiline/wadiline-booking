"""SQLite storage for routes, timetable and bookings."""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, date, datetime
from importlib.resources import files
from pathlib import Path

from wadiline import fares
from wadiline.clock import from_db_time, to_db_time
from wadiline.models import (
    AlreadyCancelled,
    Booking,
    BookingNotFound,
    Leg,
    PassengerType,
    SeedError,
    Stop,
    Ticket,
    Trip,
    TripNotFound,
    TripStop,
    UnknownStop,
)
from wadiline.refunds import RefundShare, refund_piastres, refund_share

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"
SERVICE_DATE = "2024-09-15"


def db_path() -> Path:
    return Path(os.environ.get("WADILINE_DB", "var/wadiline.db"))


def connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def savepoint(conn, name):
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
        if conn.in_transaction:
            conn.execute(f"RELEASE {name}")
    except BaseException:
        if conn.in_transaction:
            conn.execute(f"ROLLBACK TO {name}")
            conn.execute(f"RELEASE {name}")
        raise


@contextmanager
def sample_transaction(conn):
    if conn.in_transaction:
        with savepoint(conn, "sample"):
            yield
        return

    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def reserve_writer(conn):
    """Take the SQLite write lock before reading stock for a write."""
    conn.execute("UPDATE meta SET value = value WHERE 0")


def migration_statements(text):
    start = 0
    for match in re.finditer(";", text):
        end = match.end()
        if sqlite3.complete_statement(text[start:end]):
            yield text[start:end]
            start = end
    tail = text[start:]
    if tail:
        yield tail


def migrate(conn, folder=None) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    if folder is None:
        folder = files("wadiline").joinpath("migrations")
    candidates = sorted((p for p in folder.iterdir() if re.fullmatch(r"\d{4}_[a-z0-9_]+\.sql", p.name)),
                        key=lambda p: p.name)
    applied = []
    refused = False

    def authorize(action, _arg1, _arg2, _database, _trigger):
        nonlocal refused
        if action in (sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT):
            refused = True
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    for path in candidates:
        with savepoint(conn, "migration"):
            conn.execute("UPDATE schema_migrations SET name = name WHERE 0")
            if conn.execute("SELECT 1 FROM schema_migrations WHERE name = ?", (path.name,)).fetchone():
                continue
            conn.set_authorizer(authorize)
            try:
                for statement in migration_statements(path.read_bytes().decode("utf-8")):
                    conn.execute(statement)
            except sqlite3.DatabaseError:
                if refused:
                    raise sqlite3.OperationalError(
                        f"{path.name}: remove BEGIN, COMMIT, END, ROLLBACK, SAVEPOINT and RELEASE. "
                        "Each migration already runs in its own transaction."
                    ) from None
                raise
            finally:
                conn.set_authorizer(None)
            conn.execute("INSERT INTO schema_migrations VALUES (?, ?)",
                         (path.name, to_db_time(datetime.now(UTC))))
            applied.append(path.name)
    return applied


def seed(conn, data_dir=SAMPLE_DIR, *, force=False) -> dict[str, int]:
    with sample_transaction(conn):
        migrate(conn)
        reserve_writer(conn)
        if conn.execute("SELECT 1 FROM trips LIMIT 1").fetchone() and not force:
            raise SeedError("The database already has data. Use --force to replace it.")
        data_dir = Path(data_dir)
        data = {name: json.loads((data_dir / f"{name}.json").read_bytes())
                for name in ("stops", "routes", "fares", "trips", "bookings")}
        for table in ("tickets", "bookings", "trip_stops", "trips", "fares",
                      "route_stops", "routes", "stops", "meta"):
            conn.execute(f"DELETE FROM {table}")
        conn.executemany("INSERT INTO stops VALUES (:code, :name)", data["stops"])
        for route in data["routes"]:
            conn.execute("INSERT INTO routes VALUES (?)", (route["code"],))
            conn.executemany("INSERT INTO route_stops VALUES (?, ?, ?)",
                             ((route["code"], n, stop) for n, stop in enumerate(route["stops"])))
        conn.executemany("INSERT INTO fares VALUES (:route, :from, :to, :adult_piastres)", data["fares"])
        for record in data["trips"]:
            trip_id = conn.execute(
                "INSERT INTO trips (code, service_date, route_code, seats) VALUES (?, ?, ?, ?)",
                (record["code"], record["service_date"], record["route"], record["seats"]),
            ).lastrowid
            conn.executemany("INSERT INTO trip_stops VALUES (?, ?, ?)", (
                (trip_id, i, to_db_time(datetime.fromisoformat(stop["time"])))
                for i, stop in enumerate(record["stops"])
            ))
        conn.executemany("INSERT INTO meta VALUES (?, ?)", (
            ("as_of", "2024-09-15T09:00:00Z"), ("service_date", SERVICE_DATE), ("sample_version", "1")))
        trips = {trip.code: trip for trip in list_trips(conn)}
        count = 0
        for row in data["bookings"]:
            conn.execute("INSERT INTO bookings VALUES (:ref, :sold_at, :channel, :email)", row)
            trip = trips[row["trip"]]
            for item in row["tickets"]:
                leg = trip.leg(item["from"], item["to"])
                conn.execute(
                    """INSERT INTO tickets (booking_ref, trip_id, seat, board, alight, passenger_name,
                    passenger_type, price_piastres, status, cancelled_at, refund_piastres)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["ref"], trip.id, item["seat"], leg.board, leg.alight, item["name"], item["type"],
                     item["price_piastres"], item["status"], item["cancelled_at"], item["refund_piastres"]))
                count += 1
        sizes = {name: len(data[name]) for name in ("stops", "routes", "trips", "bookings")}
        return {**sizes, "tickets": count}


def meta(conn, key) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise LookupError(f"No database value for {key}.")
    return row["value"]


def _trip(conn, row):
    stops = conn.execute(
        """SELECT s.code, s.name, ts.number, ts.time FROM trip_stops ts
        JOIN route_stops rs ON rs.route_code = ? AND rs.number = ts.number
        JOIN stops s ON s.code = rs.stop_code
        WHERE ts.trip_id = ? ORDER BY ts.number""", (row["route_code"], row["id"]))
    return Trip(row["id"], row["code"], date.fromisoformat(row["service_date"]), row["route_code"],
                row["seats"], tuple(TripStop(s["number"], Stop(s["code"], s["name"]),
                                           from_db_time(s["time"])) for s in stops))


def get_trip(conn, code, service_date=None) -> Trip:
    day = meta(conn, "service_date") if service_date is None else service_date
    row = conn.execute("SELECT * FROM trips WHERE code = ? AND service_date = ?", (code, str(day))).fetchone()
    if row is None:
        raise TripNotFound(f"No trip {code} on {day}.")
    return _trip(conn, row)


def trip_by_id(conn, trip_id) -> Trip:
    row = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if row is None:
        raise TripNotFound(f"No trip with ID {trip_id}.")
    return _trip(conn, row)


def list_trips(conn, from_stop=None, to_stop=None, service_date=None) -> list[Trip]:
    day = meta(conn, "service_date") if service_date is None else service_date
    trips = (_trip(conn, row) for row in conn.execute("SELECT * FROM trips WHERE service_date = ?", (str(day),)))
    matches = []
    for trip in trips:
        try:
            start = trip.stop_number(from_stop) if from_stop is not None else -1
            end = trip.stop_number(to_stop) if to_stop is not None else len(trip.stops)
        except UnknownStop:
            continue
        if start < end:
            matches.append(trip)
    return sorted(matches, key=lambda trip: (trip.time_at(0), trip.code))


def _ticket(row):
    return Ticket(row["id"], row["booking_ref"], row["trip_id"], row["seat"],
                  Leg(row["board"], row["alight"]), row["passenger_name"],
                  PassengerType(row["passenger_type"]), row["price_piastres"], row["status"],
                  from_db_time(row["cancelled_at"]) if row["cancelled_at"] else None,
                  row["refund_piastres"])


def live_tickets(conn, trip, seat=None) -> list[Ticket]:
    sql = "SELECT * FROM tickets WHERE trip_id = ? AND status = 'sold'"
    params = (trip.id,)
    if seat is not None:
        sql += " AND seat = ?"
        params += (seat,)
    return [_ticket(row) for row in conn.execute(sql + " ORDER BY seat, id", params)]


def get_booking(conn, ref) -> Booking:
    row = conn.execute("SELECT * FROM bookings WHERE ref = ?", (ref,)).fetchone()
    if row is None:
        raise BookingNotFound(f"No booking {ref}.")
    tickets = conn.execute("SELECT * FROM tickets WHERE booking_ref = ? ORDER BY seat, id", (ref,))
    return Booking(ref, from_db_time(row["sold_at"]), row["channel"], row["email"],
                   tuple(_ticket(ticket) for ticket in tickets))


def fare_table(conn, route_code):
    return {(r["from_code"], r["to_code"]): r["adult_piastres"] for r in conn.execute(
        "SELECT * FROM fares WHERE route_code = ?", (route_code,))}


def create_booking(conn, trip, seat, leg, passenger_name, passenger_type, channel, email, now) -> Booking:
    sold = to_db_time(now)
    reserve_writer(conn)
    amount = fares.price(fares.adult_fare(fare_table(conn, trip.route_code), trip, leg), passenger_type)
    highest = conn.execute("SELECT MAX(ref) FROM bookings").fetchone()[0]
    number = int(highest[3:]) + 1 if highest else 1
    ref = f"WL-{number:05d}"
    conn.execute("INSERT INTO bookings VALUES (?, ?, ?, ?)", (ref, sold, channel, email))
    conn.execute(
        """INSERT INTO tickets (booking_ref, trip_id, seat, board, alight, passenger_name,
        passenger_type, price_piastres) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ref, trip.id, seat, leg.board, leg.alight, passenger_name, passenger_type, amount))
    return get_booking(conn, ref)


def cancel_booking(conn, ref, now) -> tuple[RefundShare, int]:
    when = to_db_time(now)
    reserve_writer(conn)
    booking = get_booking(conn, ref)
    live = [t for t in booking.tickets if t.status == "sold"]
    if not live:
        raise AlreadyCancelled(f"Booking {ref} is already cancelled.")
    shares = []
    total = 0
    for ticket in live:
        departure = conn.execute("SELECT time FROM trip_stops WHERE trip_id = ? AND number = ?",
                                 (ticket.trip_id, ticket.leg.board)).fetchone()[0]
        share = refund_share(from_db_time(departure), now)
        value = refund_piastres(ticket.price_piastres, share)
        conn.execute("UPDATE tickets SET status = 'cancelled', cancelled_at = ?, refund_piastres = ? WHERE id = ?",
                     (when, value, ticket.id))
        shares.append(share)
        total += value
    return min(shares, key=(RefundShare.NONE, RefundShare.HALF, RefundShare.FULL).index), total
