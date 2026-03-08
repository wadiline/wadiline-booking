from datetime import UTC, datetime, timedelta

import pytest

from wadiline.clock import FixedClock, SystemClock, cairo, from_db_time, to_db_time


@pytest.mark.parametrize("case", ["reads", "midnight", "naive"])
def test_fixed(case):
    start = datetime.fromisoformat("2026-03-08T23:59:00+02:00")
    if case == "naive":
        with pytest.raises(ValueError):
            FixedClock(start.replace(tzinfo=None))
    else:
        clock = FixedClock(start)
        if case == "midnight":
            clock.advance(minutes=2)
            assert clock.now().isoformat() == "2026-03-09T00:01:00+02:00"
        else:
            assert clock.now() == start


@pytest.mark.parametrize("value", ["2026-03-08T10:00:00Z", "2026-03-08T12:00:00.123+02:00",
                                   "2026-03-08T10:00:00"])
def test_to_db(value):
    at = datetime.fromisoformat(value)
    if at.tzinfo is None:
        with pytest.raises(ValueError):
            to_db_time(at)
    else:
        assert to_db_time(at) == "2026-03-08T10:00:00Z"


@pytest.mark.parametrize("case", ["aware", "round-trip"])
def test_from_db(case):
    text = "2026-03-08T10:00:00Z"
    at = from_db_time(text)
    if case == "aware":
        assert at.tzinfo is UTC
    else:
        assert to_db_time(at) == text


def test_system_now_utc():
    before = datetime.now(UTC)
    actual = SystemClock().now()
    assert actual.tzinfo is UTC and before <= actual <= datetime.now(UTC)


def test_cairo_offset_at_snapshot():
    assert cairo(datetime(2026, 3, 8, 10, tzinfo=UTC)).utcoffset() == timedelta(hours=2)
