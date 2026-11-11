import json

import pytest

from wadiline import db, timetable
from wadiline.models import TimetableError, TripNotFound


def record(code="TEST-0700", date="2026-11-12"):
    return {"code": code, "route": "ALEX", "service_date": date, "seats": 49,
            "stops": [{"stop": "CAI", "time": f"{date}T07:00:00+02:00"},
                      {"stop": "ALX", "time": f"{date}T10:00:00+02:00"}]}


@pytest.mark.parametrize("case", ["load-file", "insert", "same-code-new-date"])
def test_good_export(conn, tmp_path, case):
    row = record("ALX-0700" if case == "same-code-new-date" else "TEST-0700")
    if case == "load-file":
        path = tmp_path / "export.json"
        path.write_text(json.dumps([row]), encoding="utf-8")
        assert timetable.load_export(path) == [row]
    else:
        assert timetable.import_trips(conn, [row]) == 1
        assert [t.code for t in db.list_trips(conn, service_date="2026-11-12")] == [row["code"]]
        assert len(db.list_trips(conn)) == 8


@pytest.mark.parametrize(("case", "message"), [
    ("route", "Unknown route"), ("stop", "Unknown stop"), ("order", "in order"),
    ("time", "must increase"), ("existing", "already exist"), ("batch", "already exist"),
    ("zero", "1 to 60"), ("over", "1 to 60"), ("fare", "No fare"),
])
def test_reject_record(conn, case, message):
    row = record()
    records = [row]
    if case == "route":
        row["route"] = "MISSING"
    elif case == "stop":
        row["stops"][0]["stop"] = "MISSING"
    elif case == "order":
        row["stops"].reverse()
    elif case == "time":
        row["stops"][1]["time"] = row["stops"][0]["time"]
    elif case == "existing":
        row = record("ALX-0700", "2026-11-11")
        records = [row]
    elif case == "batch":
        records.append(row.copy())
    elif case == "zero":
        row["seats"] = 0
    elif case == "over":
        row["seats"] = 61
    else:
        with conn:
            conn.execute("DELETE FROM fares WHERE route_code='ALEX'")
    with pytest.raises(TimetableError, match=f"{row['code']} {row['service_date']}: .*{message}"):
        timetable.import_trips(conn, records)


@pytest.mark.parametrize("case", ["bad-first", "bad-last", "preserves", "retry"])
def test_atomic_import(conn, case):
    good, bad = record(), record("TEST-BAD")
    bad["seats"] = 61
    records = [bad, good] if case == "bad-first" else [good, bad]
    with pytest.raises(TimetableError, match="TEST-BAD"):
        timetable.import_trips(conn, records)
    with pytest.raises(TripNotFound):
        db.get_trip(conn, good["code"], good["service_date"])
    if case == "preserves":
        assert len(db.list_trips(conn)) == 8
    if case == "retry":
        bad["seats"] = 49
        assert timetable.import_trips(conn, records) == 2
        assert len(db.list_trips(conn, service_date=good["service_date"])) == 2
