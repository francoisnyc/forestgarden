"""Fetch data from NYC Open Data SODA API."""

import json
import logging
import os
import requests

log = logging.getLogger(__name__)


def _build_soda_url(base_url: str, limit: int, offset: int) -> str:
    separator = "&" if "?" in base_url else "?"
    params = f"$limit={limit}&$offset={offset}"
    return f"{base_url}{separator}{params}"


def fetch_mappluto(config: dict, output_path: str) -> int:
    """Download MapPLUTO GeoJSON from SODA API with pagination.

    Returns the total number of features downloaded.
    """
    source = config["sources"]["mappluto"]
    base_url = source["base_url"]
    batch_size = source["batch_size"]

    all_features = []
    offset = 0

    while True:
        url = _build_soda_url(base_url, limit=batch_size, offset=offset)
        log.info("Fetching MapPLUTO offset=%d ...", offset)

        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        offset += batch_size
        log.info("  fetched %d features (total: %d)", len(features), len(all_features))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    combined = {
        "type": "FeatureCollection",
        "features": all_features,
    }
    with open(output_path, "w") as f:
        json.dump(combined, f)

    log.info("MapPLUTO download complete: %d features", len(all_features))
    return len(all_features)


def fetch_deed_restrictions(config: dict, output_path: str) -> int:
    """Download DCAS Deed Restriction Database from SODA API.

    Returns the total number of records downloaded.
    """
    source = config["sources"]["deed_restrictions"]
    base_url = source["base_url"]
    batch_size = 5000

    all_records = []
    offset = 0

    while True:
        url = _build_soda_url(base_url, limit=batch_size, offset=offset)
        log.info("Fetching deed restrictions offset=%d ...", offset)

        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        records = resp.json()

        if not records:
            break

        all_records.extend(records)
        offset += batch_size

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_records, f)

    log.info("Deed restrictions download complete: %d records", len(all_records))
    return len(all_records)
