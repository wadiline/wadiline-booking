from pathlib import Path

import pytest

from wadiline import db, fares, refunds

RULES = Path(__file__).resolve().parents[1] / "docs" / "rules"
PASSAGES = [
    ('README.md', "These pages are Wadiline's rules for selling seats. Amira Abdelaziz, Operations, owns them. When the code and a page disagree, the page is right until Amira changes it."),
    ('README.md', 'A ticket keeps the terms it was sold under.'),
    ('seats.md', 'A ticket covers one leg: from the stop where its passenger boards to the stop where they get off.'),
    ('seats.md', 'A seat is sold again from the stop where its passenger gets off. Two tickets for one seat never share any part of the road.'),
    ('seats.md', 'A cancelled ticket frees its seat for its whole leg.'),
    ('fares.md', 'A child under 12 on the day of travel pays half the adult fare.'),
    ('fares.md', 'A student with a valid student card gets 25% off the adult fare.'),
    ('fares.md', 'A price that comes to part of a piastre is rounded down.'),
    ('refunds.md', 'A cancelled ticket is refunded in full up to 24 hours before departure, half up to 3 hours before, and nothing after.'),
    ('refunds.md', 'Departure is the timetabled time at the stop where the passenger boards.'),
    ('refunds.md', 'At exactly 24 hours before departure the refund is still in full, and at exactly 3 hours before it is still half.'),
]


@pytest.mark.parametrize(("file", "sentence"), PASSAGES, ids=[f"rule-{i:02d}" for i in range(1, 12)])
def test_rule_passage(file, sentence):
    assert sentence in (RULES / file).read_text(encoding="utf-8")


def test_fare_table_matches(conn):
    trip = db.get_trip(conn, "ALX-0700")
    names = {stop.stop.code: stop.stop.name for stop in trip.stops}
    table = (RULES / "fares.md").read_text(encoding="utf-8")
    actual = [line for line in table.splitlines() if line.startswith("| ") and line.endswith(" EGP |")]
    expected = [
        f"| {names[start]} | {names[end]} | {amount // 100} EGP |"
        for (start, end), amount in db.fare_table(conn, "ALEX").items()
    ]
    assert actual == expected


@pytest.mark.parametrize(("module", "constant", "file", "spoken"), [
    (fares, "CHILD_UNDER_YEARS", "fares.md", "under 12"),
    (fares, "STUDENT_PERCENT_OFF", "fares.md", "25% off"),
    (refunds, "FULL_REFUND_HOURS", "refunds.md", "24 hours"),
    (refunds, "HALF_REFUND_HOURS", "refunds.md", "3 hours"),
], ids=["child", "student", "full", "half"])
def test_rule_number(module, constant, file, spoken):
    number = int("".join(c for c in spoken if c.isdecimal()))
    assert getattr(module, constant) == number
    assert spoken in (RULES / file).read_text(encoding="utf-8")
