# Model card

## Intended use
Internship prototype exploring seven-day-ahead modal wholesale price forecasts
and >=15% price-drop warnings. Same-date, equivalent-produce cost comparisons.
Not guaranteed selling quotes, personalized investment advice, or income evidence.

## Classical algorithms
Price: persistence, Ridge, Random Forest, HistGradientBoosting.
Risk: DummyClassifier prior, Logistic Regression, Random Forest,
HistGradientBoosting. No deep learning or hardware.

## Training methodology
Preprocessing fitted on training only. Global date boundaries: approximately 65%
train, 17% validation, 18% test, minus seven-day boundary embargoes. Model selection
uses validation MAE/Brier. Calibration, where feasible, fits sigmoid on validation
probabilities, never test. This reuses validation for selection/calibration; the
independent test is the final evaluation. Alert threshold fixed at 0.30.

## Uncertainty
Approximate 80% intervals use validation residual 10th/90th quantiles pooled across
markets. These are empirical ranges, not guaranteed safety/profit bounds. Report
test coverage. Risk calibration is skipped with insufficient validation class
counts; UI states uncalibrated. Sparse test events generate a warning.

## Freshness and supported cases
Forecasts limited to series represented in training, adequate recent feature
history, and observations within three days of IST current date. New observations
may be used by an existing model; model training timestamp is visible. Target
date remains observation date +7. Same crop/variety/grade/date/unit enforced in
comparison. Unknown produce grading and source delays remain limitations.

## Evaluation
Artifact evaluation.json contains date boundaries, row/event counts, candidates,
selected models, regression and persistence test metrics, baseline improvement,
risk precision/recall/F1/Brier/AP, reliability bins, and per-market MAE/RMSE/WAPE.
Never manually improve or invent scores. Negative skill or baseline selection
must be disclosed. Test data is not used to alter model selection.

## Real-world limitations
Prices can change because of events absent from features. Missing exact-date
labels create selection bias. Historical backtests omit actual farmer quality,
negotiation, commissions, travel disruptions, and adoption behavior. More mandis
and multiple seasonal holdouts are needed before generalization claims. Retraining
and drift monitoring require operational decisions beyond this local prototype.

## Artifact security
Load application-created joblib only; no upload/load endpoint for serialized
models. Do not run untrusted model files obtained from another person.
## Historical pilot outcome
Actual published market-history holdout: learned price models failed persistence;
selected persistence MAE 427.33 INR/quintal. Risk Brier 0.20994 failed constant
baseline 0.20724; precision 53.85%, recall 13.29%. Nominal 80% empirical interval
coverage was only 61.83%. See REAL_DATA_RESULTS.md. These are negative findings,
not production effectiveness evidence.
