import json

import pytest

from wadiline import cli, db

NIGHT_HEADER = "ASW-2200  Cairo 11 Nov 22:00 -> Aswan 12 Nov 10:40\n"
SEED_LINE = "7 stops, 5 routes, 8 trips, 263 bookings, 313 tickets.\n"
NOURHAN_LINE = "WL-58214  Luxor 12 Nov 07:30 -> Aswan 12 Nov 10:40  adult  240 EGP  Nourhan Elsayed\n"


@pytest.mark.parametrize("case", ["default", "path", "refusal", "force"])
def test_seed(run_cli, tmp_path, monkeypatch, capsys, case):
    if case == "default":
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("WADILINE_DB", raising=False)
        assert cli.main(["seed"]) == 0
        captured = capsys.readouterr()
        assert (captured.out, captured.err) == ("Seeded var/wadiline.db: " + SEED_LINE, "")
        assert (tmp_path / "var/wadiline.db").is_file()
    elif case == "refusal":
        assert run_cli("seed") == (2, "", "The database already has data. Use --force to replace it.\n")
    elif case == "force":
        code, out, err = run_cli("seed", "--force")
        assert code == 0 and err == "" and out.endswith(SEED_LINE)
    else:
        path = tmp_path / "new.db"
        assert cli.main(["--db", str(path), "seed"]) == 0
        captured = capsys.readouterr()
        assert (captured.out, captured.err) == (f"Seeded {path}: " + SEED_LINE, "")


@pytest.mark.parametrize(("args", "expected"), [
    ((), "ALX-0700 ASW-0700 LXR-0800 HRG-0830 ALX-1500 ALX-1900 ASW-2200 SSH-2300"),
    (("--from", "Hurghada"), "LXR-0800 HRG-0830"), (("--to", "Luxor"), "ASW-0700 LXR-0800 ASW-2200"),
    (("--from", "CAI", "--to", "ASW"), "ASW-0700 ASW-2200"),
    (("--date", "2026-11-12"), ""), (("--from", "Suez"), ""),
], ids=["order", "from", "to", "pair", "date", "no-match"])
def test_trips(run_cli, args, expected):
    code, out, err = run_cli("trips", *args)
    assert code == 0 and err == ""
    assert [line.split()[0] for line in out.splitlines()] == expected.split()
    if "ASW-2200" in expected:
        assert "ASW-2200  11 Nov 22:00  Cairo -> Assiut -> Luxor -> Aswan" in out.splitlines()


@pytest.mark.parametrize("case", ["free", "sold", "ranges", "bad-stop", "bad-seat", "missing-trip"])
def test_seats(run_cli, conn, case):
    trip = db.get_trip(conn, "ALX-0700")
    sold = db.live_tickets(conn, trip)[0].seat
    code = "UNKNOWN" if case == "missing-trip" else trip.code
    start = "Suez" if case == "bad-stop" else "cai"
    seat = {"free": 49, "sold": sold, "bad-seat": 50}.get(case)
    if case == "ranges":
        with conn:
            conn.execute("UPDATE tickets SET status='cancelled' WHERE trip_id=?", (trip.id,))
    options = ("--seat", str(seat)) if seat is not None else ()
    status, out, err = run_cli("seats", code, "--from", start, "--to", "alx", *options)
    if case in ("bad-stop", "bad-seat", "missing-trip"):
        assert status == (3 if case == "missing-trip" else 2) and out == "" and err
    elif case == "ranges":
        assert (status, err) == (0, "")
        assert out == ("ALX-0700  Cairo 11 Nov 07:00 -> Alexandria 11 Nov 10:00\n"
                       "Seats for Cairo -> Alexandria\nFree (49): 1-49\nTaken (0): none\n")
    else:
        assert (status, out, err) == (0, f"Seat {seat} is {'free' if case == 'free' else 'taken'} for Cairo -> Alexandria.\n", "")


@pytest.mark.parametrize("case", ["sorted", "filtered", "singular", "empty"])
def test_tickets(run_cli, conn, case):
    code, options = {
        "sorted": ("ASW-2200", ()), "filtered": ("ASW-2200", ("--seat", "22")),
        "singular": ("ASW-2200", ("--seat", "14")), "empty": ("ALX-0700", ("--seat", "49")),
    }[case]
    status, out, err = run_cli("tickets", code, *options)
    assert status == 0 and err == ""
    if case == "singular":
        assert out == NIGHT_HEADER + "Seat 14: 1 ticket\n" + NOURHAN_LINE
    elif case == "empty":
        assert out.endswith("Seat 49: 0 tickets\n") and len(out.splitlines()) == 2
    else:
        records = db.live_tickets(conn, db.get_trip(conn, code), 22 if options else None)
        assert [line.split()[0] for line in out.splitlines()[2:]] == [t.booking_ref for t in records]
        assert out.splitlines()[1] == ("Seat 22: 2 tickets" if options else "54 tickets")


@pytest.mark.parametrize("case", [
    "story", "group", "missing",
])
def test_booking(run_cli, conn, case):
    if case == "story":
        assert run_cli("booking", "WL-58214") == (0, "WL-58214  sold 8 Nov 20:14  app  240 EGP\n" + NOURHAN_LINE, "")
    elif case == "missing":
        assert run_cli("booking", "WL-99999") == (3, "", "No booking WL-99999.\n")
    else:
        ref = conn.execute("SELECT booking_ref FROM tickets GROUP BY booking_ref HAVING count(*)=4").fetchone()[0]
        code, out, err = run_cli("booking", ref)
        assert code == 0 and err == ""
        assert len(out.splitlines()) == 5 and all(line.startswith(ref) for line in out.splitlines())


@pytest.mark.parametrize("case", ["three", "refused", "atomic"])
def test_import_timetable(run_cli, conn, tmp_path, case):
    path = tmp_path / "export.json"
    rows = [{"code": code, "route": "ALEX", "service_date": "2026-11-12", "seats": 49,
             "stops": [{"stop": "CAI", "time": "2026-11-12T07:00:00+02:00"},
                       {"stop": "ALX", "time": "2026-11-12T10:00:00+02:00"}]}
            for code in ("NEW-1", "NEW-2", "NEW-3")]
    if case != "three":
        rows[0 if case == "refused" else -1]["route"] = "UNKNOWN"
    path.write_text(json.dumps(rows), encoding="utf-8")
    status, out, err = run_cli("import-timetable", str(path))
    if case == "three":
        assert (status, out, err) == (0, f"Imported 3 trips from {path}.\n", "")
        assert len(db.list_trips(conn, service_date="2026-11-12")) == 3
    else:
        assert status == 1 and out == "" and err.startswith("Import stopped: ")
        assert not db.list_trips(conn, service_date="2026-11-12")


@pytest.mark.parametrize("case", ["argparse", "missing-db", "unseeded-db"])
def test_command_error(run_cli, tmp_path, capsys, case):
    if case == "argparse":
        status, out, err = run_cli("seats", "ALX-0700")
        assert status == 2 and out == "" and "required" in err
    else:
        path = tmp_path / "unseeded.db"
        if case == "unseeded-db":
            path.touch()
        assert cli.main(["--db", str(path), "trips"]) == 4
        capture = capsys.readouterr()
        assert capture.out == "" and "Run seed first." in capture.err


def test_seats_asw_2200_cairo_to_aswan(run_cli):
    assert run_cli("seats", "ASW-2200", "--from", "Cairo", "--to", "Aswan") == (
        0, NIGHT_HEADER + "Seats for Cairo -> Aswan\nFree (0): none\nTaken (49): 1-49\n", "")
