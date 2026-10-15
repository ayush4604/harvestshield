# Deployment

## Single hosted service

Build the root Dockerfile directly from Git. A prepared `deployment/seed` is
optional: when absent, the image creates a clearly labeled synthetic demo.
Real observations require a separately prepared seed or authorized import.

Leave the start-command override empty, or use:

```text
python -m deployment.bootstrap web
```

The launcher starts FastAPI on internal loopback and Streamlit on the provider's
`PORT`. Set the health-check path to `/_stcore/health`. Keep production read-only
mode enabled. Attach persistent storage at `/state`, writable by UID/GID 10001.
Without persistent storage, imports and model changes do not survive replacement.
If the provider mounts volumes as root, configure supported volume permissions
before startup rather than making the data directory publicly writable.

For separate services, use `python -m deployment.bootstrap api` and
`python -m deployment.bootstrap ui`, and configure the UI's
`HARVESTSHIELD_API_URL` to the backend's private address. Set explicit backend
allowed hosts for that private address. Both roles honor the host's `PORT`.

## Docker Compose

### Automatic daily prices

The production backend enables its server-owned collector by default. Set a
private `DATA_GOV_API_KEY` service variable. It fetches immediately on first
startup, then every six hours; a saved next-attempt deadline prevents restart
storms from repeatedly calling the provider. Public refresh/import/train routes
remain blocked by `HARVESTSHIELD_READ_ONLY=true`.

Optional service variables (official source spellings):

```text
HARVESTSHIELD_AUTO_REFRESH=true
HARVESTSHIELD_FEED_STATE=Maharashtra
HARVESTSHIELD_FEED_COMMODITY=Tomato
HARVESTSHIELD_FEED_MARKET=
HARVESTSHIELD_REFRESH_SECONDS=21600
HARVESTSHIELD_FEED_MAX_PAGES=3
```

Only the backend needs these variables. Local development defaults to collection
disabled unless explicitly enabled. Use one backend worker and one service replica
with this SQLite deployment. Attach persistent storage at `/state`; otherwise data,
collection status and retry deadlines are lost on container replacement. Ensure
the volume is writable by UID/GID 10001. Configure the public domain target port
to match the Streamlit `PORT` (8080 in the initial Railway deployment).

Railway mounts volumes as root. Prefer arranging write access for UID 10001;
if unavailable, Railway documents `RAILWAY_RUN_UID=0` as its workaround for
non-root images. That runs the container as root, so use it only when needed for
volume permissions, not as a general application requirement.
See [Railway volume permissions](https://docs.railway.com/volumes#permissions).

`GET /api/feed/status` and the Real dashboard show collection state, filters,
last success, next attempt and truncation warnings. Failures retain existing data
and retry after 15 minutes with exponential backoff up to the regular interval.
The site remains available while the first fetch is running or the provider fails.
Keys and provider exception URLs are not included in status or worker logs.

Failure status includes an allowlisted `error_code` and optional numeric upstream
HTTP status, not the raw provider body. Examples: `HTTP_401` (authentication
rejected), `HTTP_403` (request denied; key or provider access restrictions),
`HTTP_429` (rate limit), `TIMEOUT`, `TLS`, `INVALID_JSON`, `SCHEMA`,
`NO_RECORDS`, `INVALID_RECORDS`, `DATA_CONFLICT`, and `STORAGE`.
For a denial, verify the key privately in the official API tester before assuming
the cloud configuration is wrong. Do not disable TLS verification, expose the
key/response URL, or repeatedly redeploy to evade provider rate limits.
The connector uses the API form's `filters[state.keyword]` parameter and still
validates returned state/crop/market identities before ingestion. This connector
revision invalidates the old schedule identity once so its first refresh runs
after deployment rather than retaining an old retry deadline.

The sidebar's State and Mandi/market controls are searchable dropdowns with custom
typing enabled. Suggestions come from imported identities and the configured
state, not a complete national mandi directory. Changing state clears the mandi
selection. These controls filter stored observations/forecasts and do not let
public visitors change the collection schedule. The administrator's manual feed
controls also support select-or-type names and remain write-protected in public
read-only deployments. An unknown name displays no matching stored records;
it does not create data or a prediction.

This endpoint supplies daily reports, not historical backfill. Automatic collection
does not train a model on a handful of new observations: sufficient exact-series
history and honest time-based evaluation are still required. Existing trained
models are preserved; no stale or unsupported forecasts are manufactured.

### Compose launch

Run one FastAPI backend and one Streamlit frontend on a Docker host with Compose
v2. The backend stays on the internal network. The frontend binds to host loopback
on port 8501, ready for a TLS reverse proxy. Use at least 4 GB RAM.

## Prepare a fresh checkout

Install the locked dependencies in a Python 3.13 virtual environment, then run:

```text
python -m backend.cli demo
python scripts/prepare_release.py
python scripts/check_deployment.py
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
```

The demo contains fictional data. Import and evaluate permitted historical
records separately for real-data analysis. See the README and
[source attribution](THIRD_PARTY_DATA.md).

Open http://127.0.0.1:8501. Set `HARVESTSHIELD_PORT` for another host port.
Release preparation refuses to overwrite an existing seed. Use a new staging
checkout for subsequent releases rather than deleting application data.

## Persistent state

The `harvest-state` volume holds SQLite data and model artifacts. On first start,
the backend verifies and copies the seed. Restarts preserve existing state.
Interrupted initialization requires a coherent restore instead of mixing files
from different generations.

Checksums detect corruption, not malicious replacement. Load only trusted,
application-owned model artifacts. Joblib files can execute code and must never
be accepted as public uploads.

## Administration

The default deployment blocks HTTP import, feed refresh, demo creation, training
and backtests. Reports, replay and cost comparisons remain available. The shared
Streamlit frontend must not receive an administrator credential.

Operators can use the backend CLI:

```text
docker compose exec backend python -m backend.cli audit --mode real
docker compose exec backend python -m backend.cli refresh --state Maharashtra --commodity Tomato
```

Daily refresh requires `DATA_GOV_API_KEY` in the backend environment. Use a host
secret manager or an ignored `.env` file. Compose reads `.env`; the Windows
launcher does not. Recreate the backend after changing its environment.

For a separate private operator API, set `HARVESTSHIELD_READ_ONLY=false` and a
random `HARVESTSHIELD_ADMIN_TOKEN` of at least 32 characters on the backend only.
Mutation requests require `Authorization: Bearer <token>`. Keep this service on
a private network. Production disables interactive API documentation and requires
explicit allowed host names.

## Public hosting

Place a TLS reverse proxy in front of the frontend port. Enable WebSocket
forwarding and keep Streamlit CORS/XSRF protections enabled. If required, set
Streamlit `browser.serverAddress` to the public domain. Add proxy authentication
for a private audience. Do not expose backend port 8000 or the data volume.

Example Nginx location inside a configured TLS server:

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

Validate the image build, health checks, browser WebSockets and resource limits
on the target host. Configure edge request limits for the expected audience.
This setup supports a single host, not replicated SQLite writers.

## Backups and upgrades

Back up the database and matching models together. Stop services before copying
the volume, or use SQLite's backup API for a live database snapshot. Preserve
ownership for UID/GID 10001 and test restoration into a separate volume.
Do not use `docker compose down --volumes` when data must be retained.

Before upgrading, make a tested backup and run the suite and seed preflight.
Then run `docker compose up -d --build --wait`. Existing volume data takes
precedence over a new image's seed. Roll back the image and matching state together.

## Checks

Backend readiness: `/ready`. Frontend health: `/_stcore/health`.
The preflight restores isolated state and tests model loading, held-out replay,
comparison and mutation denial. GitHub Actions includes Linux tests, a synthetic
demo image build, startup checks and inference. Check the actual workflow result
rather than assuming a configured workflow passed.

## References

- [Streamlit Docker deployment](https://docs.streamlit.io/deploy/tutorials/docker)
- [Streamlit configuration](https://docs.streamlit.io/develop/api-reference/configuration/config.toml)
- [Compose health dependencies](https://docs.docker.com/compose/how-tos/startup-order)
