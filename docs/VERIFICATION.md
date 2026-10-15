# Verification evidence — 2026-10-15 (IST)

## Environment
- Windows, Python 3.13.6, isolated project .venv.
- FastAPI 0.143.1; Streamlit 1.66.0; pandas 2.3.3; NumPy 2.3.5;
  scikit-learn 1.9.1; uvicorn 0.54.0.
- Full dependency snapshot: requirements-lock.txt. `pip check` reports no broken
  requirements. NumPy constrained below 2.4 to avoid pandas 2.3 timedelta warning
  incompatibilities observed with 2.5.4.
- Existing global Python packages were not changed. Missing files in its Streamlit
  and old protobuf motivated a clean isolated project environment.

## Automated tests
- Complete suite: **31 passed**, 22.77 seconds in the final isolated dependency set.
- Only remaining warning: upstream Starlette TestClient deprecation for httpx.
- Backend: health/schema, upload/validation, audit/history, demo idempotence,
  unavailable models, missing feed key, bounded mock feed normalization/filtering,
  credential-safe errors, transaction rollback, future observation rejection,
  exact calendar labels, feature future isolation, temporal embargo, freshness,
  revenue units, duplicate/cross-variety/cross-date comparison rejection.
- Streamlit AppTest: all views, comparison submission, empty real mode, disabled
  training with no records, backend connection failure. Frontend talks to a real
  in-process FastAPI app via an HTTP adapter; no mocked forecast numbers.
- Relevant frontend tests rerun after responsive/sidebar/timezone/width updates.

## Running services
- Windows launcher successfully started hidden loopback backend/frontend.
- Backend `/health` returned service=harvestshield, status=ok, today_ist=2026-10-15,
  feed_key_configured=false.
- `/api/forecasts` returned 4 demo forecasts, zero withheld.
- Streamlit `/_stcore/health` returned HTTP 200.
- Final cleanup exposed Windows PowerShell 5.1 JSON-array pipeline behavior in
  the service record. Corrected parsing/serialization; stop verified interpreter
  children and redirector parents only after matching project path/role. Both
  ports subsequently refused connections (socket code 10061).
- Real observations: 0. Public live-feed reachability: AGMARKNET 403,
  unauthenticated data.gov.in timeout. Authenticated refresh remains unverified.

## Demo evaluation (SYNTHETIC ONLY)
- 4,380 fictional observations; last date 2026-10-15.
- Train: 2,780 rows; validation: 708; test: 780. Seven-day gaps enforced.
- Selected price model: Ridge; test MAE 105.0915 INR/quintal.
- Persistence test MAE: 119.9792; synthetic MAE improvement 12.41%.
- Selected risk model: Logistic Regression with validation sigmoid calibration.
- Test risk events: 52; precision 0.1607; recall 0.5192; F1 0.2455.
- Risk Brier 0.08249 vs constant-frequency baseline 0.06286 (lower is better).
  **Risk model fails this baseline comparison**; explicit report/UI warning added.
- Approximate 80% interval test coverage: 77.69%.
- These results do not demonstrate real-world prediction or farmer income impact.

## Manual browser inspection
- Overview rendered with provenance ribbon, counts, reported-price table, chart.
- Forecast page rendered prices/ranges, observation and target dates, risk estimates,
  model evidence, and baseline-failure warning. Model timestamp displayed in IST.
- Narrow in-app browser: sidebar defaults to auto and can be expanded/collapsed.
- Market comparison live form exercised with 12 quintals and INR 800 total transport
  for the first market; results/export verified during final browser check.

## Remaining evidence gate
Acquire permitted, sufficiently complete historical data for actual mandis;
validate units/varieties/reporting delays, train real models, evaluate on later
dates, configure own daily-feed key, and assess user interpretation with an FPO.
Neither software tests nor synthetic scores satisfy this gate.

## Follow-up completion — published real-history pilot
The user requested finishing remaining work and testing. Historical acquisition
was completed through a licensed public release after CEDA's public archive
sample succeeded but bulk requests returned 429. Limits were respected.

- Source: Vandeet Shah's Kaggle India Commodity Wise Mandi Dataset v1, Apache 2.0.
- Tomato.csv only downloaded; 2,338,352 source rows read. Pilot: 3,560 observations
  in four Pune markets, 2021-01-01 to 2024-02-01, reported Local variety.
- Raw archive, publisher metadata, checksum, coverage and cleaning manifest saved.
- Reimport test: zero new rows, 3,560 identical repeats skipped; no overwrite.
- Real chronological evaluation and three expanding-prefix backtests completed.
- Main artifact preserved during backtests, verified by hash in tests.
- Historical replay restricted to held-out dates; modifying future observations
  does not change replay predictions. Earlier training-period replay rejected.
- Live comparison rejects missing grade; replay is explicitly illustrative.
- Real API: current forecasts 0, withheld 4; replay 2024-01-25 returned 4 forecasts.
- Actual-data Streamlit integration checked stale banner, replay, and comparison.
- **Latest complete suite: 49 passed in 39.97 seconds; pip check clean.**
- Compile check passed after final acquisition-script error-handling updates.
- Browser verified real-data sidebar, source/grade/staleness labels, replay date
  and forecast cards. Screenshot saved as HarvestShield-Replay.jpg in chat outputs.

See REAL_DATA_RESULTS.md for the negative baseline findings and interval undercoverage.
These replace the earlier 'real rows=0 / history unavailable' status. Current
authenticated feed and prospective field effectiveness remain unverified.

## Authenticated connector follow-up (2026-10-15)
- Default Python Requests client timed out with both 1-row and 100-row requests.
  Controlled named-client probe returned 25 records in ~1.2 seconds.
- Explicit HarvestShield/1.0 User-Agent and JSON Accept header added; errors remain
  credential-safe and distinguish timeout, connection failure, and malformed JSON.
- Seven API tests passed in 6.59 seconds, including header and timeout checks.
- Complete regression suite after connector/UI changes: 49 passed in 31.37 seconds;
  only the existing upstream TestClient deprecation warning remains.
- Live backend refresh succeeded in 1.3 seconds: 25 inserted, no repeats; no
  historical data/model replacement. Key held only in process environment.
- User needs to rotate the chat-exposed credential; no key persisted in project files.
- Successful daily snapshot supersedes the earlier unverified connector status,
  not the unresolved forecast-quality/field-effectiveness limitations.

## Deployment preparation 1.1.0 (15 October 2026)
- Final complete suite: **67 passed in 163.00 seconds**. pip check and compileall
  passed. Existing upstream TestClient/httpx deprecation is the only warning.
- Production writes deny before JSON/multipart parsing. Token-gated private writes,
  host validation, body-size limits, hidden docs and readiness failures tested.
- Read-only/admin-protected Streamlit controls tested. No shared frontend token.
- 25 one-row fixture series no longer break a four-series historical cohort.
- SQLite online backup, seed checksums, idempotent initialization, interrupted-seed
  refusal, archive secret exclusions and state preservation tested.
- Linux CPython 3.13 wheel resolution/download succeeded for all 56 locked packages.
  This verifies dependency availability, not actual Linux/container execution.
- Restored real seed: 3,585 rows, four forecasts at replay 2024-01-25 and two-market
  cost comparison. Restored demo: 4,380 rows, four replay forecasts and comparison.
- Live production-mode 8008/8508 health OK, readiness OK, real replay 4 forecasts,
  attempted public training HTTP 403. No main model was overwritten.
- Docker runtime unavailable here. Compose/build and target-host TLS/WebSockets,
  persistence/restore/load tests are explicitly not claimed as completed.
