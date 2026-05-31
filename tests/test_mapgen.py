import json
import os
import pytest
from src.db import create_database, insert_lot
from src.mapgen import generate_map, export_geojson


@pytest.fixture
def db(tmp_path):
    conn = create_database(str(tmp_path / "test.db"))
    insert_lot(conn, {
        "bbl": "1000010001", "borough": "MN", "block": "00001", "lot": "0001",
        "address": "1 CENTRE ST", "owner_name": "HPD", "owner_agency": "HPD",
        "lot_area": 500.0, "lot_front": 15.0, "lot_depth": 33.0,
        "land_use": "11", "zoning": "R6", "resid_far": 0.0, "built_far": 0.0,
        "irr_lot_code": "Y", "compactness": 0.35, "easement_count": 0,
        "fail_reasons": json.dumps(["no_residential_far: resid_far=0"]),
        "flags": json.dumps({"vacant": True}),
        "wkt": "POLYGON ((-74.006 40.713, -74.006 40.714, -74.005 40.714, -74.005 40.713, -74.006 40.713))",
    })
    insert_lot(conn, {
        "bbl": "3000020002", "borough": "BK", "block": "00002", "lot": "0002",
        "address": "100 FLATBUSH AVE", "owner_name": "DOT", "owner_agency": "DOT",
        "lot_area": 800.0, "lot_front": 20.0, "lot_depth": 40.0,
        "land_use": "11", "zoning": "R6", "resid_far": 2.0, "built_far": 0.0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 1,
        "fail_reasons": json.dumps(["has_easements: count=1"]),
        "flags": json.dumps({}),
        "wkt": "POLYGON ((-73.978 40.685, -73.978 40.686, -73.977 40.686, -73.977 40.685, -73.978 40.685))",
    })
    yield conn
    conn.close()


def test_generate_map_creates_html(db, tmp_path):
    output_path = str(tmp_path / "map.html")
    primary = ["HPD", "DCAS", "MTA"]
    generate_map(db, output_path, primary)
    assert os.path.exists(output_path)
    with open(output_path) as f:
        html = f.read()
    assert "folium" in html.lower() or "leaflet" in html.lower()


def test_generate_map_contains_lot_data(db, tmp_path):
    output_path = str(tmp_path / "map.html")
    generate_map(db, output_path, ["HPD", "DCAS", "MTA"])
    with open(output_path) as f:
        html = f.read()
    assert "1000010001" in html
    assert "1 CENTRE ST" in html


def test_export_geojson_creates_file(db, tmp_path):
    output_path = str(tmp_path / "candidates.geojson")
    count = export_geojson(db, output_path)
    assert count == 2
    assert os.path.exists(output_path)

    with open(output_path) as f:
        data = json.load(f)
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 2


def test_export_geojson_includes_properties(db, tmp_path):
    output_path = str(tmp_path / "candidates.geojson")
    export_geojson(db, output_path)
    with open(output_path) as f:
        data = json.load(f)
    props = data["features"][0]["properties"]
    assert "bbl" in props
    assert "owner_agency" in props
    assert "fail_reasons" in props
