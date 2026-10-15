# Milestone tracker

Status legend: TODO / IN PROGRESS / DONE / EXTERNAL DATA GATE.

| ID | Milestone | Acceptance evidence | Status |
|---|---|---|---|
| M1 | Scope, architecture, persistent documentation | Context, plan, data contract written | DONE |
| M2 | Data ingestion and audit | CSV contract/idempotence/rollback tests passed | DONE |
| M3 | Classical ML pipeline | Calendar targets/embargo/future-isolation tests passed; initial synthetic report generated | DONE |
| M4 | FastAPI backend | API health/import/audit/history/error tests passed | DONE |
| M5 | Streamlit frontend | Four API-driven views; AppTest and live browser comparison passed | DONE |
| M6 | End-to-end verification | 49 tests passed; real replay/data-cleaning/backtest tests included; pip check clean | DONE |
| M7 | Internship handoff | Tested launchers, locked environment, README, cards, demo/viva script, context and verification | DONE |
| M8a | Published market-history pilot | 3,560 licensed historical records, four Pune markets, source/checksum/coverage saved | DONE |
| M8b | Historical empirical evaluation | Real holdout + three expanding-prefix backtests; negative baseline comparisons disclosed | DONE |
| M8c | Current authenticated updates | Successful authenticated refresh: 25 Maharashtra tomato records imported in 1.3 seconds on 2026-10-15; key rotation required after chat exposure | DONE (snapshot only) |
| M9 | Deployment software preparation | Production write controls, cohort selection, Compose, persistent seed, preflight and CI configuration | DONE |
| M10 | Actual container/host launch | Docker runtime unavailable here; hosting/TLS/restore must be verified on target host | HOST VERIFICATION REQUIRED |
| M11 | Validated current forecasting | Recent consistent history and prospective baseline evaluation still insufficient | EXTERNAL DATA / EVIDENCE GATE |

Historical validation now uses published market records rather than synthetic data.
It does not establish production effectiveness, equal produce quality, or income
improvements. Current snapshot fetch is verified. Original-report reconciliation
and prospective field effectiveness remain unverified. See RESUME_TOMORROW.md.

## Evidence summary
See REAL_DATA_RESULTS.md and VERIFICATION.md. Real price MAE 427.33 INR/quintal
(persistence selected); risk precision 53.85%, recall 13.29%, Brier 0.20994 vs
constant baseline 0.20724. No accuracy or farmer-savings claim. Records end in
February 2024 in the evaluated cohort. A separate authenticated snapshot adds 25
records dated 14 October 2026, bringing real rows to 3,585. New one-row series
lack forecast history. Historical replay is labeled and tested for future isolation.
