"""End-to-end integration test with synthetic data."""

import json
import os
import pytest
import yaml
from src.db import create_database, get_all_lots
from src.filter import process_lots
from src.mapgen import generate_map, export_geojson


def _make_feature(bbl, owner, lot_area, lot_front, resid_far, zoning,
                  irr_lot_code=None, easements=0, land_use="11",
                  coords=None):
    """Create a synthetic MapPLUTO GeoJSON feature."""
    if coords is None:
        coords = [[[-74.006, 40.713], [-74.006, 40.714],
                    [-74.005, 40.714], [-74.005, 40.713], [-74.006, 40.713]]]
    return {
        "type": "Feature",
        "properties": {
            "bbl": bbl,
            "borough": "MN",
            "block": "00001",
            "lot": bbl[-4:],
            "address": f"{bbl} TEST ST",
            "ownername": owner,
            "lotarea": lot_area,
            "lotfront": lot_front,
            "lotdepth": 100,
            "landuse": land_use,
            "zonedist1": zoning,
            "residfar": resid_far,
            "builtfar": 0,
            "irrlotcode": irr_lot_code,
            "easements": easements,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": coords,
        },
    }


@pytest.fixture
def setup(tmp_path):
    """Set up synthetic data files and config."""
    features = [
        # Candidate: HPD-owned, below zoning min area (1600 < 1700 for R6)
        _make_feature("1000010001", "NYC DEPT OF HOUSING PRESERVATION & DEVELOPMENT",
                      1600, 25, 2.0, "R6"),
        # Candidate: DCAS-owned, no residential FAR
        _make_feature("1000010002", "DEPT OF CITYWIDE ADMIN SERVICES",
                      5000, 25, 0, "M1-2"),
        # Candidate: DOT-owned, has easements
        _make_feature("1000010003", "NYC DEPARTMENT OF TRANSPORTATION",
                      5000, 25, 2.0, "R6", easements=2),
        # NOT a candidate: HPD-owned but passes all tests
        _make_feature("1000010004", "NYC DEPT OF HOUSING PRESERVATION & DEVELOPMENT",
                      5000, 25, 2.0, "R6"),
        # NOT public: private owner
        _make_feature("1000010005", "JOHN SMITH",
                      200, 10, 0, "R6"),
    ]
    geojson = {"type": "FeatureCollection", "features": features}
    geojson_path = str(tmp_path / "mappluto.geojson")
    with open(geojson_path, "w") as f:
        json.dump(geojson, f)

    deed_records = [
        {
            "borough": "MANHATTAN", "block": "00001", "lot": "0002",
            "description_of_restriction": "Height limit 3 stories",
            "description_of_restriction_continued": "Imposed 2005",
        }
    ]
    deed_path = str(tmp_path / "deed_restrictions.json")
    with open(deed_path, "w") as f:
        json.dump(deed_records, f)

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    db_path = str(tmp_path / "scout.db")
    conn = create_database(db_path)

    return {
        "geojson_path": geojson_path,
        "deed_path": deed_path,
        "config": config,
        "conn": conn,
        "tmp_path": tmp_path,
    }


def test_full_pipeline(setup):
    conn = setup["conn"]
    config = setup["config"]

    stats = process_lots(
        setup["geojson_path"],
        setup["deed_path"],
        config,
        conn,
    )

    assert stats["total_fetched"] == 5
    assert stats["public_owned"] == 4
    assert stats["candidates"] == 3

    lots = get_all_lots(conn)
    assert len(lots) == 3

    bbls = {lot["bbl"] for lot in lots}
    assert "1000010001" in bbls
    assert "1000010002" in bbls
    assert "1000010003" in bbls
    assert "1000010004" not in bbls
    assert "1000010005" not in bbls

    hpd_lot = next(l for l in lots if l["bbl"] == "1000010001")
    reasons = json.loads(hpd_lot["fail_reasons"])
    assert any("below_zoning_min_area" in r for r in reasons)

    # Shadow risk should be present (unknown for GeoJSON test data without xcoord/ycoord)
    assert hpd_lot["shadow_risk"] is not None

    map_path = str(setup["tmp_path"] / "map.html")
    generate_map(conn, map_path, config["agencies"]["primary"])
    assert os.path.exists(map_path)

    geojson_path = str(setup["tmp_path"] / "candidates.geojson")
    count = export_geojson(conn, geojson_path)
    assert count == 3

    with open(geojson_path) as f:
        data = json.load(f)
    assert len(data["features"]) == 3

    conn.close()


def test_deed_restrictions_joined(setup):
    """Verify deed restrictions are joined to lots by BBL."""
    conn = setup["conn"]
    process_lots(
        setup["geojson_path"],
        setup["deed_path"],
        setup["config"],
        conn,
    )

    rows = conn.execute(
        "SELECT * FROM deed_restrictions WHERE bbl = '1000010002'"
    ).fetchall()
    assert len(rows) == 1
    assert "Height limit" in rows[0]["restriction"]

    conn.close()


def test_shadow_risk_with_flat_records(tmp_path):
    """Shadow risk is computed for flat JSON records with xcoord/ycoord."""
    records = [
        {
            "bbl": "2000010001", "borough": "BX", "borocode": "2",
            "block": "00001", "lot": "0001",
            "address": "1 TEST ST", "ownername": "NYC DEPT OF HOUSING PRESERVATION",
            "lotarea": "1600", "lotfront": "25", "lotdepth": "33",
            "landuse": "11", "zonedist1": "R6",
            "residfar": "2.0", "builtfar": "0",
            "irrlotcode": "", "easements": "0",
            "latitude": "40.82", "longitude": "-73.92",
            "xcoord": "1020000", "ycoord": "250000",
            "numfloors": "0",
        },
        # Tall building 60ft to the south of the candidate
        {
            "bbl": "2000010099", "borough": "BX", "borocode": "2",
            "block": "00001", "lot": "0099",
            "address": "99 TEST ST", "ownername": "JOHN SMITH",
            "lotarea": "2000", "lotfront": "20", "lotdepth": "100",
            "landuse": "1", "zonedist1": "R6",
            "residfar": "2.0", "builtfar": "1.0",
            "irrlotcode": "", "easements": "0",
            "latitude": "40.819", "longitude": "-73.92",
            "xcoord": "1020000", "ycoord": "249940",
            "numfloors": "12",
        },
    ]
    data_path = str(tmp_path / "mappluto.json")
    with open(data_path, "w") as f:
        json.dump(records, f)

    deed_path = str(tmp_path / "deeds.json")
    with open(deed_path, "w") as f:
        json.dump([], f)

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    db_path = str(tmp_path / "scout.db")
    conn = create_database(db_path)
    stats = process_lots(data_path, deed_path, config, conn)

    assert stats["candidates"] == 1
    lots = get_all_lots(conn)
    lot = lots[0]
    assert lot["shadow_risk"] == "high"
    detail = json.loads(lot["shadow_detail"])
    assert "south" in detail
    assert detail["south"]["numfloors"] == 12
    conn.close()
