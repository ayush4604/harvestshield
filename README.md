# HarvestShield

**Classical machine-learning early warning for crop price drops.** A FastAPI
backend predicts modal wholesale prices seven calendar days ahead and estimates
the risk of a >=15% decline. A Streamlit frontend compares equivalent produce
across markets after user-entered total transport and market costs.

Built for an internship project aligned with SDG 1 (No Poverty) and SDG 2 (Zero
Hunger). No CNNs, neural networks, devices, or hardware purchases.

## Deployment release

Release 1.1.0 includes a safe read-only public dashboard profile, authenticated
backend administration, bounded request bodies, persistent state bootstrap,
Docker/Compose configuration, an isolated deployment preflight and Linux CI.
See **docs/DEPLOYMENT.md** for setup, secrets, backups and the actual verification
boundary. No public hosting was created. Docker execution must be checked on a
Docker host; Docker is not installed on this authoring computer.

## Current truth status
The project includes both a labeled synthetic demo and a **published historical
pilot with 3,560 records** for Pune, Pune(Khadiki), Pune(Moshi), and Pune(Pimpri).
Reported variety: Local; dates: 2021-01-01 to 2024-02-01. Grade is unreported.
The source is Vandeet Shah's Apache-2.0-licensed Kaggle release, with metadata,
raw archive, checksum, normalized CSV, and coverage manifest retained.

Real-data evaluation and three expanding-prefix backtests are complete. Learned
price models did not beat persistence; final risk Brier was 0.20994 versus a
constant baseline of 0.20724. These results are disclosed, not marketed as model
success. Original daily government records have not been independently reconciled.

The historical data is stale: current real forecasts are withheld. Historical
replay supports held-out dates only, excluding later observations from features.
An authenticated daily refresh added 25 Maharashtra tomato records dated
2026-10-14 (3,585 total real observations). New one-row series lack sufficient
forecast history. The rotated API key is operator-owned and never packaged.
Farmer income impact and production forecasting effectiveness are unproven.

## Windows quick start
When cloning this repository, databases, trained models, private notes and keys
are intentionally absent. After setup, generate the clearly labeled synthetic
demo with `.\.venv\Scripts\python.exe -m backend.cli demo` before starting the
app. For real historical evaluation, follow the published-pilot import steps below.

Open PowerShell in this directory:

```powershell
.\Setup-HarvestShield.ps1
.\Start-HarvestShield.ps1
```

On this prepared computer, you can also double-click **Start-HarvestShield.cmd**.
Use **Stop-HarvestShield.cmd** to stop the project-owned services.

If your local PowerShell policy blocks scripts, run a single script using
`powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-HarvestShield.ps1`.
This does not change the machine's execution policy.

The prepared environment on this computer is isolated from global packages.
Setup also creates an isolated environment by default on another computer;
`-UseExistingPackages` is an optional shortcut only for healthy existing installs.
Python 3.13 is the verified runtime. Setup uses the tested requirements-lock.txt
when present; requirements.txt describes the supported dependency ranges.

- Dashboard: http://127.0.0.1:8501
- FastAPI docs: http://127.0.0.1:8000/docs
- Stop owned services: `.\Stop-HarvestShield.ps1`
- Alternate ports: `.\Start-HarvestShield.ps1 -BackendPort 8008 -FrontendPort 8508`

Launch services individually if preferred:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
# In a second terminal, in this same directory:
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.port 8501
```

## Reproduce demo and evaluation

```powershell
.\.venv\Scripts\python.exe -m backend.cli demo
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m backend.cli train --mode demo
```

## Run the prepared historical pilot
Start the app, select **Real · imported records**, open **Forecasts**, enable
**Historical replay (research only)**, and use the default held-out date
2024-01-25. The same option on Market comparison permits an illustrative,
clearly labeled historical cost comparison. It is not current selling advice.

Reproduce acquisition/training/backtests:

```powershell
.\.venv\Scripts\python.exe scripts/import_public_history.py
.\.venv\Scripts\python.exe -m backend.cli train --mode real
.\.venv\Scripts\python.exe -m backend.cli backtest --mode real
```

The importer downloads only Tomato.csv (195 MB uncompressed, compressed download),
not the entire 4.7 GB dataset. It reuses the cached archive/subset on reruns and
imports idempotently. Source/cleaning details: docs/THIRD_PARTY_DATA.md and
data/raw/public_release/pilot_manifest.json. No prices or labels are interpolated.

The generator uses seed 42 and dates ending when initially created. Existing demo
observations are retained, so a demo started many days later may deliberately
withhold stale forecasts. For a refreshed demo, use a NEW alternate data directory
(do not erase existing data):

```powershell
$env:HARVESTSHIELD_DATA_DIR = Join-Path $PWD 'work\fresh-demo'
.\.venv\Scripts\python.exe -m backend.cli demo
.\Start-HarvestShield.ps1 -BackendPort 8008 -FrontendPort 8508
```

## Real historical data
Open **Real · imported records > Data & models**. Download the CSV header, obtain
permitted AGMARKNET historical market reports, transform them to the contract,
and import with a source note. Audit coverage before fitting a real-mode model.

Required fields:

```text
date,state,district,market,commodity,variety,grade,unit,min_price,max_price,modal_price
```

- Dates: YYYY-MM-DD or DD/MM/YYYY, no future observations.
- Unit: exactly `INR/quintal`; 1 quintal = 100 kg.
- Prices: finite positive numbers; min <= modal <= max.
- District/grade default to `Unspecified` if the columns are absent. Other identity
  fields must be supplied. Never mix varieties/grades in a comparison.
- Identical repeated records are skipped. Conflicting duplicates reject the entire
  import; review source revisions explicitly instead of silently overwriting.
- UTF-8 CSV, maximum 20 MB / 200,000 rows per import.
- User imports always go to real mode. Only import actual observed records there.
- Modal price is not the average, retail price, or an individual farmer's quote.

CLI alternative:

```powershell
.\.venv\Scripts\python.exe -m backend.cli import --file .\your_history.csv --source 'AGMARKNET report; downloaded YYYY-MM-DD; verified INR/quintal'
.\.venv\Scripts\python.exe -m backend.cli audit --mode real
.\.venv\Scripts\python.exe -m backend.cli train --mode real
```

Aim for 2–3 years for 3–5 nearby markets. Software minimums (120 distinct labeled
dates and minimum split row counts) only permit an experiment, not a quality claim.

## Official daily feed
Register on data.gov.in and generate your own API key. Set it in the PowerShell
session BEFORE starting the backend, without putting the actual key in source:

```powershell
$env:DATA_GOV_API_KEY = '<your key>'
.\Start-HarvestShield.ps1
```

If services are already running, stop/restart the project backend to pick up the
environment. Use **Real > Data & models > Government daily-feed connector**.
Select official state/crop spelling and optionally a market. The adapter uses
bounded pagination, verifies records, and stores snapshots in real mode. It
does not assume the feed contains historical archives. Connector HTTP errors are
sanitized to avoid displaying credentials.

Manual daily-refresh command (no scheduled task is created automatically):

```powershell
.\.venv\Scripts\python.exe -m backend.cli refresh --state Maharashtra --commodity Tomato
```

Training is limited to 20 produce/market series to bound memory usage. The initial
pilot should stay at 3–5 nearby markets for one consistent crop/variety/grade.

Optional direct CEDA archive: `scripts/fetch_pilot.py`. The source answered sample
queries but rate-limited the multiyear download. This connector honors Retry-After,
throttles requests, caches windows, and splits responses hitting the 1,000-row cap.
It is not the source of the loaded pilot. CEDA attribution/logo terms apply if used.

During implementation an unauthenticated AGMARKNET API probe returned 403 and a
data.gov.in probe timed out. A successful authenticated live refresh is unverified.
Inspect current resource schema, filter behavior, units, and your key before field
use; do not equate daily reporting with continuous live auction prices.

## Model design
- Features: current price, lagged reported prices with their ages, time-window
  rolling means/volatility, returns, calendar cycles, and series identity.
- Exact target: reported modal price at t+7; unavailable targets are not imputed.
- Risk target: t+7 modal price <= 85% of the t price.
- Global chronological train/validation/test periods; seven-day label embargoes.
- Forecast candidates: persistence, Ridge, Random Forest, gradient boosting.
- Risk candidates: constant frequency, Logistic Regression, Random Forest,
  gradient boosting. Validation Brier score chooses the risk model.
- Sigmoid calibration only when validation has >=20 examples of each class;
  otherwise estimates are explicitly uncalibrated.
- Forecast selection uses validation MAE and includes the persistence baseline.
- Approximate intervals use pooled validation residual quantiles. Coverage is
  measured on test but is not guaranteed for individual markets or future dates.
- Test report includes MAE, RMSE, WAPE, baseline skill, precision/recall/F1, Brier,
  reliability bins, event counts, and per-market errors.
- Latest observations >3 days old, inadequate recent history, or unseen series
  lead to withheld forecasts. The target date is anchored to the observation date,
  not automatically seven days after opening the app.
- Historical replay accepts only dates in the frozen model's held-out test period;
  observations after that date are excluded. Replay does not retrain on future data.
- Live comparisons reject unreported grades. Historical comparisons are illustrative
  and explicitly warn that broad variety labels do not verify equivalent quality.
- Expanding-prefix backtests keep the main model intact and report all runs, including
  failures versus baselines. Overlapping windows are not independent replications.

## Architecture

```text
Streamlit UI --HTTP--> FastAPI --> SQLite observations (demo / real)
                         |
                         +--> validation / audit / features / training
                         +--> application-owned model artifacts / evaluation
                         +--> official daily feed (optional key)
```

Training is serialized within the single backend process. The launcher runs one
worker. Bind to loopback only; this local prototype has no authentication and is
not designed for public exposure or multiworker concurrent training.

## Files and continuity
- `docs/CONTEXT.md`: user decisions, current state, next steps.
- `docs/PLAN.md`: detailed scope, implementation/evidence gates.
- `docs/MILESTONES.md`: acceptance tracker and verification outcomes.
- `docs/DATA_CARD.md`, `docs/MODEL_CARD.md`: methodology and limits.
- `docs/DEMO_SCRIPT.md`: presentation walkthrough.
- `docs/REAL_DATA_RESULTS.md`: actual pilot and rolling-backtest outcomes.
- `docs/THIRD_PARTY_DATA.md`: publisher, license, provenance limits.
- `backend/`: reusable data/ML services and FastAPI endpoints.
- `frontend/app.py`: Streamlit interface, API consumer only.
- `tests/`: correctness/leakage/security tests.
- `data/`: local database, uploaded records, CSV template.
- `artifacts/{demo,real}/`: model and evaluation bundles (generated).
- `work/`: local service records/logs, not presentation evidence.

## Evidence needed before claiming real impact
Audit actual market history and source publication delays; verify the feed; beat
stronger historical baselines on later dates; check warning calibration and rare
event counts; validate costs and interpretation with farmers/FPOs. Historical
cost comparisons are not proof that adopting the app increases farmer income.

## Sources
- https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi
- https://www.data.gov.in/help
- https://agmarknet.gov.in/
- https://www.kaggle.com/datasets/vandeetshah/india-commodity-wise-mandi-dataset
