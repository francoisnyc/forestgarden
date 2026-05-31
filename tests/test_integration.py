"""End-to-end integration test with synthetic data."""

import json
import os
import pytest
import yaml
from src.db import create_database, get_all_lots
from src.filter import process_lots
from src.mapgen import generate_map, export_geojson


def _make_feature(bbl, owner, lot_area, lot_front, resid_far, zoning,
                  irr_lot_code=None, easements=0, land_use="11", coords=None):
    if coords is None:
        coords = [[[-74.006, 40.713], [-74.006, 40.714],
                   [-74.005, 40.714], [-74.005, 40.713], [-74.006, 40.713]]]
    return {
        "type": "Feature",
        "properties": {
            "bbl": bbl, "borough": "MN", "block": "00001", "lot": bbl[-4:],
            "address": f"{bbl} TEST ST", "ownername": owner,
            "lotarea": lot_area, "lotfront": lot_front, "lotdepth": 100,
            "landuse": land_use, "zonedist1": zoning, "residfar": resid_far,
            "builtfar": 0, "irrlotcode": irr_lot_code, "easements": easements,
        },
        "geometry": {"type": "Polygon", "coordinates": coords},
    }


@pytest.fixture
def setup(tmp_path):
    features = [
        _make_feature("1000010001", "NYC DEPT OF HOUSING PRESERVATION & DEVELOPMENT", 500, 25, 2.0, "R6"),
        _make_feature("1000010002", "DEPT OF CITYWIDE ADMIN SERVICES", 5000, 25, 0, "M1-2"),
        _make_feature("1000010003", "NYC DEPARTMENT OF TRANSPORTATION", 5000, 25, 2.0, "R6", easements=2),
        _make_feature("1000010004", "NYC DEPT OF HOUSING PRESERVATION & DEVELOPMENT", 5000, 25, 2.0, "R6"),
        _make_feature("1000010005", "JOHN SMITH", 200, 10, 0, "R6"),
    ]
    geojson_path = str(tmp_path / "mappluto.geojson")
    with open(geojson_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    deed_path = str(tmp_path / "deed_restrictions.json")
    with open(deed_path, "w") as f:
        json.dump([{
            "borough": "MANHATTAN", "block": "00001", "lot": "0002",
            "description_of_restriction": "Height limit 3 stories",
            "description_of_restriction_continued": "Imposed 2005",
        }], f)

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    conn = create_database(str(tmp_path / "scout.db"))
    return {"geojson_path": geojson_path, "deed_path": deed_path,
            "config": config, "conn": conn, "tmp_path": tmp_path}


def test_full_pipeline(setup):
    conn = setup["conn"]
    config = setup["config"]

    stats = process_lots(setup["geojson_path"], setup["deed_path"], config, conn)

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
    assert any("below_zoning_min_area" in r for r in json.loads(hpd_lot["fail_reasons"]))

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
    conn = setup["conn"]
    process_lots(setup["geojson_path"], setup["deed_path"], setup["config"], conn)
    rows = conn.execute("SELECT * FROM deed_restrictions WHERE bbl = '1000010002'").fetchall()
    assert len(rows) == 1
    assert "Height limit" in rows[0]["restriction"]
    conn.close()
