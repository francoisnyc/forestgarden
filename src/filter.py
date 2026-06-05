"""Ownership matching and buildability filters."""

import json
import logging
from typing import Optional
from shapely.geometry import shape

from src.zoning import get_zoning_minimums

log = logging.getLogger(__name__)

# Map of agency abbreviations to keywords found in MapPLUTO OwnerName
_AGENCY_KEYWORDS = {
    "HPD": ["HPD", "HOUSING PRESERVATION", "HOUSING PRES"],
    "DCAS": ["DCAS", "CITYWIDE ADMIN", "DEPT OF CITYWIDE"],
    "MTA": ["MTA", "METROPOLITAN TRANSPORTATION", "METRO TRANS"],
    "DOT": ["DOT", "DEPT OF TRANSPORTATION", "DEPARTMENT OF TRANSPORTATION"],
    "DEP": ["DEP", "ENVIRONMENTAL PROTECTION"],
    "NYCHA": ["NYCHA", "HOUSING AUTHORITY"],
    "SCA": ["SCA", "SCHOOL CONSTRUCTION"],
    "DOE": ["DOE", "DEPT OF EDUCATION", "DEPARTMENT OF EDUCATION"],
    "PARKS": ["PARKS", "DPR", "DEPT OF PARKS"],
}


def match_agency(owner_name: Optional[str], agency_list: list) -> Optional[str]:
    """Match an OwnerName string to an agency abbreviation."""
    if not owner_name:
        return None
    owner_upper = owner_name.upper()
    for agency in agency_list:
        keywords = _AGENCY_KEYWORDS.get(agency, [agency])
        for keyword in keywords:
            if keyword in owner_upper:
                return agency
    return None


def compute_compactness(polygon) -> float:
    """Compute compactness ratio: polygon area / bounding box area."""
    bbox = polygon.bounds
    bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    if bbox_area == 0:
        return 0.0
    return polygon.area / bbox_area


def run_buildability_tests(lot: dict, config: dict) -> list:
    """Run all buildability tests on a lot. Returns list of fail reasons."""
    reasons = []
    zoning = lot.get("zoning")
    zoning_mins = get_zoning_minimums(zoning, config["zoning_minimums"])

    # Test 1: Below zoning minimum lot area
    if zoning_mins is not None:
        min_area = zoning_mins["area"]
        lot_area = lot.get("lot_area") or 0
        if lot_area < min_area:
            reasons.append(f"below_zoning_min_area: {lot_area} < {min_area} ({zoning})")

    # Test 2: Below zoning minimum frontage
    if zoning_mins is not None:
        min_front = zoning_mins["frontage"]
        lot_front = lot.get("lot_front") or 0
        if lot_front < min_front:
            reasons.append(f"below_zoning_min_frontage: {lot_front} < {min_front} ({zoning})")

    # Test 3: No residential FAR
    resid_far = lot.get("resid_far") or 0
    if resid_far == 0:
        reasons.append("no_residential_far: resid_far=0")

    # Test 4: Irregular geometry (both flags required)
    irr_code = lot.get("irr_lot_code")
    compactness = lot.get("compactness") or 1.0
    threshold = config["filters"]["compactness_ratio"]
    if irr_code and str(irr_code).strip().upper() in ("Y", "YES", "1") and compactness < threshold:
        reasons.append(f"irregular_geometry: compactness {compactness:.2f}")

    # Test 5: Has easements
    easement_count = lot.get("easement_count") or 0
    if easement_count > 0:
        reasons.append(f"has_easements: count={easement_count}")

    return reasons


def _normalize_records(raw_data):
    """Normalize input data to a list of (props, geom_json) tuples.

    Handles two formats:
    - GeoJSON FeatureCollection (from tests): {"type": "FeatureCollection", "features": [...]}
    - Flat JSON array (from live SODA API): [{...}, {...}, ...]
    """
    if isinstance(raw_data, dict) and "features" in raw_data:
        # GeoJSON FeatureCollection
        for feature in raw_data["features"]:
            yield feature.get("properties", {}), feature.get("geometry")
    elif isinstance(raw_data, list):
        # Flat JSON records from SODA API
        for record in raw_data:
            yield record, None
    else:
        return


def process_lots(data_path: str, deed_restrictions_path: str, config: dict, db_conn) -> dict:
    """Process raw MapPLUTO data and write candidates to database.

    Accepts both GeoJSON FeatureCollection (from tests) and flat JSON arrays
    (from live SODA API).
    """
    from src.db import insert_lot, insert_deed_restriction

    with open(data_path) as f:
        raw_data = json.load(f)

    deed_lookup = {}
    with open(deed_restrictions_path) as f:
        deed_records = json.load(f)
    for rec in deed_records:
        borough_code = _borough_name_to_code(rec.get("borough", ""))
        block = str(rec.get("block", "")).zfill(5)
        lot_num = str(rec.get("lot", "")).zfill(4)
        bbl = f"{borough_code}{block}{lot_num}"
        deed_lookup.setdefault(bbl, []).append(rec)

    all_agencies = config["agencies"]["primary"] + config["agencies"]["broad"]

    stats = {"total_fetched": 0, "public_owned": 0, "candidates": 0,
             "by_borough": {}, "by_agency": {}, "by_fail_reason": {}}

    for props, geom_json in _normalize_records(raw_data):
        stats["total_fetched"] += 1

        owner_name = props.get("ownername", "")
        agency = match_agency(owner_name, all_agencies)
        if agency is None:
            continue

        stats["public_owned"] += 1
        bbl = str(props.get("bbl", ""))
        borough = str(props.get("borough", ""))
        zoning = props.get("zonedist1", "")
        land_use = props.get("landuse", "")

        # Skip non-developable land uses and zonings (parks, transportation, etc.)
        excluded_lu = config["filters"].get("excluded_land_uses", [])
        excluded_z = config["filters"].get("excluded_zonings", [])
        if land_use in excluded_lu or zoning in excluded_z:
            continue

        # Compute geometry: use polygon if available (GeoJSON), else point from lat/lon
        compactness = 1.0
        wkt = None
        if geom_json:
            try:
                poly = shape(geom_json)
                compactness = compute_compactness(poly)
                wkt = poly.wkt
            except Exception:
                pass
        else:
            # Flat SODA records have latitude/longitude fields
            lat = props.get("latitude")
            lon = props.get("longitude")
            if lat and lon:
                try:
                    wkt = f"POINT ({float(lon)} {float(lat)})"
                except (ValueError, TypeError):
                    pass

        lot_record = {
            "lot_area": float(props.get("lotarea", 0) or 0),
            "lot_front": float(props.get("lotfront", 0) or 0),
            "resid_far": float(props.get("residfar", 0) or 0),
            "irr_lot_code": props.get("irrlotcode"),
            "compactness": compactness,
            "easement_count": int(props.get("easements", 0) or 0),
            "zoning": zoning,
        }

        fail_reasons = run_buildability_tests(lot_record, config)
        if not fail_reasons:
            continue

        stats["candidates"] += 1
        stats["by_borough"][borough] = stats["by_borough"].get(borough, 0) + 1
        stats["by_agency"][agency] = stats["by_agency"].get(agency, 0) + 1
        for reason in fail_reasons:
            key = reason.split(":")[0]
            stats["by_fail_reason"][key] = stats["by_fail_reason"].get(key, 0) + 1

        flags = {}
        if land_use == config["filters"]["vacant_land_use"]:
            flags["vacant"] = True
        if agency == "PARKS":
            flags["potential_greenthumb_conflict"] = True

        db_lot = {
            "bbl": bbl, "borough": borough,
            "block": str(props.get("block", "")), "lot": str(props.get("lot", "")),
            "address": props.get("address", ""), "owner_name": owner_name,
            "owner_agency": agency, "lot_area": lot_record["lot_area"],
            "lot_front": lot_record["lot_front"],
            "lot_depth": float(props.get("lotdepth", 0) or 0),
            "land_use": land_use, "zoning": zoning,
            "resid_far": lot_record["resid_far"],
            "built_far": float(props.get("builtfar", 0) or 0),
            "irr_lot_code": lot_record["irr_lot_code"],
            "compactness": compactness,
            "easement_count": lot_record["easement_count"],
            "fail_reasons": json.dumps(fail_reasons),
            "flags": json.dumps(flags),
            "wkt": wkt,
        }
        insert_lot(db_conn, db_lot)

        for deed_rec in deed_lookup.get(bbl, []):
            insert_deed_restriction(db_conn, {
                "bbl": bbl,
                "restriction": deed_rec.get("description_of_restriction", ""),
                "detail": deed_rec.get("description_of_restriction_continued", ""),
            })

    db_conn.commit()
    return stats


_BOROUGH_CODES = {
    "MANHATTAN": "1", "MN": "1", "BRONX": "2", "BX": "2",
    "BROOKLYN": "3", "BK": "3", "QUEENS": "4", "QN": "4",
    "STATEN ISLAND": "5", "SI": "5",
}


def _borough_name_to_code(name: str) -> str:
    return _BOROUGH_CODES.get(name.upper().strip(), "0")
