import json
import os
import pytest
from src.db import create_database, insert_lot, insert_deed_restriction, get_all_lots, get_lot_by_bbl


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_scout.db")


@pytest.fixture
def db(db_path):
    conn = create_database(db_path)
    yield conn
    conn.close()


def _make_lot(**overrides):
    defaults = {
        "bbl": "1000010001",
        "borough": "MN",
        "block": "00001",
        "lot": "0001",
        "address": "1 CENTRE ST",
        "owner_name": "CITY OF NEW YORK",
        "owner_agency": "DCAS",
        "lot_area": 500.0,
        "lot_front": 15.0,
        "lot_depth": 33.0,
        "land_use": "11",
        "zoning": "R6",
        "resid_far": 2.43,
        "built_far": 0.0,
        "irr_lot_code": "Y",
        "compactness": 0.35,
        "easement_count": 0,
        "fail_reasons": json.dumps(["below_zoning_min_area: 500 < 1700 (R6)"]),
        "flags": json.dumps({"vacant": True}),
        "wkt": "POLYGON ((-74.0 40.7, -74.0 40.701, -73.999 40.701, -73.999 40.7, -74.0 40.7))",
    }
    defaults.update(overrides)
    return defaults


def test_create_database_creates_file(db_path, db):
    assert os.path.exists(db_path)


def test_insert_and_retrieve_lot(db):
    lot = _make_lot()
    insert_lot(db, lot)
    result = get_lot_by_bbl(db, "1000010001")
    assert result is not None
    assert result["bbl"] == "1000010001"
    assert result["owner_agency"] == "DCAS"
    assert result["lot_area"] == 500.0


def test_insert_deed_restriction(db):
    lot = _make_lot()
    insert_lot(db, lot)
    insert_deed_restriction(db, {
        "bbl": "1000010001",
        "restriction": "No residential above 3 stories",
        "detail": "Imposed 2005-03-15 by DCAS",
    })
    result = get_lot_by_bbl(db, "1000010001")
    assert result is not None


def test_get_all_lots_returns_list(db):
    insert_lot(db, _make_lot(bbl="1000010001"))
    insert_lot(db, _make_lot(bbl="2000020002", borough="BX"))
    lots = get_all_lots(db)
    assert len(lots) == 2


def test_duplicate_bbl_replaces(db):
    insert_lot(db, _make_lot(bbl="1000010001", lot_area=500.0))
    insert_lot(db, _make_lot(bbl="1000010001", lot_area=600.0))
    result = get_lot_by_bbl(db, "1000010001")
    assert result["lot_area"] == 600.0
