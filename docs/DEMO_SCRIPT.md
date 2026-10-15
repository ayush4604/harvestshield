# Five-minute internship demonstration

1. Introduce the problem: daily wholesale prices alone do not quantify next-week
   downside risk. HarvestShield combines classical forecasting, decline warnings,
   and cost-adjusted market comparison. Primary SDGs 1 and 2.
2. State that current demo markets/data are synthetic; no actual farmer savings or
   forecasting effectiveness has been proven.
3. Overview: show latest report dates and 180-day price chart for four markets.
4. Forecasts: show observation-to-target dates, forecast price, approximate range,
   >=15% drop risk, and calibrated/uncalibrated labeling.
5. Market comparison: enter 10 quintals and different TOTAL shipping/market costs.
   Inspect estimated revenue and overlapping intervals. Export the table.
6. Data & models: explain CSV contract and audit, compare candidate models, show
   chronological split/embargo, baseline skill, and actual held-out event counts.
7. Explain real-data path: historical AGMARKNET reports -> audit -> training;
   optional daily feed -> stored updates -> forecasts. Daily, not auction streaming.
8. Close with the empirical next step: audited real mandis and validation with
   a Farmer Producer Organisation, not a promise of guaranteed profit.

## Likely viva questions
- Why no random split? Future observations must not leak into historical forecasts.
- Why modal price? It is a consistently reported wholesale market indicator;
  it is not an average or a guaranteed individual transaction price.
- Why a seven-day gap? Training labels themselves extend seven days into the future.
- Why compare to persistence? Complex models must beat a meaningful simple forecast.
- Why might accuracy fail? Reporting gaps, abrupt supply/demand shocks, unobserved
  quality, and changing conditions.
- Is cost comparison ML? No. ML forecasts prices/risk; a transparent calculation
  uses user-entered costs to compare outcomes.
- What is original? The evaluated downside-warning and same-date cost comparison,
  especially under imperfect reporting—not invention of crop forecasting itself.

## Real-history demonstration now available
Select Real dataset. Explain that the four Pune series contain 3,560 published
historical records through 2024-02-01, not current quotes. On Forecasts, enable
Historical replay and use 2024-01-25. Show the as-of date and 2024-02-01 target.
The frozen model used only earlier training/validation periods; later records are
excluded from features. Show comparison only in explicitly labeled replay mode.

Open Data & models for three expanding-prefix backtests. Explain the actual
negative finding: learned price models did not beat persistence and risk Brier
did not beat constant risk. Report weak recall and interval undercoverage. This
is honest experimental work, not proven selling advice. Source attribution and
unreported grade are documented in THIRD_PARTY_DATA.md and REAL_DATA_RESULTS.md.
