import pytest

from wadiline.money import format_egp, parse_egp


@pytest.mark.parametrize(("amount", "shown"), [
    (0, "0 EGP"), (5, "0.05 EGP"), (105, "1.05 EGP"), (24000, "240 EGP"),
    (24050, "240.50 EGP"), (150000, "1500 EGP"),
])
def test_format_amount(amount, shown):
    assert format_egp(amount) == shown


@pytest.mark.parametrize(("shown", "amount"), [
    ("0", 0), ("240", 24000), ("240 EGP", 24000), ("240.5", 24050),
    ("240.50 EGP", 24050), ("0.05", 5),
])
def test_parse_amount(shown, amount):
    assert parse_egp(shown) == amount


def test_negative_format():
    with pytest.raises(ValueError):
        format_egp(-1)


@pytest.mark.parametrize("shown", ["+240", "-240", "1.001"])
def test_invalid_text(shown):
    with pytest.raises(ValueError):
        parse_egp(shown)
