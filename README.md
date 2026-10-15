# HarvestShield

Crop price forecasting and market comparison using FastAPI, Streamlit and
scikit-learn. Developed by Ayush Kumar.

HarvestShield estimates wholesale modal prices seven calendar days ahead,
assesses the risk of a price decline of at least 15%, and compares estimated
market revenue after transport and handling costs.

## Features

- Historical price charts, source attribution and data coverage checks.
- Price forecasts, decline-risk estimates and approximate uncertainty ranges.
- Market comparisons for matching crop, variety, grade, unit and selling date.
- CSV import and automatic production AGMARKNET daily updates through data.gov.in.
- Chronological evaluation, baseline comparisons and historical replay.
- Read-only deployment mode with protected backend administration.

## Stack

Python 3.13, FastAPI, Streamlit, pandas, NumPy, scikit-learn, Plotly and SQLite.

## Run locally

```text
git clone https://github.com/ayush4604/harvestshield.git
cd harvestshield
```

On Windows, run in PowerShell:

```powershell
.\Setup-HarvestShield.ps1
.\.venv\Scripts\python.exe -m backend.cli demo
.\Start-HarvestShield.ps1
```

On Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
python -m backend.cli demo
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
# In a second terminal with the virtual environment activated:
python -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
```

Dashboard: http://127.0.0.1:8501. Local API docs: http://127.0.0.1:8000/docs.
Stop Windows services with `.\Stop-HarvestShield.ps1`.

The demo contains fictional observations. Databases, models and credentials
are not committed to this repository.

## Real market data

Use **Real > Data & models** to import a UTF-8 CSV with these columns:

```text
date,state,district,market,commodity,variety,grade,unit,min_price,max_price,modal_price
```

Prices must use `INR/quintal`, with positive values satisfying
`min_price <= modal_price <= max_price`. Dates accept `YYYY-MM-DD` or
`DD/MM/YYYY`. Keep unknown grades unspecified rather than inferring quality.

To reproduce the historical tomato pilot, use the virtual environment:

```text
python scripts/import_public_history.py
python -m backend.cli train --mode real
```

The importer downloads the Tomato.csv archive and retains source metadata.
See [data attribution](docs/THIRD_PARTY_DATA.md) for publisher and licensing details.

For daily government updates, configure `DATA_GOV_API_KEY` privately in the backend
environment before starting it. Local launches do not automatically load `.env`.
In production, the backend automatically collects Maharashtra tomato prices on
first startup and every six hours, with persistent retry status and safe backoff.
The Real dashboard shows collection status; public write controls stay disabled.
State/crop/market filters and scheduling are configurable in the deployment guide.
Daily snapshots do not backfill historical data or automatically train models.

## Deployment

The Dockerfile builds directly from a Git checkout. If no prepared seed is
present, it generates a labeled synthetic demo during the image build. The
default container runs both services and serves Streamlit on `PORT` (8501 by
default), with FastAPI bound internally. Real observations are never fabricated.

For a single hosted service, use the Dockerfile's default start command and
`/_stcore/health` as the health path. Attach persistent storage at `/state`.

After creating data and models, prepare the deployment seed:

```text
python scripts/prepare_release.py
python scripts/check_deployment.py
docker compose up --build -d --wait
```

The seed directory must be new. Compose keeps the backend internal, persists data
and models in a named volume, and exposes a read-only dashboard on host loopback.
See [deployment instructions](docs/DEPLOYMENT.md) for hosting and backups.

## Tests

```text
python -m pytest -q
```

GitHub Actions runs the test suite and Docker health/inference checks.

## Model limitations

The historical evaluation used 3,560 tomato records from four Pune market series
covering January 2021 to February 2024. Grade was unreported. Persistence was the
selected price model, with test MAE of 427.33 INR/quintal. Learned price models did
not improve on that baseline. Risk Brier score was 0.20994 versus 0.20724 for the
constant baseline, where lower is better.

Current forecasts require sufficient recent history. The application withholds
unsupported forecasts and restricts comparisons when produce identity is unclear.
Wholesale prices and model estimates do not guarantee transaction prices or income.
