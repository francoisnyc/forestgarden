# Scout & Vector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI pipeline that downloads NYC municipal lot data, filters for publicly-owned "unbuildable" parcels, and outputs a SpatiaLite database, interactive map, and GeoJSON export.

**Architecture:** Stage-based CLI (`scout.py fetch|filter|map|run|stats`) with independent modules under `src/`. Each stage reads from the previous stage's output — raw files → database → map/export. All thresholds and endpoints live in `config.yaml`.

**Tech Stack:** Python 3.10+, requests, geopandas, shapely, spatialite, folium, pyyaml, pytest

---

## Task 0: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `.gitignore`
- Create: `src/__init__.py`

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/francois/dev/forestgarden
git init
```

- [ ] **Step 2: Create `.gitignore`**

Create `.gitignore`:

```
data/raw/
data/scout.db
output/
__pycache__/
*.pyc
.venv/
.superpowers/
```

- [ ] **Step 3: Create `requirements.txt`**

Create `requirements.txt`:

```
requests>=2.31
geopandas>=0.14
shapely>=2.0
folium>=0.15
pyyaml>=6.0
pytest>=8.0
```

- [ ] **Step 4: Create `config.yaml`**

Create `config.yaml`:

```yaml
sources:
  mappluto:
    base_url: "https://data.cityofnewyork.us/resource/f888-ni5f.geojson"
    batch_size: 5000
  deed_restrictions:
    base_url: "https://data.cityofnewyork.us/resource/rfu7-paqe.json"

agencies:
  primary:
    - "HPD"
    - "DCAS"
    - "MTA"
  broad:
    - "DOT"
    - "DEP"
    - "NYCHA"
    - "SCA"
    - "DOE"
    - "PARKS"

zoning_minimums:
  R1-1:  { area: 7125, frontage: 75 }
  R1-2:  { area: 4750, frontage: 50 }
  R1-2A: { area: 4750, frontage: 50 }
  R2:    { area: 2850, frontage: 30 }
  R2A:   { area: 2850, frontage: 30 }
  R2X:   { area: 2850, frontage: 30 }
  R3X:   { area: 2850, frontage: 30 }
  R3-1:  { area: 2850, frontage: 30 }
  R3-2:  { area: 2850, frontage: 30 }
  R3A:   { area: 2375, frontage: 25 }
  R4:    { area: 2850, frontage: 30 }
  R4-1:  { area: 2375, frontage: 25 }
  R4A:   { area: 2375, frontage: 25 }
  R4B:   { area: 2375, frontage: 25 }
  R5:    { area: 2850, frontage: 30 }
  R5A:   { area: 2375, frontage: 25 }
  R5B:   { area: 2375, frontage: 25 }
  R5D:   { area: 2375, frontage: 25 }
  R6:    { area: 1700, frontage: 18 }
  R7:    { area: 1700, frontage: 18 }
  R8:    { area: 1700, frontage: 18 }
  R9:    { area: 1700, frontage: 18 }
  R10:   { area: 1700, frontage: 18 }
  default: { area: 1700, frontage: 18 }

filters:
  compactness_ratio: 0.4
  vacant_land_use: "11"
```

- [ ] **Step 5: Create empty `src/__init__.py`**

Create `src/__init__.py` as an empty file.

- [ ] **Step 6: Create directories**

```bash
mkdir -p data/raw output
```

- [ ] **Step 7: Set up virtual environment and install dependencies**

```bash
cd /Users/francois/dev/forestgarden
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 8: Commit scaffolding**

```bash
git add .gitignore requirements.txt config.yaml src/__init__.py
git commit -m "chore: project scaffolding with config and dependencies"
```

---

## Task 1: Zoning Lookup Module

**Files:**
- Create: `src/zoning.py`
- Create: `tests/test_zoning.py`

This module provides a single function: given a zoning district string (e.g. `"R6"`, `"R3A"`, `"M1-2"`), return the minimum lot area and frontage. It reads thresholds from config.yaml. Non-residential zones (M, C, parks) have no residential minimum — return `None` to signal "no residential use possible."

- [ ] **Step 1: Write the failing tests**

Create `tests/test_zoning.py`:

```python
import pytest
import yaml
from src.zoning import get_zoning_minimums


@pytest.fixture
def config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def test_exact_match_r6(config):
    result = get_zoning_minimums("R6", config["zoning_minimums"])
    assert result == {"area": 1700, "frontage": 18}


def test_exact_match_r1_1(config):
    result = get_zoning_minimums("R1-1", config["zoning_minimums"])
    assert result == {"area": 7125, "frontage": 75}


def test_subdistrict_match_r6a(config):
    """R6A is not in config, but R6 is. Should match R6."""
    result = get_zoning_minimums("R6A", config["zoning_minimums"])
    assert result == {"area": 1700, "frontage": 18}


def test_subdistrict_match_r5b(config):
    """R5B is explicitly in config."""
    result = get_zoning_minimums("R5B", config["zoning_minimums"])
    assert result == {"area": 2375, "frontage": 25}


def test_manufacturing_zone_returns_none(config):
    """M zones have no residential minimums."""
    result = get_zoning_minimums("M1-2", config["zoning_minimums"])
    assert result is None


def test_commercial_zone_returns_none(config):
    """C zones have no residential minimums."""
    result = get_zoning_minimums("C4-4A", config["zoning_minimums"])
    assert result is None


def test_park_zone_returns_none(config):
    result = get_zoning_minimums("PARK", config["zoning_minimums"])
    assert result is None


def test_empty_string_returns_default(config):
    result = get_zoning_minimums("", config["zoning_minimums"])
    assert result == {"area": 1700, "frontage": 18}


def test_none_returns_default(config):
    result = get_zoning_minimums(None, config["zoning_minimums"])
    assert result == {"area": 1700, "frontage": 18}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/francois/dev/forestgarden
source .venv/bin/activate
pytest tests/test_zoning.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.zoning'`

- [ ] **Step 3: Write the implementation**

Create `src/zoning.py`:

```python
"""Zoning district minimum lot size lookup."""


# Zones that have no residential use — return None
_NON_RESIDENTIAL_PREFIXES = ("M", "C", "PARK", "BPC")


def get_zoning_minimums(
    zone_dist: str | None, zoning_config: dict
) -> dict | None:
    """Return {"area": float, "frontage": float} for a zoning district.

    Returns None if the zone doesn't allow residential use (M, C, PARK, etc.).
    Falls back to the "default" entry for unknown residential zones.
    """
    if not zone_dist:
        return dict(zoning_config["default"])

    zone_dist = zone_dist.strip().upper()

    for prefix in _NON_RESIDENTIAL_PREFIXES:
        if zone_dist.startswith(prefix):
            return None

    # Try exact match first
    if zone_dist in zoning_config:
        return dict(zoning_config[zone_dist])

    # Try stripping trailing letter variants (e.g., R6A → R6)
    base = zone_dist.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if base and base in zoning_config:
        return dict(zoning_config[base])

    return dict(zoning_config["default"])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_zoning.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/zoning.py tests/test_zoning.py
git commit -m "feat: zoning district minimum lot size lookup"
```

---

## Task 2: Database Module

**Files:**
- Create: `src/db.py`
- Create: `tests/test_db.py`

This module handles SpatiaLite database creation, schema setup, and insert/query helpers. It creates two tables: `lots` and `deed_restrictions`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.db'`

- [ ] **Step 3: Write the implementation**

Create `src/db.py`:

```python
"""SpatiaLite database schema and helpers."""

import sqlite3


def create_database(path: str) -> sqlite3.Connection:
    """Create a SpatiaLite database with the lots and deed_restrictions tables."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Try to load SpatiaLite extension; fall back to plain SQLite if unavailable
    try:
        conn.enable_load_extension(True)
        conn.load_extension("mod_spatialite")
        conn.execute("SELECT InitSpatialMetaData(1)")
        has_spatialite = True
    except (OSError, sqlite3.OperationalError):
        has_spatialite = False

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lots (
            bbl TEXT PRIMARY KEY,
            borough TEXT,
            block TEXT,
            lot TEXT,
            address TEXT,
            owner_name TEXT,
            owner_agency TEXT,
            lot_area REAL,
            lot_front REAL,
            lot_depth REAL,
            land_use TEXT,
            zoning TEXT,
            resid_far REAL,
            built_far REAL,
            irr_lot_code TEXT,
            compactness REAL,
            easement_count INTEGER,
            fail_reasons TEXT,
            flags TEXT
        );

        CREATE TABLE IF NOT EXISTS deed_restrictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bbl TEXT REFERENCES lots(bbl),
            restriction TEXT,
            detail TEXT
        );
    """)

    if has_spatialite:
        try:
            conn.execute(
                "SELECT AddGeometryColumn('lots', 'geometry', 4326, 'GEOMETRY', 'XY')"
            )
        except sqlite3.OperationalError:
            pass  # Column already exists
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lots_geometry_fallback (
                bbl TEXT PRIMARY KEY REFERENCES lots(bbl),
                wkt TEXT
            )
        """)

    conn.commit()
    return conn


def _has_spatialite(conn: sqlite3.Connection) -> bool:
    try:
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='geometry_columns'"
        ).fetchone()
        return result is not None
    except sqlite3.OperationalError:
        return False


def insert_lot(conn: sqlite3.Connection, lot: dict) -> None:
    """Insert or replace a lot record."""
    wkt = lot.pop("wkt", None)

    conn.execute("""
        INSERT OR REPLACE INTO lots (
            bbl, borough, block, lot, address, owner_name, owner_agency,
            lot_area, lot_front, lot_depth, land_use, zoning,
            resid_far, built_far, irr_lot_code, compactness,
            easement_count, fail_reasons, flags
        ) VALUES (
            :bbl, :borough, :block, :lot, :address, :owner_name, :owner_agency,
            :lot_area, :lot_front, :lot_depth, :land_use, :zoning,
            :resid_far, :built_far, :irr_lot_code, :compactness,
            :easement_count, :fail_reasons, :flags
        )
    """, lot)

    if wkt:
        if _has_spatialite(conn):
            conn.execute(
                "UPDATE lots SET geometry = GeomFromText(?, 4326) WHERE bbl = ?",
                (wkt, lot["bbl"]),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO lots_geometry_fallback (bbl, wkt) VALUES (?, ?)",
                (lot["bbl"], wkt),
            )

    conn.commit()


def insert_deed_restriction(conn: sqlite3.Connection, record: dict) -> None:
    """Insert a deed restriction record."""
    conn.execute("""
        INSERT INTO deed_restrictions (bbl, restriction, detail)
        VALUES (:bbl, :restriction, :detail)
    """, record)
    conn.commit()


def get_lot_by_bbl(conn: sqlite3.Connection, bbl: str) -> dict | None:
    """Fetch a single lot by BBL."""
    row = conn.execute("SELECT * FROM lots WHERE bbl = ?", (bbl,)).fetchone()
    if row is None:
        return None
    return dict(row)


def get_all_lots(conn: sqlite3.Connection) -> list[dict]:
    """Fetch all lots."""
    rows = conn.execute("SELECT * FROM lots").fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/test_db.py
git commit -m "feat: SpatiaLite database schema and helpers"
```

---

## Task 3: Fetch Module

**Files:**
- Create: `src/fetch.py`
- Create: `tests/test_fetch.py`

This module downloads MapPLUTO data via the SODA API (paginated GeoJSON) and the DCAS Deed Restriction dataset. Saves raw files to `data/raw/`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fetch.py`:

```python
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from src.fetch import fetch_mappluto, fetch_deed_restrictions, _build_soda_url


def test_build_soda_url_first_page():
    url = _build_soda_url(
        base_url="https://data.cityofnewyork.us/resource/f888-ni5f.geojson",
        limit=5000,
        offset=0,
    )
    assert "$limit=5000" in url
    assert "$offset=0" in url


def test_build_soda_url_with_offset():
    url = _build_soda_url(
        base_url="https://data.cityofnewyork.us/resource/f888-ni5f.geojson",
        limit=5000,
        offset=10000,
    )
    assert "$offset=10000" in url


@patch("src.fetch.requests.get")
def test_fetch_mappluto_saves_file(mock_get, tmp_path):
    feature = {
        "type": "Feature",
        "properties": {"bbl": "1000010001", "ownername": "HPD"},
        "geometry": {"type": "Polygon", "coordinates": [[[-74, 40], [-74, 41], [-73, 41], [-73, 40], [-74, 40]]]},
    }
    geojson_page = {"type": "FeatureCollection", "features": [feature]}
    empty_page = {"type": "FeatureCollection", "features": []}

    response_1 = MagicMock()
    response_1.status_code = 200
    response_1.json.return_value = geojson_page

    response_2 = MagicMock()
    response_2.status_code = 200
    response_2.json.return_value = empty_page

    mock_get.side_effect = [response_1, response_2]

    config = {
        "sources": {
            "mappluto": {
                "base_url": "https://data.cityofnewyork.us/resource/f888-ni5f.geojson",
                "batch_size": 5000,
            }
        }
    }

    output_path = str(tmp_path / "mappluto.geojson")
    count = fetch_mappluto(config, output_path)
    assert count == 1
    assert os.path.exists(output_path)

    with open(output_path) as f:
        data = json.load(f)
    assert len(data["features"]) == 1


@patch("src.fetch.requests.get")
def test_fetch_deed_restrictions_saves_file(mock_get, tmp_path):
    records = [
        {"borough": "MANHATTAN", "block": "00001", "lot": "0001",
         "description_of_restriction": "Height limit", "description_of_restriction_continued": "Max 3 stories"}
    ]

    response_1 = MagicMock()
    response_1.status_code = 200
    response_1.json.return_value = records

    response_2 = MagicMock()
    response_2.status_code = 200
    response_2.json.return_value = []

    mock_get.side_effect = [response_1, response_2]

    config = {
        "sources": {
            "deed_restrictions": {
                "base_url": "https://data.cityofnewyork.us/resource/rfu7-paqe.json",
            }
        }
    }

    output_path = str(tmp_path / "deed_restrictions.json")
    count = fetch_deed_restrictions(config, output_path)
    assert count == 1
    assert os.path.exists(output_path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_fetch.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.fetch'`

- [ ] **Step 3: Write the implementation**

Create `src/fetch.py`:

```python
"""Fetch data from NYC Open Data SODA API."""

import json
import logging
import os
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)


def _build_soda_url(base_url: str, limit: int, offset: int) -> str:
    separator = "&" if "?" in base_url else "?"
    params = urlencode({"$limit": limit, "$offset": offset})
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fetch.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fetch.py tests/test_fetch.py
git commit -m "feat: SODA API data fetcher for MapPLUTO and deed restrictions"
```

---

## Task 4: Filter Module

**Files:**
- Create: `src/filter.py`
- Create: `tests/test_filter.py`

This is the core logic. It reads raw MapPLUTO GeoJSON, identifies publicly-owned lots, runs the five buildability tests, computes `fail_reasons`, and writes candidates to the database. Also joins deed restrictions by BBL.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_filter.py`:

```python
import json
import pytest
import yaml
from src.filter import match_agency, compute_compactness, run_buildability_tests, process_lots
from shapely.geometry import Polygon, box


@pytest.fixture
def config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


# --- Agency matching ---

def test_match_agency_hpd():
    assert match_agency("NYC DEPT OF HOUSING PRESERVATION & DEVELOPMENT", ["HPD", "DCAS", "MTA"]) == "HPD"


def test_match_agency_dcas():
    assert match_agency("DEPT OF CITYWIDE ADMIN SERVICES", ["HPD", "DCAS", "MTA"]) == "DCAS"


def test_match_agency_mta():
    assert match_agency("METROPOLITAN TRANSPORTATION AUTHORITY", ["HPD", "DCAS", "MTA"]) == "MTA"


def test_match_agency_dot():
    assert match_agency("NYC DEPARTMENT OF TRANSPORTATION", ["DOT", "DEP"]) == "DOT"


def test_match_agency_no_match():
    assert match_agency("JOHN SMITH", ["HPD", "DCAS"]) is None


def test_match_agency_none_input():
    assert match_agency(None, ["HPD"]) is None


# --- Compactness ---

def test_compactness_square():
    """A square has compactness 1.0."""
    poly = box(0, 0, 10, 10)
    assert compute_compactness(poly) == pytest.approx(1.0)


def test_compactness_triangle():
    """A triangle inside a bounding box has compactness 0.5."""
    poly = Polygon([(0, 0), (10, 0), (5, 10), (0, 0)])
    assert compute_compactness(poly) == pytest.approx(0.5)


def test_compactness_narrow_sliver():
    """A very thin triangle has low compactness."""
    poly = Polygon([(0, 0), (100, 0), (50, 1), (0, 0)])
    result = compute_compactness(poly)
    assert result < 0.4


# --- Buildability tests ---

def test_fails_area_below_zoning_min(config):
    lot = {
        "lot_area": 500, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("below_zoning_min_area" in r for r in reasons)


def test_fails_frontage_below_zoning_min(config):
    lot = {
        "lot_area": 5000, "lot_front": 10, "resid_far": 2.0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("below_zoning_min_frontage" in r for r in reasons)


def test_fails_no_resid_far(config):
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("no_residential_far" in r for r in reasons)


def test_fails_irregular_geometry(config):
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": "Y", "compactness": 0.3, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("irregular_geometry" in r for r in reasons)


def test_irregular_needs_both_flags(config):
    """Irregular lot code alone is not enough — compactness must also be low."""
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": "Y", "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert not any("irregular_geometry" in r for r in reasons)


def test_fails_has_easements(config):
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 2,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("has_easements" in r for r in reasons)


def test_passes_all_buildability(config):
    """A lot that passes all tests should return empty list."""
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert reasons == []


def test_manufacturing_zone_fails_far(config):
    """M-zoned lots have no residential FAR."""
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "M1-2",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("no_residential_far" in r for r in reasons)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_filter.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.filter'`

- [ ] **Step 3: Write the implementation**

Create `src/filter.py`:

```python
"""Ownership matching and buildability filters."""

import json
import logging
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


def match_agency(owner_name: str | None, agency_list: list[str]) -> str | None:
    """Match an OwnerName string to an agency abbreviation.

    Returns the matched agency abbreviation or None.
    """
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
    """Compute compactness ratio: polygon area / bounding box area.

    Returns a float between 0 and 1. A perfect rectangle returns 1.0.
    """
    bbox = polygon.bounds  # (minx, miny, maxx, maxy)
    bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    if bbox_area == 0:
        return 0.0
    return polygon.area / bbox_area


def run_buildability_tests(lot: dict, config: dict) -> list[str]:
    """Run all buildability tests on a lot. Returns list of fail reasons."""
    reasons = []
    zoning = lot.get("zoning")
    zoning_mins = get_zoning_minimums(zoning, config["zoning_minimums"])

    # Test 1: Below zoning minimum lot area
    if zoning_mins is not None:
        min_area = zoning_mins["area"]
        lot_area = lot.get("lot_area") or 0
        if lot_area < min_area:
            reasons.append(
                f"below_zoning_min_area: {lot_area} < {min_area} ({zoning})"
            )

    # Test 2: Below zoning minimum frontage
    if zoning_mins is not None:
        min_front = zoning_mins["frontage"]
        lot_front = lot.get("lot_front") or 0
        if lot_front < min_front:
            reasons.append(
                f"below_zoning_min_frontage: {lot_front} < {min_front} ({zoning})"
            )

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


def process_lots(
    geojson_path: str,
    deed_restrictions_path: str,
    config: dict,
    db_conn,
) -> dict:
    """Process raw MapPLUTO GeoJSON and write candidates to database.

    Returns stats dict with counts.
    """
    from src.db import insert_lot, insert_deed_restriction

    with open(geojson_path) as f:
        geojson = json.load(f)

    # Load deed restrictions into a lookup by BBL
    deed_lookup: dict[str, list[dict]] = {}
    with open(deed_restrictions_path) as f:
        deed_records = json.load(f)
    for rec in deed_records:
        borough_code = _borough_name_to_code(rec.get("borough", ""))
        block = str(rec.get("block", "")).zfill(5)
        lot_num = str(rec.get("lot", "")).zfill(4)
        bbl = f"{borough_code}{block}{lot_num}"
        deed_lookup.setdefault(bbl, []).append(rec)

    all_agencies = config["agencies"]["primary"] + config["agencies"]["broad"]

    stats = {
        "total_fetched": 0,
        "public_owned": 0,
        "candidates": 0,
        "by_borough": {},
        "by_agency": {},
        "by_fail_reason": {},
    }

    for feature in geojson.get("features", []):
        stats["total_fetched"] += 1
        props = feature.get("properties", {})
        geom_json = feature.get("geometry")

        owner_name = props.get("ownername", "")
        agency = match_agency(owner_name, all_agencies)
        if agency is None:
            continue

        stats["public_owned"] += 1

        bbl = str(props.get("bbl", ""))
        borough = str(props.get("borough", ""))
        zoning = props.get("zonedist1", "")

        # Compute compactness from geometry
        compactness = 1.0
        wkt = None
        if geom_json:
            try:
                poly = shape(geom_json)
                compactness = compute_compactness(poly)
                wkt = poly.wkt
            except Exception:
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

        land_use = props.get("landuse", "")
        flags = {}
        if land_use == config["filters"]["vacant_land_use"]:
            flags["vacant"] = True
        if agency == "PARKS":
            flags["potential_greenthumb_conflict"] = True

        db_lot = {
            "bbl": bbl,
            "borough": borough,
            "block": str(props.get("block", "")),
            "lot": str(props.get("lot", "")),
            "address": props.get("address", ""),
            "owner_name": owner_name,
            "owner_agency": agency,
            "lot_area": lot_record["lot_area"],
            "lot_front": lot_record["lot_front"],
            "lot_depth": float(props.get("lotdepth", 0) or 0),
            "land_use": land_use,
            "zoning": zoning,
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

        # Insert deed restrictions if any
        for deed_rec in deed_lookup.get(bbl, []):
            insert_deed_restriction(db_conn, {
                "bbl": bbl,
                "restriction": deed_rec.get("description_of_restriction", ""),
                "detail": deed_rec.get("description_of_restriction_continued", ""),
            })

    return stats


_BOROUGH_CODES = {
    "MANHATTAN": "1", "MN": "1",
    "BRONX": "2", "BX": "2",
    "BROOKLYN": "3", "BK": "3",
    "QUEENS": "4", "QN": "4",
    "STATEN ISLAND": "5", "SI": "5",
}


def _borough_name_to_code(name: str) -> str:
    return _BOROUGH_CODES.get(name.upper().strip(), "0")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_filter.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/filter.py tests/test_filter.py
git commit -m "feat: ownership matching and buildability filter logic"
```

---

## Task 5: Map Generation Module

**Files:**
- Create: `src/mapgen.py`
- Create: `tests/test_mapgen.py`

Reads candidate lots from the database, generates an interactive Folium HTML map and a GeoJSON export file.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mapgen.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_mapgen.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.mapgen'`

- [ ] **Step 3: Write the implementation**

Create `src/mapgen.py`:

```python
"""Map generation and GeoJSON export."""

import json
import logging
import os
import sqlite3

import folium
from folium.plugins import MarkerCluster

from src.db import get_all_lots

log = logging.getLogger(__name__)

_NYC_CENTER = [40.7128, -74.0060]
_NYC_ZOOM = 11


def _get_geometry_wkt(conn: sqlite3.Connection, bbl: str) -> str | None:
    """Get WKT geometry for a lot, trying SpatiaLite first, then fallback table."""
    try:
        row = conn.execute(
            "SELECT AsText(geometry) as wkt FROM lots WHERE bbl = ? AND geometry IS NOT NULL",
            (bbl,),
        ).fetchone()
        if row and row["wkt"]:
            return row["wkt"]
    except sqlite3.OperationalError:
        pass

    try:
        row = conn.execute(
            "SELECT wkt FROM lots_geometry_fallback WHERE bbl = ?",
            (bbl,),
        ).fetchone()
        if row:
            return row["wkt"]
    except sqlite3.OperationalError:
        pass

    return None


def _wkt_to_coords(wkt: str) -> list | None:
    """Extract coordinate pairs from a WKT POLYGON string."""
    try:
        from shapely import wkt as shapely_wkt
        geom = shapely_wkt.loads(wkt)
        centroid = geom.centroid
        return [centroid.y, centroid.x]
    except Exception:
        return None


def generate_map(
    conn: sqlite3.Connection,
    output_path: str,
    primary_agencies: list[str],
) -> None:
    """Generate an interactive Folium HTML map of candidate lots."""
    lots = get_all_lots(conn)

    m = folium.Map(location=_NYC_CENTER, zoom_start=_NYC_ZOOM, tiles="CartoDB positron")

    primary_cluster = MarkerCluster(name="Primary Targets (HPD/DCAS/MTA)")
    broad_cluster = MarkerCluster(name="Broad Net (other agencies)")

    for lot in lots:
        wkt = _get_geometry_wkt(conn, lot["bbl"])
        if not wkt:
            continue

        coords = _wkt_to_coords(wkt)
        if not coords:
            continue

        fail_reasons = lot.get("fail_reasons", "[]")
        try:
            reasons_list = json.loads(fail_reasons)
        except (json.JSONDecodeError, TypeError):
            reasons_list = []

        reasons_html = "<br>".join(f"&bull; {r}" for r in reasons_list)

        popup_html = f"""
        <div style="min-width:200px">
            <b>BBL:</b> {lot['bbl']}<br>
            <b>Address:</b> {lot.get('address', 'N/A')}<br>
            <b>Agency:</b> {lot.get('owner_agency', 'N/A')}<br>
            <b>Lot Area:</b> {lot.get('lot_area', 0):,.0f} sq ft<br>
            <b>Zoning:</b> {lot.get('zoning', 'N/A')}<br>
            <b>Fail Reasons:</b><br>{reasons_html}
        </div>
        """

        is_primary = lot.get("owner_agency") in primary_agencies
        color = "green" if is_primary else "blue"

        marker = folium.Marker(
            location=coords,
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color=color, icon="leaf", prefix="fa"),
        )

        if is_primary:
            marker.add_to(primary_cluster)
        else:
            marker.add_to(broad_cluster)

    primary_cluster.add_to(m)
    broad_cluster.add_to(m)
    folium.LayerControl().add_to(m)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    m.save(output_path)
    log.info("Map saved to %s (%d lots)", output_path, len(lots))


def export_geojson(conn: sqlite3.Connection, output_path: str) -> int:
    """Export all candidate lots as a GeoJSON FeatureCollection."""
    lots = get_all_lots(conn)
    features = []

    for lot in lots:
        wkt = _get_geometry_wkt(conn, lot["bbl"])
        geometry = None
        if wkt:
            try:
                from shapely import wkt as shapely_wkt
                geom = shapely_wkt.loads(wkt)
                geometry = json.loads(json.dumps(geom.__geo_interface__))
            except Exception:
                pass

        properties = {
            k: v for k, v in lot.items()
            if k != "geometry"
        }

        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": geometry,
        })

    collection = {
        "type": "FeatureCollection",
        "features": features,
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(collection, f, indent=2)

    log.info("GeoJSON exported to %s (%d features)", output_path, len(features))
    return len(features)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_mapgen.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mapgen.py tests/test_mapgen.py
git commit -m "feat: Folium map generation and GeoJSON export"
```

---

## Task 6: CLI Entry Point

**Files:**
- Create: `scout.py`
- Create: `tests/test_cli.py`

The CLI ties all modules together with `fetch`, `filter`, `map`, `run`, and `stats` subcommands.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
import json
import os
import subprocess
import sys
import pytest


def run_scout(*args):
    result = subprocess.run(
        [sys.executable, "scout.py", *args],
        capture_output=True,
        text=True,
        cwd="/Users/francois/dev/forestgarden",
    )
    return result


def test_cli_help():
    result = run_scout("--help")
    assert result.returncode == 0
    assert "fetch" in result.stdout
    assert "filter" in result.stdout
    assert "map" in result.stdout
    assert "run" in result.stdout
    assert "stats" in result.stdout


def test_cli_stats_no_db():
    """Stats should fail gracefully when no database exists."""
    result = run_scout("stats", "--db", "/tmp/nonexistent_scout_test.db")
    assert result.returncode != 0 or "no database" in result.stderr.lower() or "no database" in result.stdout.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli.py -v
```

Expected: FAIL — `scout.py` does not exist.

- [ ] **Step 3: Write the implementation**

Create `scout.py`:

```python
#!/usr/bin/env python3
"""Scout & Vector — Phase 1: Find candidate lots for urban forest gardens in NYC."""

import argparse
import json
import logging
import os
import sys

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("scout")

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(ROOT, "config.yaml")
DEFAULT_DB = os.path.join(ROOT, "data", "scout.db")
DEFAULT_RAW_DIR = os.path.join(ROOT, "data", "raw")
DEFAULT_OUTPUT_DIR = os.path.join(ROOT, "output")


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def cmd_fetch(args):
    from src.fetch import fetch_mappluto, fetch_deed_restrictions

    config = load_config(args.config)
    os.makedirs(args.raw_dir, exist_ok=True)

    mappluto_path = os.path.join(args.raw_dir, "mappluto.geojson")
    log.info("Fetching MapPLUTO data...")
    count = fetch_mappluto(config, mappluto_path)
    log.info("MapPLUTO: %d features downloaded", count)

    deed_path = os.path.join(args.raw_dir, "deed_restrictions.json")
    log.info("Fetching deed restrictions...")
    count = fetch_deed_restrictions(config, deed_path)
    log.info("Deed restrictions: %d records downloaded", count)


def cmd_filter(args):
    from src.db import create_database
    from src.filter import process_lots

    config = load_config(args.config)

    mappluto_path = os.path.join(args.raw_dir, "mappluto.geojson")
    deed_path = os.path.join(args.raw_dir, "deed_restrictions.json")

    if not os.path.exists(mappluto_path):
        log.error("Raw data not found at %s. Run 'scout.py fetch' first.", mappluto_path)
        sys.exit(1)

    if not os.path.exists(deed_path):
        log.error("Deed restrictions not found at %s. Run 'scout.py fetch' first.", deed_path)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.db), exist_ok=True)

    # Remove old database for clean rebuild
    if os.path.exists(args.db):
        os.remove(args.db)

    conn = create_database(args.db)
    stats = process_lots(mappluto_path, deed_path, config, conn)
    conn.close()

    print(f"\nFilter complete:")
    print(f"  Total lots fetched:     {stats['total_fetched']:>10,}")
    print(f"  Public-owned lots:      {stats['public_owned']:>10,}")
    print(f"  Candidates (fail >= 1): {stats['candidates']:>10,}")


def cmd_map(args):
    import sqlite3
    from src.mapgen import generate_map, export_geojson

    config = load_config(args.config)

    if not os.path.exists(args.db):
        log.error("Database not found at %s. Run 'scout.py filter' first.", args.db)
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        conn.enable_load_extension(True)
        conn.load_extension("mod_spatialite")
    except (OSError, sqlite3.OperationalError):
        pass

    os.makedirs(args.output_dir, exist_ok=True)

    map_path = os.path.join(args.output_dir, "scout_map.html")
    geojson_path = os.path.join(args.output_dir, "candidates.geojson")

    primary = config["agencies"]["primary"]
    generate_map(conn, map_path, primary)
    count = export_geojson(conn, geojson_path)

    conn.close()

    print(f"\nMap output:")
    print(f"  HTML map:    {map_path}")
    print(f"  GeoJSON:     {geojson_path} ({count} features)")


def cmd_run(args):
    cmd_fetch(args)
    cmd_filter(args)
    cmd_map(args)


def cmd_stats(args):
    import sqlite3

    if not os.path.exists(args.db):
        print(f"No database found at {args.db}. Run 'scout.py filter' first.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) as c FROM lots").fetchone()["c"]

    print(f"\nScout & Vector — Database Stats")
    print(f"{'=' * 45}")
    print(f"  Total candidates: {total:,}")

    print(f"\nBy borough:")
    for row in conn.execute("SELECT borough, COUNT(*) as c FROM lots GROUP BY borough ORDER BY c DESC"):
        print(f"  {row['borough']:<20} {row['c']:>6,}")

    print(f"\nBy agency:")
    for row in conn.execute("SELECT owner_agency, COUNT(*) as c FROM lots GROUP BY owner_agency ORDER BY c DESC"):
        print(f"  {row['owner_agency']:<20} {row['c']:>6,}")

    print(f"\nBy fail reason:")
    all_reasons: dict[str, int] = {}
    for row in conn.execute("SELECT fail_reasons FROM lots"):
        try:
            reasons = json.loads(row["fail_reasons"])
        except (json.JSONDecodeError, TypeError):
            continue
        for reason in reasons:
            key = reason.split(":")[0]
            all_reasons[key] = all_reasons.get(key, 0) + 1

    for key, count in sorted(all_reasons.items(), key=lambda x: -x[1]):
        print(f"  {key:<35} {count:>6,}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Scout & Vector — Find candidate lots for urban forest gardens in NYC",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to config.yaml")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SpatiaLite database")
    parser.add_argument("--raw-dir", default=DEFAULT_RAW_DIR, help="Directory for raw downloads")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for output files")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="Download data from NYC Open Data")
    sub.add_parser("filter", help="Apply ownership and buildability filters")
    sub.add_parser("map", help="Generate interactive map and GeoJSON export")
    sub.add_parser("run", help="Run full pipeline: fetch → filter → map")
    sub.add_parser("stats", help="Print summary statistics from database")

    args = parser.parse_args()

    commands = {
        "fetch": cmd_fetch,
        "filter": cmd_filter,
        "map": cmd_map,
        "run": cmd_run,
        "stats": cmd_stats,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cli.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scout.py tests/test_cli.py
git commit -m "feat: CLI entry point with fetch/filter/map/run/stats subcommands"
```

---

## Task 7: CLAUDE.md

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Create `CLAUDE.md`**

Create `CLAUDE.md`:

```markdown
# Forest Garden — Scout & Vector

## Project Overview
Automated pipeline to identify vacant, city-owned parcels in NYC that are candidates for containerized urban forest gardens. Phase 1 focuses on data acquisition and filtering.

## Quick Start
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scout.py run        # full pipeline
python scout.py stats      # view results
open output/scout_map.html # interactive map
```

## Commands
```bash
python scout.py fetch      # download MapPLUTO + deed restrictions
python scout.py filter     # apply ownership + buildability filters
python scout.py map        # generate Folium map + GeoJSON
python scout.py run        # all three in sequence
python scout.py stats      # print summary statistics
```

## Architecture
Stage-based CLI pipeline: `fetch → filter → map`. Each stage independently re-runnable.

- `scout.py` — CLI entry point (argparse)
- `src/fetch.py` — SODA API data download (MapPLUTO + DCAS deed restrictions)
- `src/filter.py` — ownership matching + 5 buildability tests
- `src/mapgen.py` — Folium interactive map + GeoJSON export
- `src/db.py` — SpatiaLite schema and helpers
- `src/zoning.py` — zoning district minimum lot size lookup
- `config.yaml` — all thresholds, API endpoints, agency lists

## Data Sources
- **MapPLUTO** — `f888-ni5f` on NYC Open Data (GeoJSON via SODA API)
- **DCAS Deed Restrictions** — `rfu7-paqe` on NYC Open Data

## Key Concepts
- A lot is a "candidate" if it's publicly owned AND fails at least one buildability test
- Buildability tests: undersized area, narrow frontage, no residential FAR, irregular geometry, easements
- All thresholds in `config.yaml` — edit there, not in code
- `fail_reasons` field on each lot makes every inclusion auditable

## Testing
```bash
pytest tests/ -v
```

## Output
- `data/scout.db` — SpatiaLite database (gitignored)
- `output/scout_map.html` — interactive Folium map
- `output/candidates.geojson` — for QGIS / kepler.gl
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md with project context"
```

---

## Task 8: Integration Test

**Files:**
- Create: `tests/test_integration.py`

End-to-end test that runs the full pipeline with synthetic data to verify all stages connect correctly.

- [ ] **Step 1: Write the integration test**

Create `tests/test_integration.py`:

```python
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
    # Synthetic MapPLUTO with a mix of lots
    features = [
        # Candidate: HPD-owned, below min area
        _make_feature("1000010001", "NYC DEPT OF HOUSING PRESERVATION & DEVELOPMENT",
                      500, 25, 2.0, "R6"),
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

    # Synthetic deed restrictions
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

    # Load real config
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

    # Run filter
    stats = process_lots(
        setup["geojson_path"],
        setup["deed_path"],
        config,
        conn,
    )

    assert stats["total_fetched"] == 5
    assert stats["public_owned"] == 4  # 4 public-owned
    assert stats["candidates"] == 3    # 3 fail at least one test

    # Verify lots in database
    lots = get_all_lots(conn)
    assert len(lots) == 3

    bbls = {lot["bbl"] for lot in lots}
    assert "1000010001" in bbls  # HPD, below min area
    assert "1000010002" in bbls  # DCAS, no resid FAR
    assert "1000010003" in bbls  # DOT, has easements
    assert "1000010004" not in bbls  # passes all tests
    assert "1000010005" not in bbls  # private owner

    # Verify fail_reasons are populated
    hpd_lot = next(l for l in lots if l["bbl"] == "1000010001")
    reasons = json.loads(hpd_lot["fail_reasons"])
    assert any("below_zoning_min_area" in r for r in reasons)

    # Generate map
    map_path = str(setup["tmp_path"] / "map.html")
    generate_map(conn, map_path, config["agencies"]["primary"])
    assert os.path.exists(map_path)

    # Export GeoJSON
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
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS across all test files.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end integration test with synthetic data"
```

---

## Task 9: Smoke Test with Live API

**Files:** None (manual verification step)

Run the actual pipeline against the live NYC Open Data API to verify it works end-to-end with real data. This is a manual step, not an automated test.

- [ ] **Step 1: Run fetch with a small sample**

To avoid downloading the full ~860K lot dataset during development, test with a small batch first. Temporarily set `batch_size: 100` in `config.yaml`, then run:

```bash
cd /Users/francois/dev/forestgarden
source .venv/bin/activate
python scout.py fetch
```

Verify: `data/raw/mappluto.geojson` and `data/raw/deed_restrictions.json` exist and contain data.

- [ ] **Step 2: Run filter**

```bash
python scout.py filter
```

Check the output counts. With 100 lots, you may get 0–5 candidates. That's fine — this just verifies the pipeline connects.

- [ ] **Step 3: Run map**

```bash
python scout.py map
```

Open `output/scout_map.html` in a browser. Verify:
- Map is centered on NYC
- Any markers that appear have clickable popups with lot info
- Layer controls work

- [ ] **Step 4: Run stats**

```bash
python scout.py stats
```

Verify the output shows counts by borough, agency, and fail reason.

- [ ] **Step 5: Restore batch_size and run full pipeline**

Set `batch_size` back to `5000` in `config.yaml`. Run the full pipeline:

```bash
python scout.py run
```

This will take several minutes to download all ~860K lots. Verify final output.

- [ ] **Step 6: Commit config restoration**

```bash
git add config.yaml
git commit -m "chore: restore full batch_size after smoke test"
```
