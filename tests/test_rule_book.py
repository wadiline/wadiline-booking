from pathlib import Path

import pytest

from wadiline import db, fares, holds, refunds

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
    ('holds.md', 'While a passenger pays in the app, their seat is held for 10 minutes. At 10 minutes the hold ends and the seat is free again.'),
    ('holds.md', 'A hold covers one leg, like a ticket. A held seat cannot be sold, or held again, for any part of that leg. Legs that only meet at a stop do not clash.'),
    ('holds.md', 'A passenger who asks again for the same seat and leg keeps the same hold. The 10 minutes do not start again.'),
    ('holds.md', 'Only the passenger who holds a seat can let it go early.'),
    ('notices/README.md', 'Dated notices from Operations. Each one says from when it applies and what it changes.'),
]


@pytest.mark.parametrize(("file", "sentence"), PASSAGES, ids=[f"rule-{i:02d}" for i in range(1, 17)])
def test_rule_passage(file, sentence):
    assert sentence in (RULES / file).read_text(encoding="utf-8")


def test_fare_table_matches(conn):
    routes = [("ALEX", "ALX-0700"), ("HURG", "HRG-0830"), ("SINAI", "SSH-2300"),
              ("REDSEA", "LXR-0800"), ("UPPER", "ASW-0700")]
    table = (RULES / "fares.md").read_text(encoding="utf-8")
    actual_rows = [line for line in table.splitlines() if line.startswith("| ") and line.endswith(" EGP |")]
    expected = []
    for route, trip_code in routes:
        trip = db.get_trip(conn, trip_code)
        names = {s.stop.code: s.stop.name for s in trip.stops}
        for (start, end), amount in db.fare_table(conn, route).items():
            expected.append(f"| {names[start]} | {names[end]} | {amount // 100} EGP |")
    assert len(expected) == 10 and set(actual_rows) == set(expected)


@pytest.mark.parametrize(("module", "constant", "file", "spoken"), [
    (fares, "CHILD_UNDER_YEARS", "fares.md", "under 12"),
    (fares, "STUDENT_PERCENT_OFF", "fares.md", "25% off"),
    (refunds, "FULL_REFUND_HOURS", "refunds.md", "24 hours"),
    (refunds, "HALF_REFUND_HOURS", "refunds.md", "3 hours"),
    (holds, "HOLD_MINUTES", "holds.md", "10 minutes"),
], ids=["child", "student", "full", "half", "hold"])
def test_rule_number(module, constant, file, spoken):
    number = int("".join(c for c in spoken if c.isdecimal()))
    assert getattr(module, constant) == number
    assert spoken in (RULES / file).read_text(encoding="utf-8")
