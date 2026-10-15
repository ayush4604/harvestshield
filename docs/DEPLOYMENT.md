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
