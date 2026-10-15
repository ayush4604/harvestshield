# HarvestShield detailed build plan

## Purpose
Classical-ML early warning for substantial wholesale crop price declines, with
seven-calendar-day forecasts and transparent cost-adjusted market comparisons.
The model supports decisions; it cannot guarantee transaction prices or profit.

## Product scope
Use one crop/variety/grade and 3–5 nearby mandis. Candidate tomato is provisional
until historical coverage is audited. User specifies quantity in quintals and
market-specific total transport/handling fees in INR. Compare the same target date.
No CNNs, devices, automated selling, unsupported savings claims, or storage advice.

## Milestone M1: reproducible scope and architecture
FastAPI owns all data/model operations; Streamlit consumes HTTP endpoints.
SQLite stores raw normalized observations and provenance. Model bundles and
evaluation JSON live under artifacts/{demo,real}. Markdown context persists decisions.

## Milestone M2: data contract, acquisition, audit
CSV required: date,state,district,market,commodity,variety,grade,unit,min_price,
max_price,modal_price. Unit is INR/quintal. Feed aliases may be normalized; missing
grade is 'Unspecified'. No conflating varieties or duplicates across markets.
Reject invalid dates, nonpositive prices, min/modal/max inconsistency, wrong units,
and conflicting duplicate observations. Identical repeats are idempotent.
Preserve the imported file with source notes. Audit date range, counts, daily gaps,
freshness, and number of exact seven-day labels per series. Gaps do not necessarily
mean missing business days; source records do not identify closures.
Synthetic demo: deterministic seed, explicitly fictional market names, separate DB
provenance and artifacts. Never merge demo with real training.
Daily government API: user-owned key in environment, paginated bounded requests,
allowlisted filters, safe errors without credential-bearing URLs. Snapshot updates
are not historical backfill. CSV import remains usable without credentials.

## Milestone M3: features, labels, temporal evaluation
Group by full series identity. Features: current price, previous reports with lag
ages, rolling means/volatility, recent returns, calendar cycles, market identity.
Avoid features requiring unverified publication timestamps. Exact-date label is
modal price at t+7; do not interpolate labels or cross series. Drop-risk definition
is a >=15% decline. Fit preprocessing on train only. Global dates across markets
define train/validation/test with seven-day embargo at boundaries.
Price baseline: persistence. Candidates: Ridge/linear, RandomForestRegressor,
HistGradientBoostingRegressor. Risk candidates: LogisticRegression,
RandomForestClassifier, HistGradientBoostingClassifier; constant-frequency baseline.
Select regression using validation MAE, classification using validation Brier
score. Report test MAE, RMSE, price-normalized error, precision, recall, F1,
average precision when both classes exist, Brier and reliability bins, per-market
results, date ranges, row counts, alert threshold, and regression baseline skill.
No guaranteed accuracy. Demo metrics only prove code behavior. Report probability
limitations for rare crash events. Use validation-only residual intervals as
empirical uncertainty; label them approximate and report held-out coverage.

## Milestone M4: API
GET health, datasets, audit, history, model report, forecasts.
POST demo bootstrap, CSV import, train, feed refresh, market comparison.
Structured schema validation and clear errors. Upload size/rows and external
requests bounded. Model training serialized; check training snapshot freshness.
Never load uploaded pickle/joblib models. Bind local services to loopback.

## Milestone M5: UI
Overview: provenance ribbon, latest observed prices, chart, coverage summary.
Forecasts: three-day freshness gate, forecast date, approximate range, drop risk,
historical reliability. Comparison: equivalent produce/date/unit constraints,
cost inputs, comparable estimated revenue, export CSV. Workspace: CSV template,
import, audit, train/report, live refresh status. Errors handled; raw keys not shown.
Streamlit never connects directly to database or runs model fitting.

## Milestone M6: verification
Tests for input contract and idempotence, conflicting duplicates, target alignment,
future isolation, temporal embargo, stale forecasts, cross-variety/date comparison,
cost units, endpoint flows, credential-safe feed failures. Train deterministic demo;
inspect actual metrics without forcing a favorable result. Use Streamlit AppTest
and local browser when available, plus HTTP readiness checks.

## Milestone M7: handoff
Provide Windows launch scripts, requirements, setup instructions, API examples,
CSV schema/template, data/model cards, limitations, walkthrough, context/status.
Keep launch output understandable. Real secrets never stored in source.

## Milestone M8: real-world evidence gate
Import permitted AGMARKNET history with source provenance; audit 2–3 years where
available, trading-date gaps, units, varieties, and crash sample counts. Validate
on later dates. If targets/class balance are inadequate, narrow scope or explicitly
change target; do not manufacture labels. Verify daily feed using own API key.
Consult a farmer/FPO on costs and interpretation before any field-readiness claim.

## Delivered historical pilot and additions
Direct CEDA archive sampling worked but bulk download was rate-limited. An
Apache-2.0-licensed published history supplied 3,560 Pune-district observations
for four Local tomato series (2021-01-01 to 2024-02-01). Raw archive, metadata,
checksum, normalized CSV, exclusions and coverage are retained. This is a
third-party historical release, not independently reconciled live government data.
Three expanding-prefix backtests are implemented and completed. Main model
artifacts are retained. Historical replay filters observations at the chosen date
and rejects dates before the held-out period. Unreported grades block live selling
comparisons; research replay labels that limitation explicitly. See results card.

## Sources
- https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi
- https://www.data.gov.in/help
- https://agmarknet.gov.in/

## Suggested student schedule
Week 1 data audit; Week 2 clean data/features/baselines; Week 3 model evaluation;
Week 4 application/comparison; Week 5 integration, verification, presentation.
The implementation session can deliver software sooner; data-quality and field
evaluation still require actual evidence rather than a schedule promise.
