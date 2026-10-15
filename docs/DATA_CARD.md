# Data card

## Demonstration dataset
Generator: backend.data.demo_frame; seed 42. Four fictional mandis, Tomato,
Demo Standard variety, Demo Grade. Three years of daily observations initially
ending on the current IST date. Seasonal waves, noise, and artificial stress
episodes exercise regression and rare-event classification. No parameters are
validated against actual agricultural markets. Demo data never trains real models.

## Real observations
Source: user-imported permitted CSV reports or optional official AGMARKNET daily
feed through data.gov.in. User is responsible for documenting source/report dates,
transformation, crop variety/grade, and original units. Original uploaded CSV files
are stored by content hash; SQLite keeps normalized values and provenance.

Record key: mode + hash(state,district,market,commodity,variety,grade,unit) + date.
Prices INR/quintal. Only valid positive min <= modal <= max accepted. Conflicting
duplicate revisions require review, never silent mutation. Date formats are strict.

## Availability and representativeness
The published pilot has 3,560 rows in four Pune markets, 2021-01-01 to 2024-02-01,
from Vandeet Shah's Apache-2.0 Kaggle release. Original archive, metadata and
checksum are retained. See THIRD_PARTY_DATA.md and REAL_DATA_RESULTS.md. These
individual records have not been reconciled against original government reports.
Reporting varies by
market/date/crop. Absence is not zero price, and calendar gaps may be closures.
Latest daily snapshots cannot reconstruct missing historical years. Unknown grade
means Unspecified, not proof that produce qualities are equivalent.

## Labels and features
Target prices exist only at exactly t+7 days. Missing targets are excluded. This
can bias training toward frequently reporting markets/dates and must be discussed.
Features use only information known through t. Publication delays are not modeled
because report timestamps may be unavailable. No future weather or future arrivals.

## Privacy / licensing
No farmer identity, bank information, or individual trades are collected. Check
the actual report/resource's permission and attribution terms when importing.
Government credentials are environment-only and never part of this dataset.

## Audit
Coverage report: per-series range, counts, calendar gaps, exact-label counts,
latest price/date, freshness, and source. Numeric completeness alone does not
establish trustworthy labels or market suitability.

The optional CEDA connector is separate from this loaded pilot. It preserves raw
JSON/manifest, caches monthly windows, subdivides requests hitting the observed
1,000-row cap, throttles requests and respects Retry-After. Do not substitute
archive dates for current data. Grade absence is explicitly retained, not inferred.
