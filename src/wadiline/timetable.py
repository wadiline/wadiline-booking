"""Read timetable exports and add complete batches to the database."""
import json
from datetime import date, datetime

from wadiline import db
from wadiline.clock import to_db_time
from wadiline.models import TimetableError


def load_export(path) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as stream:
            records = json.load(stream)
    except (OSError, ValueError) as error:
        raise TimetableError(str(error)) from error
    if not isinstance(records, list):
        raise TimetableError("The export must be a list of trips.")
    return records


def _insert_trip(conn, record):
    code = record["code"]
    if not isinstance(code, str) or not code:
        raise ValueError("Trip code must be a non-empty string.")
    service_date = date.fromisoformat(record["service_date"]).isoformat()
    route = record["route"]
    if not isinstance(route, str):
        raise ValueError("Route code must be a string.")
    route_stops = [row[0] for row in conn.execute(
        "SELECT stop_code FROM route_stops WHERE route_code = ? ORDER BY number", (route,))]
    if not route_stops:
        raise ValueError(f"Unknown route {route}.")
    stops = [stop["stop"] for stop in record["stops"]]
    for stop in stops:
        if not isinstance(stop, str):
            raise ValueError("Stop code must be a string.")
        if conn.execute("SELECT 1 FROM stops WHERE code = ?", (stop,)).fetchone() is None:
            raise ValueError(f"Unknown stop {stop}.")
    if stops != route_stops:
        raise ValueError(f"Stops must follow route {route} in order.")
    times = [to_db_time(datetime.fromisoformat(stop["time"])) for stop in record["stops"]]
    if times != sorted(set(times)):
        raise ValueError("Stop times must increase.")
    if conn.execute("SELECT 1 FROM trips WHERE code = ? AND service_date = ?",
                    (code, service_date)).fetchone():
        raise ValueError("This trip code and service date already exist.")
    seats = record["seats"]
    if type(seats) is not int or not 1 <= seats <= 60:
        raise ValueError("The trip must have 1 to 60 seats.")
    fares = db.fare_table(conn, route)
    for index, start in enumerate(stops):
        for end in stops[index + 1:]:
            if (start, end) not in fares:
                raise ValueError(f"No fare from {start} to {end}.")
    cursor = conn.execute("INSERT INTO trips (code, service_date, route_code, seats) VALUES (?, ?, ?, ?)",
                          (code, service_date, route, seats))
    conn.executemany("INSERT INTO trip_stops VALUES (?, ?, ?)",
                     ((cursor.lastrowid, number, value) for number, value in enumerate(times)))


def import_trips(conn, records) -> int:
    count = 0
    with db.savepoint(conn, "timetable"):
        db.reserve_writer(conn)
        for record in records:
            if not isinstance(record, dict):
                raise TimetableError("? ?: A trip must be an object.")
            try:
                _insert_trip(conn, record)
            except (KeyError, TypeError, ValueError) as error:
                raise TimetableError(f"{record.get('code', '?')} {record.get('service_date', '?')}: {error}") from error
            count += 1
    return count
