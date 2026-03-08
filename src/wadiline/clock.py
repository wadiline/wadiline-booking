"""Time at the service boundaries."""
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo("Africa/Cairo")


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    def __init__(self, at: datetime):
        _require_aware(at)
        self._at = at

    def now(self) -> datetime:
        return self._at

    def advance(self, **timedelta_kwargs) -> None:
        self._at = (self._at.astimezone(UTC) + timedelta(**timedelta_kwargs)).astimezone(
            self._at.tzinfo)


def _require_aware(dt: datetime) -> None:
    if dt.utcoffset() is None:
        raise ValueError("A time must have a UTC offset.")


def to_db_time(dt: datetime) -> str:
    _require_aware(dt)
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def from_db_time(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    _require_aware(dt)
    return dt.astimezone(UTC)


def cairo(dt: datetime) -> datetime:
    _require_aware(dt)
    return dt.astimezone(CAIRO)
