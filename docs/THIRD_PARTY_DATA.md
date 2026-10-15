# Third-party historical data attribution

The current real-data pilot uses **India Commodity Wise Mandi Dataset**, version 1,
published by **Vandeet Shah** on Kaggle, last updated 2024-10-14.

Source: https://www.kaggle.com/datasets/vandeetshah/india-commodity-wise-mandi-dataset

Publisher metadata declares **Apache 2.0**. Metadata was obtained through Kaggle's
public API and is retained in data/raw/public_release/publisher_metadata.json.
The archive checksum and download information are in download_manifest.json;
cleaning decisions and pilot coverage are in pilot_manifest.json.
The deployment release retains publisher metadata and the original download
manifest under deployment/seed/provenance (copied into the persistent volume).
The Apache 2.0 license text accompanies the release in LICENSES/Apache-2.0.txt.

Only Tomato.csv was downloaded, not the full multicommodity bundle. Original
archive is retained. The pilot filters Maharashtra/Pune, four markets, reported
Local variety, 2021-01-01 through 2024-02-01. Missing grades are Unspecified,
not invented quality labels. No missing prices or future targets are imputed.

This is an attributed public historical release. Individual records have not
been independently reconciled against original daily government reports. The
publisher and government do not endorse HarvestShield. Records are stale for
current selling decisions; use only explicitly labeled historical replay until
recent, verified observations and grades are available.

The CEDA archive connector is a separate optional noncommercial research route.
It is not the source of the loaded pilot. Its public endpoint answered sample
queries but subsequently rate-limited downloads. Preserve its attribution/logo
requirements if importing it in future; do not bypass rate limits or authentication.

CEDA source and terms:
- https://agmarknet.ceda.ashoka.edu.in/
- https://ceda.ashoka.edu.in/api-terms-conditions/
