import pytest

from wadiline import cli, db

SEED_LINE = "2 stops, 1 routes, 2 trips, 1 bookings, 1 tickets.\n"


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
    ((), "ALX-0700 ALX-1500"),
    (("--from", "Cairo"), "ALX-0700 ALX-1500"), (("--to", "Alexandria"), "ALX-0700 ALX-1500"),
    (("--from", "CAI", "--to", "ALX"), "ALX-0700 ALX-1500"),
    (("--date", "2024-09-16"), ""), (("--from", "Suez"), ""),
], ids=["order", "from", "to", "pair", "date", "no-match"])
def test_trips(run_cli, args, expected):
    code, out, err = run_cli("trips", *args)
    assert code == 0 and err == ""
    assert [line.split()[0] for line in out.splitlines()] == expected.split()



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
        assert out == ("ALX-0700  Cairo 15 Sep 07:00 -> Alexandria 15 Sep 10:00\n"
                       "Seats for Cairo -> Alexandria\nFree (49): 1-49\nTaken (0): none\n")
    else:
        assert (status, out, err) == (0, f"Seat {seat} is {'free' if case == 'free' else 'taken'} for Cairo -> Alexandria.\n", "")


def test_tickets(run_cli, conn):
    trip = db.get_trip(conn, "ALX-0700")
    ticket = db.live_tickets(conn, trip)[0]
    status, out, err = run_cli("tickets", trip.code, "--seat", str(ticket.seat))
    assert status == 0 and err == ""
    assert out.splitlines()[1] == f"Seat {ticket.seat}: 1 ticket"
    assert out.splitlines()[2].startswith("WL-58001  ")


def test_booking(run_cli):
    code, out, err = run_cli("booking", "WL-58001")
    assert code == 0 and err == ""
    assert out.splitlines()[1].startswith("WL-58001  ")
    assert run_cli("booking", "WL-99999") == (3, "", "No booking WL-99999.\n")


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
