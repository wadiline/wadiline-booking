import json
import shutil
import sqlite3
from contextlib import closing
from datetime import date, timedelta

import pytest

from wadiline import db
from wadiline.models import (
    AlreadyCancelled,
    BookingNotFound,
    PassengerType,
    SeedError,
    TripNotFound,
)
from wadiline.refunds import RefundShare


def test_schema_is_safe_to_run_twice(tmp_path):
    with closing(db.connect(tmp_path / "test.db")) as conn:
        db.migrate(conn)
        db.migrate(conn)
        assert conn.execute("SELECT count(*) FROM trips").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


@pytest.mark.parametrize("case", ["counts", "refusal", "force", "failed-replacement"])
def test_seed(tmp_path, conn, case):
    expected = {"stops": 2, "routes": 1, "trips": 2, "bookings": 1, "tickets": 1}
    if case == "refusal":
        with pytest.raises(SeedError, match="Use force=True"):
            db.seed(conn)
    elif case == "force":
        with conn:
            conn.execute("DELETE FROM tickets")
        assert db.seed(conn, force=True) == expected
        assert conn.execute("SELECT count(*) FROM tickets").fetchone()[0] == expected["tickets"]
    elif case == "failed-replacement":
        folder = tmp_path / "bad"
        shutil.copytree(db.SAMPLE_DIR, folder)
        rows = json.loads((folder / "bookings.json").read_bytes())
        rows.append(rows[0].copy())
        (folder / "bookings.json").write_text(json.dumps(rows), encoding="utf-8")
        with pytest.raises(sqlite3.IntegrityError):
            db.seed(conn, folder, force=True)
        ref = "WL-58001"
        assert db.get_booking(conn, ref).ref == ref
        assert conn.execute("SELECT count(*) FROM tickets").fetchone()[0] == expected["tickets"]
    else:
        with closing(db.connect(tmp_path / "new.db")) as empty:
            assert db.seed(empty) == expected
            assert db.meta(empty, "as_of") == "2024-09-15T09:00:00Z"
            assert db.meta(empty, "service_date") == "2024-09-15"
            assert db.meta(empty, "sample_version") == "1"


@pytest.mark.parametrize("case", ["default", "explicit", "missing", "order", "forward", "reverse"])
def test_trips(conn, case):
    code = "ALX-0700"
    if case == "default":
        assert db.get_trip(conn, code).service_date == date(2024, 9, 15)
    elif case == "explicit":
        assert db.get_trip(conn, code, date(2024, 9, 15)).id == 1
        assert not db.list_trips(conn, service_date=date(2024, 9, 16))
    elif case == "missing":
        with pytest.raises(TripNotFound):
            db.get_trip(conn, code, date(2024, 9, 16))
    elif case == "order":
        assert [t.code for t in db.list_trips(conn)] == ["ALX-0700", "ALX-1500"]
    elif case == "forward":
        assert [t.code for t in db.list_trips(conn, "cai", "aLeXaNdRiA")] == ["ALX-0700", "ALX-1500"]
    else:
        assert db.list_trips(conn, "Alexandria", "Cairo") == []


@pytest.mark.parametrize("case", ["reference", "priced-row", "caller-rollback"])
def test_create(conn, clock, case):
    trip = db.get_trip(conn, "ALX-1500")
    leg = trip.leg("CAI", "ALX")
    with conn:
        record = db.create_booking(conn, trip, 44, leg, "Adham Gabr", PassengerType.ADULT, "counter", None, clock.now())
        if case == "caller-rollback":
            conn.rollback()
    if case == "reference":
        assert record.ref == "WL-58002"
    elif case == "priced-row":
        saved = db.get_booking(conn, record.ref)
        assert saved.sold_at == clock.now() and saved.tickets[0].price_piastres == 26000
        assert saved.tickets[0].leg == leg
    else:
        with pytest.raises(BookingNotFound):
            db.get_booking(conn, record.ref)


@pytest.mark.parametrize("case", ["already-cancelled", "missing"])
def test_cancel(conn, clock, case):
    if case == "missing":
        with pytest.raises(BookingNotFound), conn:
            db.cancel_booking(conn, "WL-99999", clock.now())
        return
    with conn:
        share, value = db.cancel_booking(conn, "WL-58001", clock.now() - timedelta(days=2))
    assert (share, value) == (RefundShare.FULL, 26000)
    with pytest.raises(AlreadyCancelled), conn:
        db.cancel_booking(conn, "WL-58001", clock.now())
