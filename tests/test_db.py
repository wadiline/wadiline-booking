import json
import shutil
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

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


@pytest.mark.parametrize("case", ["initial", "rerun", "discover", "rollback"])
def test_migration(tmp_path, case):
    folder = tmp_path / "migrations"
    folder.mkdir()
    packaged = Path(__file__).resolve().parents[1] / "src" / "wadiline" / "migrations"
    first = ["0001_base.sql", "0002_holds.sql"]
    for name in first:
        shutil.copyfile(packaged / name, folder / name)
    with closing(db.connect(tmp_path / "test.db")) as conn:
        assert db.migrate(conn, folder) == first
        if case == "initial":
            assert [r[0] for r in conn.execute("SELECT name FROM schema_migrations ORDER BY rowid")] == first
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        elif case == "rerun":
            original = conn.execute("SELECT * FROM schema_migrations ORDER BY rowid").fetchall()
            assert db.migrate(conn, folder) == []
            assert conn.execute("SELECT * FROM schema_migrations ORDER BY rowid").fetchall() == original
        elif case == "discover":
            (folder / "1001_extra.sql").write_text("CREATE TABLE extra (id INTEGER);\n", encoding="utf-8")
            (folder / "007_other.sql").write_text("not SQL", encoding="utf-8")
            assert db.migrate(conn, folder) == ["1001_extra.sql"]
            assert not conn.execute("SELECT * FROM extra").fetchall()
        else:
            (folder / "0003_extra.sql").write_text("CREATE TABLE extra (id INTEGER);\nNOT SQL;\n", encoding="utf-8")
            with pytest.raises(sqlite3.OperationalError):
                db.migrate(conn, folder)
            assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='extra'").fetchone()
            assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == len(first)


@pytest.mark.parametrize("case", ["counts", "refusal", "force", "failed-replacement"])
def test_seed(tmp_path, conn, case):
    expected = {"stops": 7, "routes": 5, "trips": 8, "bookings": 263, "tickets": 313}
    if case == "refusal":
        with pytest.raises(SeedError, match="Use --force"):
            db.seed(conn)
    elif case == "force":
        trip = db.get_trip(conn, "ASW-0700")
        leg = trip.leg("LXR", "ASW")
        with conn:
            conn.execute("INSERT INTO holds VALUES (1, ?, 45, ?, ?, 'app', ?, ?, NULL)",
                         (trip.id, leg.board, leg.alight, "2026-11-11T10:00:00Z",
                          "2026-11-11T10:10:00Z"))
        assert db.seed(conn, force=True) == expected
        assert conn.execute("SELECT count(*) FROM holds").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM tickets").fetchone()[0] == expected["tickets"]
    elif case == "failed-replacement":
        folder = tmp_path / "bad"
        shutil.copytree(db.SAMPLE_DIR, folder)
        rows = json.loads((folder / "bookings.json").read_bytes())
        rows[-1]["ref"] = rows[0]["ref"]
        (folder / "bookings.json").write_text(json.dumps(rows), encoding="utf-8")
        with pytest.raises(sqlite3.IntegrityError):
            db.seed(conn, folder, force=True)
        ref = "WL-58263"
        assert db.get_booking(conn, ref).ref == ref
        assert conn.execute("SELECT count(*) FROM tickets").fetchone()[0] == expected["tickets"]
    else:
        with closing(db.connect(tmp_path / "new.db")) as empty:
            assert db.seed(empty) == expected
            assert db.meta(empty, "as_of") == "2026-11-11T10:00:00Z"
            assert db.meta(empty, "service_date") == "2026-11-11"
            assert db.meta(empty, "sample_version") == "2"


@pytest.mark.parametrize("case", ["default", "explicit", "missing", "order", "forward", "reverse"])
def test_trips(conn, case):
    code = "ASW-0700"
    if case == "default":
        assert db.get_trip(conn, code).service_date == date(2026, 11, 11)
    elif case == "explicit":
        assert db.get_trip(conn, code, date(2026, 11, 11)).id == 7
        assert not db.list_trips(conn, service_date=date(2026, 11, 12))
    elif case == "missing":
        with pytest.raises(TripNotFound):
            db.get_trip(conn, code, date(2026, 11, 12))
    elif case == "order":
        order = [
            "ALX-0700", "ASW-0700", "LXR-0800", "HRG-0830",
            "ALX-1500", "ALX-1900", "ASW-2200", "SSH-2300"]
        assert [t.code for t in db.list_trips(conn)] == order
    elif case == "forward":
        assert [t.code for t in db.list_trips(conn, "cai", "lUxOr")] == ["ASW-0700", "ASW-2200"]
    else:
        assert db.list_trips(conn, "Luxor", "Cairo") == []


@pytest.mark.parametrize("case", ["live-order", "seat-filter", "booking-total", "fares"])
def test_reads(conn, case):
    trip = db.get_trip(conn, "ASW-2200")
    if case == "live-order":
        tickets = db.live_tickets(conn, trip)
        pairs = [(t.seat, t.id) for t in tickets]
        assert len(pairs) == 54 and pairs == sorted(pairs)
        assert all(t.status == "sold" for t in tickets)
    elif case == "seat-filter":
        assert [t.booking_ref for t in db.live_tickets(conn, trip, 14)] == ["WL-58214"]
    elif case == "booking-total":
        assert db.get_booking(conn, "WL-58214").total_piastres == 24000
    else:
        assert db.fare_table(conn, "UPPER") == {
            ("CAI", "AST"): 42000, ("CAI", "LXR"): 78000, ("CAI", "ASW"): 92000,
            ("AST", "LXR"): 38000, ("AST", "ASW"): 56000, ("LXR", "ASW"): 24000}


@pytest.mark.parametrize("case", ["reference", "priced-row", "caller-rollback"])
def test_create(conn, clock, case):
    trip = db.get_trip(conn, "ASW-0700")
    leg = trip.leg("LXR", "ASW")
    with conn:
        record = db.create_booking(conn, trip, 44, leg, "Adham Gabr", PassengerType.STUDENT, "counter", None, clock.now())
        if case == "caller-rollback":
            conn.rollback()
    if case == "reference":
        assert record.ref == "WL-58264"
    elif case == "priced-row":
        saved = db.get_booking(conn, record.ref)
        assert saved.sold_at == clock.now() and saved.tickets[0].price_piastres == 18000
        assert saved.tickets[0].leg == leg
    else:
        with pytest.raises(BookingNotFound):
            db.get_booking(conn, record.ref)


@pytest.mark.parametrize("case", ["group", "already-cancelled", "missing"])
def test_cancel(conn, clock, case):
    if case == "missing":
        with pytest.raises(BookingNotFound), conn:
            db.cancel_booking(conn, "WL-99999", clock.now())
        return
    ref = conn.execute("SELECT booking_ref FROM tickets GROUP BY booking_ref HAVING count(*) = 4").fetchone()[0]
    original = db.get_booking(conn, ref)
    with conn:
        share, value = db.cancel_booking(conn, ref, clock.now() - timedelta(days=2))
    if case == "group":
        assert share is RefundShare.FULL and value == original.total_piastres
        cancelled = db.get_booking(conn, ref)
        assert cancelled.total_piastres == 0
        assert all(t.status == "cancelled" and t.refund_piastres == t.price_piastres for t in cancelled.tickets)
    else:
        with pytest.raises(AlreadyCancelled), conn:
            db.cancel_booking(conn, ref, clock.now())
