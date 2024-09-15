# Wadiline booking

Wadiline's booking service: trips, seats, fares, refunds, and the booking API that the app, the website and the station counters use.

## Quick start

Use Python 3.12 or newer. Fork the repository, then clone your fork.

```text
git clone <your-fork-url>
cd wadiline-booking
```

On Windows, create and activate a virtual environment in PowerShell.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

On macOS or Linux, use your terminal.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
```

Install the package, load the sample and run the checks.

```text
python -m pip install -e ".[dev]"
python -c "from wadiline import db; path = db.db_path(); path.parent.mkdir(parents=True, exist_ok=True); conn = db.connect(path); db.seed(conn); conn.close()"
python -m pytest
python -m ruff check .
```

To try the API, run `python -m uvicorn wadiline.api:app --reload` and open
`http://127.0.0.1:8000/docs`.

- [HTTP API](docs/api.md)
