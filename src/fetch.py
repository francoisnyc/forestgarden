"""Fetch data from NYC Open Data SODA API."""

import json
import logging
import os
import requests

log = logging.getLogger(__name__)


def _get_app_token() -> str:
    """Read optional SODA API app token from environment."""
    return os.environ.get("NYC_OPEN_DATA_TOKEN", "")


def _build_soda_url(base_url: str, limit: int, offset: int) -> str:
    separator = "&" if "?" in base_url else "?"
    params = f"$limit={limit}&$offset={offset}"
    return f"{base_url}{separator}{params}"


def fetch_mappluto(config: dict, output_path: str) -> int:
    """Download MapPLUTO data from SODA API with pagination.

    The SODA API returns flat JSON arrays (not GeoJSON). Each record has
    lat/lon fields instead of polygon geometry. We wrap the records in a
    simple dict for consistency with the rest of the pipeline.

    Returns the total number of records downloaded.
    """
    source = config["sources"]["mappluto"]
    base_url = source["base_url"]
    batch_size = source["batch_size"]

    max_records = source.get("max_records", 0)
    headers = {}
    app_token = _get_app_token()
    if app_token:
        headers["X-App-Token"] = app_token

    all_records = []
    offset = 0

    while True:
        url = _build_soda_url(base_url, limit=batch_size, offset=offset)
        log.info("Fetching MapPLUTO offset=%d ...", offset)

        resp = requests.get(url, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        # SODA JSON endpoint returns a flat array of records
        records = data if isinstance(data, list) else data.get("features", [])
        if not records:
            break

        all_records.extend(records)
        offset += batch_size
        log.info("  fetched %d records (total: %d)", len(records), len(all_records))

        if max_records and len(all_records) >= max_records:
            log.info("  reached max_records limit (%d), stopping", max_records)
            break
        if len(records) < batch_size:
            break

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_records, f)

    log.info("MapPLUTO download complete: %d records", len(all_records))
    return len(all_records)


def fetch_deed_restrictions(config: dict, output_path: str) -> int:
    """Download DCAS Deed Restriction Database from SODA API.

    Returns the total number of records downloaded.
    """
    source = config["sources"]["deed_restrictions"]
    base_url = source["base_url"]
    batch_size = 5000

    headers = {}
    app_token = _get_app_token()
    if app_token:
        headers["X-App-Token"] = app_token

    all_records = []
    offset = 0

    while True:
        url = _build_soda_url(base_url, limit=batch_size, offset=offset)
        log.info("Fetching deed restrictions offset=%d ...", offset)

        resp = requests.get(url, headers=headers, timeout=120)
        resp.raise_for_status()
        records = resp.json()

        if not records:
            break

        all_records.extend(records)
        offset += batch_size
        if len(records) < batch_size:
            break

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_records, f)

    log.info("Deed restrictions download complete: %d records", len(all_records))
    return len(all_records)


_WETLANDS_URL = "https://data.cityofnewyork.us/resource/p48c-iqtu.json"


def fetch_wetland_bbls(bbls_with_coords: list) -> set:
    """Check which candidate lots overlap NYC wetlands.

    Args:
        bbls_with_coords: list of (bbl, lat, lon) tuples

    Returns:
        Set of BBLs that are within 30m of a wetland polygon.
    """
    wetland_bbls = set()
    headers = {}
    app_token = _get_app_token()
    if app_token:
        headers["X-App-Token"] = app_token

    for i, (bbl, lat, lon) in enumerate(bbls_with_coords):
        try:
            resp = requests.get(
                _WETLANDS_URL,
                params={
                    "$where": f"within_circle(multipolygon,{lat},{lon},30)",
                    "$select": "classname",
                    "$limit": 1,
                },
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            if resp.json():
                wetland_bbls.add(bbl)
        except Exception:
            pass
        if (i + 1) % 100 == 0:
            log.info("Wetland check: %d/%d lots checked, %d in wetlands",
                     i + 1, len(bbls_with_coords), len(wetland_bbls))

    log.info("Wetland check complete: %d/%d lots in wetlands",
             len(wetland_bbls), len(bbls_with_coords))
    return wetland_bbls


_ARCGIS_MAPPLUTO_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "MAPPLUTO/FeatureServer/0/query"
)


def fetch_lot_polygons(bbls: list, output_path: str) -> int:
    """Fetch lot polygon geometry from DCP's ArcGIS MapPLUTO FeatureServer.

    Queries in batches of 100 BBLs. Saves a GeoJSON FeatureCollection
    mapping BBL -> polygon geometry.

    Returns the number of polygons fetched.
    """
    batch_size = 100
    all_features = []

    for i in range(0, len(bbls), batch_size):
        batch = bbls[i:i + batch_size]
        # BBLs in our DB may have decimals from SODA — strip to integer
        clean = [str(b).split(".")[0] for b in batch]
        where = "BBL IN (" + ",".join(clean) + ")"

        log.info("Fetching lot polygons batch %d-%d of %d ...",
                 i + 1, min(i + batch_size, len(bbls)), len(bbls))

        resp = requests.get(
            _ARCGIS_MAPPLUTO_URL,
            params={"where": where, "outFields": "BBL", "f": "geojson",
                    "resultRecordCount": batch_size},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        all_features.extend(features)

    collection = {"type": "FeatureCollection", "features": all_features}
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(collection, f)

    log.info("Lot polygons download complete: %d polygons for %d BBLs",
             len(all_features), len(bbls))
    return len(all_features)
