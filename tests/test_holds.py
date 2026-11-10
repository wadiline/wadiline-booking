from datetime import timedelta

import pytest

from wadiline import db, holds
from wadiline.models import PassengerType

STARTER_NAMES = frozenset({
    "sqlite3", "dataclass", "datetime", "from_db_time", "Leg", "WadilineError", "HOLD_MINUTES",
    "Hold", "HoldError", "SeatTaken", "SeatHeld", "HoldNotFound", "hold_from_row",
})
# Run as soon as holds.py differs from the starter, so missing or misnamed functions fail.
if {name for name in vars(holds) if not name.startswith("__")} == STARTER_NAMES:
    pytest.skip("Seat holds are not written yet.", allow_module_level=True)


@pytest.fixture
def trip(conn):
    return db.get_trip(conn, "ALX-0700")


def place(conn, trip, clock, start="CAI", end="ALX", seat=45, holder="app-7f3a"):
    return holds.place_hold(conn, trip, seat, trip.leg(start, end), holder, clock.now())


def sell(conn, trip, clock, start, end):
    with conn:
        book = db.create_booking(conn, trip, 45, trip.leg(start, end), "Adham Gabr",
                                 PassengerType.ADULT, "counter", None, clock.now())
    return book


def test_new_fields(conn, trip, clock):
    hold = place(conn, trip, clock)
    assert (hold.id, hold.ref, hold.trip_id, hold.seat, hold.leg, hold.holder) == (
        1, "H-000001", trip.id, 45, trip.leg("CAI", "ALX"), "app-7f3a")
    assert hold.created_at == clock.now()
    assert hold.expires_at == clock.now() + timedelta(minutes=10)
    assert hold.released_at is None


def test_stored_utc(conn, trip, clock):
    hold = place(conn, trip, clock)
    row = conn.execute("SELECT * FROM holds WHERE id=?", (hold.id,)).fetchone()
    assert (row["created_at"], row["expires_at"], row["released_at"]) == (
        "2024-09-15T09:00:00Z", "2024-09-15T09:10:00Z", None)


def test_ids_count_up(conn, trip, clock):
    first = place(conn, trip, clock)
    second = place(conn, trip, clock, seat=46, holder="app-else")
    assert (first.ref, second.ref) == ("H-000001", "H-000002")


def test_sold_seat_conflicts_until_cancelled(conn, trip, clock):
    booking = sell(conn, trip, clock, "CAI", "ALX")
    with pytest.raises(holds.SeatTaken):
        place(conn, trip, clock)
    with conn:
        db.cancel_booking(conn, booking.ref, clock.now())
    assert place(conn, trip, clock).seat == 45


def test_blocked_at_959(conn, trip, clock):
    clock.advance(microseconds=900_999)
    expiry = clock.now() + timedelta(minutes=10)
    first = place(conn, trip, clock)
    assert first.expires_at == expiry
    created = conn.execute("SELECT created_at FROM holds WHERE id=?", (first.id,)).fetchone()[0]
    assert created == clock.now().isoformat(timespec="microseconds").replace("+00:00", "Z")
    clock.advance(seconds=599, microseconds=999_999)
    with pytest.raises(holds.SeatHeld):
        place(conn, trip, clock, holder="app-else")
    clock.advance(microseconds=1)
    second = place(conn, trip, clock, holder="app-else")
    assert second.id != first.id
    clock.advance(microseconds=1)
    holds.release_hold(conn, second.id, second.holder, clock.now())
    assert released_at(conn, second) == clock.now().isoformat(timespec="microseconds").replace("+00:00", "Z")


def test_free_at_1000(conn, trip, clock):
    first = place(conn, trip, clock)
    clock.advance(minutes=10)
    second = place(conn, trip, clock, holder="app-else")
    assert first.id != second.id


def test_free_after_release(conn, trip, clock):
    first = place(conn, trip, clock)
    holds.release_hold(conn, first.id, first.holder, clock.now())
    assert place(conn, trip, clock, holder="app-else").id != first.id


def test_repeat_keeps_row_and_expiry(conn, trip, clock):
    first = place(conn, trip, clock)
    clock.advance(minutes=5)
    assert place(conn, trip, clock) == first
    assert conn.execute("SELECT count(*) FROM holds").fetchone()[0] == 1


def test_renew_after_end(conn, trip, clock):
    first = place(conn, trip, clock)
    clock.advance(minutes=10)
    second = place(conn, trip, clock)
    assert first.id != second.id and second.expires_at == clock.now() + timedelta(minutes=10)
    assert conn.execute("SELECT count(*) FROM holds").fetchone()[0] == 2


@pytest.mark.parametrize(("seat", "holder", "naive"), [
    (0, "app", False), (50, "app", False), (45, "app", True), (45, "", False), (45, "a" * 65, False),
], ids=["seat-zero", "seat-50", "naive", "empty", "too-long"])
def test_invalid_hold(conn, trip, clock, seat, holder, naive):
    now = clock.now().replace(tzinfo=None) if naive else clock.now()
    with pytest.raises(ValueError):
        holds.place_hold(conn, trip, seat, trip.leg("CAI", "ALX"), holder, now)


def released_at(conn, hold):
    return conn.execute("SELECT released_at FROM holds WHERE id=?", (hold.id,)).fetchone()[0]


def test_release_sets_time(conn, trip, clock):
    hold = place(conn, trip, clock)
    clock.advance(minutes=1)
    holds.release_hold(conn, hold.id, hold.holder, clock.now())
    assert released_at(conn, hold) == "2024-09-15T09:01:00Z"


def test_release_twice(conn, trip, clock):
    hold = place(conn, trip, clock)
    holds.release_hold(conn, hold.id, hold.holder, clock.now())
    clock.advance(minutes=1)
    holds.release_hold(conn, hold.id, hold.holder, clock.now())
    assert released_at(conn, hold) == "2024-09-15T09:00:00Z"


def test_release_ended(conn, trip, clock):
    hold = place(conn, trip, clock)
    clock.advance(minutes=10)
    holds.release_hold(conn, hold.id, hold.holder, clock.now())
    assert released_at(conn, hold) is None


def test_wrong_holder(conn, trip, clock):
    hold = place(conn, trip, clock)
    with pytest.raises(holds.HoldNotFound):
        holds.release_hold(conn, hold.id, "someone-else", clock.now())
    assert released_at(conn, hold) is None


def test_unknown_id(conn, clock):
    with pytest.raises(holds.HoldNotFound):
        holds.release_hold(conn, 999, "app-7f3a", clock.now())


def test_active_list_filters_sorts_and_preserves_rows(conn, trip, clock):
    place(conn, trip, clock, seat=41, holder="ended")
    clock.advance(minutes=10)
    later_seat = place(conn, trip, clock, seat=47, holder="first")
    first = place(conn, trip, clock, seat=45, holder="second")
    released = place(conn, trip, clock, seat=46, holder="third")
    holds.release_hold(conn, released.id, released.holder, clock.now())
    clock.advance(minutes=1)
    second = place(conn, trip, clock, seat=44, holder="fourth")
    place(conn, db.get_trip(conn, "ALX-1500"), clock, "CAI", "ALX", 49, "other-trip")
    before = conn.execute("SELECT * FROM holds ORDER BY id").fetchall()
    assert holds.active_holds(conn, trip, clock.now()) == [second, first, later_seat]
    assert conn.execute("SELECT * FROM holds ORDER BY id").fetchall() == before
