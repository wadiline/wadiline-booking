from datetime import UTC, datetime, timedelta, timezone

import pytest

from wadiline.refunds import RefundShare, refund_piastres, refund_share

NOW = datetime(2024, 6, 23, 10, tzinfo=UTC)


@pytest.mark.parametrize(("seconds", "share"), [
    (86401, "full"), (86400, "full"), (86399, "half"), (10801, "half"),
    (10800, "half"), (10799, "none"), (0, "none"), (-1, "none"),
])
def test_threshold(seconds, share):
    assert refund_share(NOW + timedelta(seconds=seconds), NOW).value == share


@pytest.mark.parametrize(("departure_aware", "now_aware"), [(False, True), (True, False), (False, False)])
def test_naive_refused(departure_aware, now_aware):
    with pytest.raises(ValueError):
        refund_share(NOW if departure_aware else NOW.replace(tzinfo=None),
                     NOW if now_aware else NOW.replace(tzinfo=None))


@pytest.mark.parametrize("share", list(RefundShare))
@pytest.mark.parametrize(("price", "half"), [(0, 0), (1, 0), (5, 2), (24000, 12000)])
def test_refund_amount(share, price, half):
    assert refund_piastres(price, share) == {"full": price, "half": half, "none": 0}[share]


def test_same_instant_other_offset():
    shifted = NOW.astimezone(timezone(timedelta(hours=2)))
    assert refund_share(NOW + timedelta(hours=24), shifted) is RefundShare.FULL
