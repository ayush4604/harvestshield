# Published historical pilot — results, 2026-10-15 IST

## Source and cohort
Publisher: Vandeet Shah; India Commodity Wise Mandi Dataset, Kaggle version 1,
Apache 2.0, release updated 2024-10-14. Individual source records have not been
independently reconciled against original daily government reports.

- Downloaded Tomato.csv only; 195,133,420 bytes uncompressed.
- Read 2,338,352 nationwide source records; retained Pune subset of 22,592.
- Pilot: Pune, Pune(Khadiki), Pune(Moshi), Pune(Pimpri); reported Local variety.
- Dates 2021-01-01 to 2024-02-01; **3,560 usable pilot records**.
- Zero invalid prices, identical duplicates, or conflicting dates in this selection.
- Source grade missing, stored as Unspecified; Local is a broad source category.
- No price filling, spline interpolation, or target imputation.
- Archive SHA256: 46e7e3f855ffc2b2ae350473a48d98f52e292a5669b7532bd245101d3c98b672

| Market | Rows | Calendar coverage | Exact seven-day labels |
|---|---:|---:|---:|
| Pune | 876 | 77.7% | 797 |
| Pune(Khadiki) | 909 | 80.7% | 783 |
| Pune(Moshi) | 899 | 79.8% | 839 |
| Pune(Pimpri) | 876 | 78.0% | 756 |

Calendar gaps can be closures or missing reporting. These are not business-day
completeness percentages. Dates without exact t+7 labels are excluded.

## Frozen chronological holdout
Train: 2,029 labeled rows, 2021-01-15 to 2023-01-08; latest label 2023-01-15.
Validation: 541 rows, 2023-01-18 to 2023-07-03; latest label 2023-07-10.
Test: 558 rows, 2023-07-11 to 2024-01-25; labels through 2024-02-01.
Preprocessing fitted only on train; seven-day gaps prevent label leakage.

Validation chose persistence over Ridge, Random Forest and gradient boosting for
price forecasting. **The learned price models did not outperform this baseline.**

- Test price MAE: **427.33 INR/quintal**; RMSE 796.52; WAPE 23.96%.
- Price improvement vs persistence: **0%** (persistence was selected).
- Risk model: Random Forest with validation sigmoid calibration.
- 158 actual defined drop events in 558 test observations.
- Warning precision: **53.85%**; recall: **13.29%**; F1: 0.2132.
- Risk Brier: **0.20994**, worse than constant-frequency baseline **0.20724**.
- Average precision 0.3872 vs event rate 0.2832; this does not establish calibrated
  probability quality or adequate recall.
- Approximate 80% interval covered only **61.83%** of test prices. Uncertainty
  was underestimated in this period; do not interpret it as a guaranteed bound.

## Expanding-prefix experiments
| Data cutoff | Selected price model | Test price MAE | Risk Brier | Constant risk Brier |
|---|---|---:|---:|---:|
| 2023-01-14 | Persistence | 277.56 | 0.20297 | 0.20297 |
| 2023-07-17 | Persistence | 275.72 | 0.12191 | 0.11152 |
| 2024-02-01 | Persistence | 427.33 | 0.20994 | 0.20724 |

Each prefix has its own earlier-only train/validation/test and embargo. Periods
overlap and are not independent replicates. All experiments are reported; none
justify better selling decisions or income gains. The main model is unchanged.

## Application behavior
Current-date forecasts are withheld for all four markets because the data is
stale. Select Real > Forecasts > Historical replay to replay 2024-01-25 (or an
allowed held-out date). Replay excludes all observations after that date. Market
comparison uses the same explicit replay date and an illustrative cost calculation.
Unreported grades block live selling comparisons. No advice to delay selling.

## Remaining external evidence
Current updates require the user's own government API key. Direct CEDA sample
requests succeeded but archive downloads were rate-limited; a recent-date query
returned no records. Do not evade either service's controls. Before field use,
obtain current, verified varieties/grades, reconcile original reports and evaluate
on genuinely future observations. Farmer/FPO interpretation is a future study.
