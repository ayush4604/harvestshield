"""Bounded, credential-safe connector for the official daily mandi feed."""
import os
import pandas as pd
import requests

from .data import ProjectError, Store, UNIT

ENDPOINT = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

ERROR_MESSAGES = {
    "KEY_MISSING": "DATA_GOV_API_KEY is not set in the backend environment. Historical CSV import works without a key.",
    "KEY_FORMAT": "The API key setting appears to contain quotes, whitespace, a URL or an unresolved reference. Set only the key value in the backend service variable.",
    "HTTP_400": "Government feed rejected the request (HTTP 400). Check source filter names and official state/crop/market spellings.",
    "HTTP_401": "Government feed rejected authentication (HTTP 401). Verify the service API key using the official API tester.",
    "HTTP_403": "Government feed denied this request (HTTP 403). Check the key in the official API tester; denial can also be caused by provider access restrictions on hosted requests.",
    "HTTP_429": "Government feed rate limit reached (HTTP 429). Automatic retries will back off; do not repeatedly restart the service.",
    "HTTP_OTHER": "Government feed returned an unsuccessful HTTP response. The service will retry without discarding stored data.",
    "TIMEOUT": "Government feed timed out. No data imported; try again later or narrow the market filter.",
    "CONNECTION": "Government feed connection failed. No data imported; check network availability.",
    "TLS": "Government feed TLS verification failed. Check the provider certificate/network; certificate verification remains enabled.",
    "INVALID_JSON": "Government feed returned invalid JSON, possibly an HTML error page. The provider may be unavailable.",
    "TOO_LARGE": "Feed response exceeded the safety size limit. Narrow the configured filters.",
    "SCHEMA": "Government feed response did not contain the expected records/schema. Check official API documentation and whether the API tester accepts the key.",
    "NO_RECORDS": "No feed records matched these filters. Check official market and crop spellings; the daily snapshot may not cover this market today.",
    "FILTER_MISMATCH": "Returned feed records did not match the requested state/crop/market. Nothing imported; check source filter documentation.",
    "DATA_CONFLICT": "Government feed conflicts with an already stored price for the same series/date. Import was rolled back; review the source revision before replacing observations.",
    "INVALID_RECORDS": "Government feed records failed date, price, unit or identity validation. Nothing from this refresh was imported; review the source schema.",
    "STORAGE": "The collector could not store the feed. Check persistent volume permissions, disk capacity and database availability.",
    "INTERNAL": "Automatic feed refresh encountered an internal error. Stored observations were retained; administrator investigation is required.",
}


class FeedError(ProjectError):
    """Allowlisted public diagnostic; never carries response bodies or URLs."""
    def __init__(self, code, status=502, upstream_status=None):
        self.code = code if code in ERROR_MESSAGES else "INTERNAL"
        self.upstream_status = upstream_status if isinstance(upstream_status, int) else None
        super().__init__(ERROR_MESSAGES[self.code], status)


def refresh_feed(store: Store, state: str, commodity: str, market: str = "", max_pages: int = 3):
    key = os.getenv("DATA_GOV_API_KEY", "").strip()
    if not key:
        raise FeedError("KEY_MISSING", 409)
    if any(c.isspace() for c in key) or key[:1] in ("'", '"') or "://" in key or "${{" in key:
        raise FeedError("KEY_FORMAT", 409)
    records = []
    for page in range(max_pages):
        params = {"api-key": key, "format": "json", "limit": 1000, "offset": page * 1000,
                  "filters[state.keyword]": state, "filters[commodity]": commodity}
        if market:
            params["filters[market]"] = market
        headers = {
            "User-Agent": os.getenv("HARVESTSHIELD_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/plain, */*",
        }
        try:
            with requests.get(ENDPOINT, params=params,
                              headers=headers,
                              timeout=(15, 60), stream=True, allow_redirects=False) as response:
                if response.status_code != 200:
                    code = f"HTTP_{response.status_code}"
                    raise FeedError(code if code in ERROR_MESSAGES else "HTTP_OTHER", upstream_status=response.status_code)
                chunks, size = [], 0
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > 5 * 1024 * 1024:
                        raise FeedError("TOO_LARGE")
                    chunks.append(chunk)
                import json
                payload = json.loads(b"".join(chunks))
        except ProjectError:
            raise
        except requests.Timeout:
            raise FeedError("TIMEOUT") from None
        except requests.exceptions.SSLError:
            raise FeedError("TLS") from None
        except requests.RequestException:
            # Exception text can contain a credential-bearing request URL.
            raise FeedError("CONNECTION") from None
        except ValueError:
            raise FeedError("INVALID_JSON") from None
        batch = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(batch, list):
            raise FeedError("SCHEMA")
        if not batch:
            break
        records.extend(batch)
        if len(batch) < 1000:
            break
    if not records:
        raise FeedError("NO_RECORDS", 404)
    frame = pd.DataFrame(records)
    frame.columns = [str(c).lower().strip() for c in frame.columns]
    # This adapter's price contract is the AGMARKNET INR/quintal feed.
    if "unit" not in frame:
        frame["unit"] = UNIT
    # Defend against ignored/upstream-changed filter parameters.
    if not {"state", "commodity", "market"}.issubset(frame.columns):
        raise FeedError("SCHEMA")
    mask = frame.state.astype(str).str.strip().str.casefold().eq(state.strip().casefold())
    mask &= frame.commodity.astype(str).str.strip().str.casefold().eq(commodity.strip().casefold())
    if market:
        mask &= frame.market.astype(str).str.strip().str.casefold().eq(market.strip().casefold())
    frame = frame[mask]
    if frame.empty:
        raise FeedError("FILTER_MISMATCH", 404)
    try:
        result = store.ingest(frame, "real", "AGMARKNET via data.gov.in daily feed (INR/quintal)")
    except ProjectError as exc:
        raise FeedError("DATA_CONFLICT" if exc.status == 409 else "INVALID_RECORDS", exc.status) from None
    result["note"] = "Daily reported snapshot, not auction streaming or historical backfill. Request is bounded; use CSV history for training. Confirm current source units/schema before field use."
    result["page_limit_reached"] = len(records) >= max_pages * 1000
    return result
