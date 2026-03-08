import shutil
from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from wadiline import cli, db
from wadiline.api import app, get_clock, get_db
from wadiline.clock import FixedClock


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory):
    path = tmp_path_factory.mktemp("sample") / "wadiline.db"
    with closing(db.connect(path)) as connection:
        db.seed(connection)
    return path


@pytest.fixture
def db_path(seeded_template, tmp_path):
    path = tmp_path / "wadiline.db"
    shutil.copyfile(seeded_template, path)
    return path


@pytest.fixture
def conn(db_path):
    with closing(db.connect(db_path)) as connection:
        yield connection


@pytest.fixture
def clock():
    return FixedClock(datetime.fromisoformat("2024-09-15T09:00:00Z"))


@pytest.fixture
def client(db_path, clock):
    def database():
        with closing(db.connect(db_path)) as connection:
            yield connection

    original = app.dependency_overrides.copy()
    app.dependency_overrides.update({get_db: database, get_clock: lambda: clock})
    try:
        with TestClient(app, base_url="http://test.wadiline.example") as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


@pytest.fixture
def run_cli(db_path):
    def run(*args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = cli.main(["--db", str(db_path), *args])
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()
    return run
