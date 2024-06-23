"""Refund rules based on the passenger's boarding time."""
from datetime import UTC, datetime, timedelta
from enum import StrEnum

FULL_REFUND_HOURS = 24
HALF_REFUND_HOURS = 3


class RefundShare(StrEnum):
    FULL = "full"
    HALF = "half"
    NONE = "none"


def refund_share(departs_at: datetime, now: datetime) -> RefundShare:
    if departs_at.utcoffset() is None or now.utcoffset() is None:
        raise ValueError("A time must have a UTC offset.")
    remaining = departs_at.astimezone(UTC) - now.astimezone(UTC)
    if remaining >= timedelta(hours=FULL_REFUND_HOURS):
        return RefundShare.FULL
    if remaining >= timedelta(hours=HALF_REFUND_HOURS):
        return RefundShare.HALF
    return RefundShare.NONE


def refund_piastres(price: int, share: RefundShare) -> int:
    return {RefundShare.FULL: price, RefundShare.HALF: price // 2, RefundShare.NONE: 0}[share]
