# HarvestShield deployment guide

Release 1.1.0, 15 October 2026. FastAPI backend and Streamlit frontend.

## What this release supports

Deploy the application as a read-only internship/research dashboard. Visitors can
inspect sources and evaluation, replay historical holdouts and compare historical
selling scenarios. The application continues to withhold unsupported current
forecasts. It does not claim validated real-world selling recommendations.

The release includes a consistent SQLite snapshot, application-owned trained
models, and evaluation reports. Historical data and the authenticated 14 October
2026 daily snapshot remain distinct series. No keys, virtual environments, raw
bulk downloads, personal submission documents or logs enter the archive/image.

## Supported topology

Run one backend process and one Streamlit process on one Docker host. The backend
stays on the internal Compose network. Only the frontend exposes a port, bound
to host loopback by default. SQLite data and model artifacts share a named
persistent volume. This is a single-host deployment, not a multi-replica design.

Use a host with Docker Engine and Compose v2, internet access for the first
image build, and at least 4 GB RAM. Linux x86-64 Python 3.13 binary-wheel
availability is checked separately from actual container execution.

## Launch from the prepared release

1. Extract the release ZIP and open a terminal in its HarvestShield directory.
2. If the Windows app is already using port 8501, stop it or choose another host
   port, e.g. HARVESTSHIELD_PORT=8502 in the shell/Compose .env file.
3. Run:

```text
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
```

Open http://127.0.0.1:8501. The backend health check uses /ready and the frontend
uses /_stcore/health. Streamlit waits for a healthy backend. Startup copies the
verified seed only into a new empty volume. Subsequent starts preserve state.

The seed manifest detects accidental corruption. It does not authenticate an
untrusted archive. Joblib can execute code: use only the application-owned model
files from a trusted release. Never accept uploaded pickle/joblib files.

## Build a fresh release from the development checkout

For a fresh Git clone, install requirements and generate the synthetic demo first.
The repository deliberately excludes runtime databases, model binaries and seeds:

```text
python -m venv .venv
# Activate the virtual environment using your operating system's command.
python -m pip install -r requirements-lock.txt
python -m backend.cli demo
python scripts/prepare_release.py
docker compose up --build -d --wait
```

This produces fictional demo data only. To reproduce the real pilot, use the
separate historical import/training instructions in README.md. Do not describe
the fresh-clone demo as live Indian market observations.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/prepare_release.py --archive C:\path\to\new-release.zip
.\.venv\Scripts\python.exe scripts/check_deployment.py
```

The seed directory must not already exist. This safety check prevents accidental
replacement of a staged release. Use a new staging checkout for another release,
or archive/move the exact deployment/seed directory after verifying it contains
only the generated snapshot. Never delete the project data or artifacts folders.

## Internet access and TLS

For an external launch, choose a host/domain and put a TLS reverse proxy in front
of the loopback frontend port. Configure WebSocket forwarding and appropriate
connection timeouts. Keep Streamlit CORS and XSRF protections enabled. Configure
Streamlit browser.serverAddress to the actual domain if required by the proxy.
Do not expose port 8000, Docker management, or the data volume to the internet.
Add authentication at the proxy if the audience must remain private.

Example Nginx server-location content (inside a correctly configured TLS server):

```nginx
location / {
    proxy_pass http://127.0.0.1:8501;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
    client_max_body_size 21m;
}
```

Apply connection/request limits at the edge appropriate to the audience. Run a
public load test before scaling traffic. This release does not claim a security
audit, high-availability support or tested multi-tenant administration.

## Administration and secrets

The shipped public deployment blocks import, demo bootstrap, training, backtests
and feed refresh over HTTP. The shared Streamlit process never receives an admin
token. Do not put an admin token in a public frontend environment: every visitor
would otherwise share that process's privilege.

An operator with shell access may use the CLI inside the backend container:

```text
docker compose exec backend python -m backend.cli audit --mode real
docker compose exec backend python -m backend.cli refresh --state Maharashtra --commodity Tomato
```

The daily refresh needs DATA_GOV_API_KEY in the backend's environment. Use a newly
rotated key entered privately through the host's secret-management facility or
an ignored local .env. Never paste it into chat, source files or command URLs.
Compose interpolates .env itself; the Windows launcher does not load .env.
No key is required for historical replay or seeded reports. Rotation requires
recreating the backend to replace its environment, not merely browser refresh.

If a separately secured operator service needs HTTP writes, explicitly set
HARVESTSHIELD_READ_ONLY=false and HARVESTSHIELD_ADMIN_TOKEN to a random value of
at least 32 characters on the backend only. Production fails startup without
that minimum. POST mutations require Authorization: Bearer <operator token>.
Restrict that operator service to a private network. Public /docs and OpenAPI
are disabled in production. Allowed host names must be explicit.

For training, select up to 20 historical series. The default excludes series
with fewer than 120 exact seven-day labels. New daily one-row series remain in
the database and audit but do not break historical training. The UI exposes the
eligible cohort when local administration is enabled. The CLI accepts repeated
--series-id arguments. Do not mix APMC aliases or infer unreported grades.

## Backup, restore and upgrades

Before an operator import/training run, take a coherent backup of both the SQLite
database and its model artifacts. For the simplest offline backup, stop both
services and copy the named volume to a dated backup using your host's volume
backup tool. Preserve ownership for UID/GID 10001. Do not copy a live SQLite file
without using SQLite's backup API. The release-preparation script uses that API.

Test restoration into a separate volume before relying on a backup. A database
without its matching models/reports is not a complete inference backup. The
bootstrap refuses partially initialized volumes instead of silently mixing seeds.
Do not use `docker compose down --volumes` on a deployment you need to retain.

Upgrade: make a tested backup, build the new image, run the regression suite and
isolated preflight, then `docker compose up -d --build --wait`. Existing volume
data takes precedence over a new seed. Model format/library changes require a
deliberate migration or retraining. Roll back image and matching state together.

## Verification boundary

Run `python scripts/check_deployment.py` against the generated seed. It restores
isolated state, loads both model modes, checks held-out replay and comparisons,
checks readiness and confirms production mutation denial. No external feed is
called and no main artifact is overwritten.

The supplied GitHub Actions workflow runs Linux tests, a synthetic-demo Docker build,
Compose health checks, model inference and a frontend HTTP smoke test. Creating the workflow does
not mean it has run: it runs only after the user pushes to their repository.

Docker is not installed on the authoring computer. Container image execution,
public-domain TLS/WebSockets, and host-specific persistence/restore still require
the documented checks on a Docker host before an external launch. No hosting
account, public deployment or paid service was created during preparation.

## Authoritative references

- [Streamlit Docker deployment](https://docs.streamlit.io/deploy/tutorials/docker)
- [Streamlit configuration](https://docs.streamlit.io/develop/api-reference/configuration/config.toml)
- [Docker Compose startup health dependencies](https://docs.docker.com/compose/how-tos/startup-order)
- [FastAPI container deployment](https://fastapi.tiangolo.com/deployment/docker/)
