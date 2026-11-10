"""Seat holds for the app's new checkout (BK-63). The rules are in docs/rules/holds.md.

A hold keeps one seat for one leg while a passenger pays. It ends HOLD_MINUTES after it was
placed, or when its holder releases it. An ended hold stays in the holds table.

Still to write:

    place_hold(conn, trip, seat, leg, holder, now) -> Hold
        Places a hold for `holder`, or returns the holder's active hold for the same seat and
        leg unchanged. Raises SeatTaken when a sold ticket on the seat shares road with `leg`,
        SeatHeld when another active hold on the seat does, and ValueError for a seat that is
        not on the trip, a naive `now`, or a holder that is empty or over 64 characters.
        A new hold takes the next ID SQLite assigns, so the first hold in an empty table
        is `H-000001`.

    release_hold(conn, hold_id, holder, now) -> None
        Ends the hold at `now`. Releasing an ended or released hold changes nothing. Raises
        HoldNotFound when there is no such hold or it belongs to someone else.

    active_holds(conn, trip, now) -> list[Hold]
        The trip's holds that are neither released nor ended at `now`, by seat, then by
        created_at. It only reads.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from wadiline.clock import from_db_time
from wadiline.models import Leg, WadilineError

HOLD_MINUTES = 10


@dataclass(frozen=True, slots=True)
class Hold:
    id: int
    trip_id: int
    seat: int
    leg: Leg
    holder: str
    created_at: datetime
    expires_at: datetime
    released_at: datetime | None

    @property
    def ref(self) -> str:
        return f"H-{self.id:06d}"


class HoldError(WadilineError):
    """A seat hold could not be completed."""


class SeatTaken(HoldError):
    """A sold ticket shares road on this seat."""


class SeatHeld(HoldError):
    """An active hold shares road on this seat."""


class HoldNotFound(HoldError):
    """The requested hold does not belong to this holder."""


def hold_from_row(row: sqlite3.Row) -> Hold:
    return Hold(row["id"], row["trip_id"], row["seat"], Leg(row["board"], row["alight"]),
                row["holder"], from_db_time(row["created_at"]), from_db_time(row["expires_at"]),
                from_db_time(row["released_at"]) if row["released_at"] else None)
