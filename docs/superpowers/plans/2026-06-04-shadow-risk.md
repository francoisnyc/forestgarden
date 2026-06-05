# Shadow Risk Heuristic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shadow risk assessment (low/medium/high) to each candidate lot based on whether nearby buildings to the south or east cast winter shadows that reach the lot.

**Architecture:** New `src/solar.py` module builds a spatial grid index from all 858K MapPLUTO records, then for each candidate lot finds the tallest neighbor to the south/east and computes whether its winter solstice shadow reaches the lot. Results stored in SQLite, displayed as a toggleable map layer.

**Tech Stack:** Python stdlib only (`math`). No new dependencies.

---

### Task 0: Database schema — add shadow columns

**Files:**
- Modify: `src/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_db.py`:

```python
def test_insert_lot_with_shadow_fields(db):
    lot = _make_lot(shadow_risk="high", shadow_detail='{"south": {"numfloors": 6}}')
    insert_lot(db, lot)
    result = get_lot_by_bbl(db, "1000010001")
    assert result["shadow_risk"] == "high"
    assert '"numfloors": 6' in result["shadow_detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_db.py::test_insert_lot_with_shadow_fields -v`
Expected: FAIL — `shadow_risk` column does not exist.

- [ ] **Step 3: Add shadow columns to schema and insert statement**

In `src/db.py`, add two columns to the `CREATE TABLE lots` statement, after the `flags` column:

```sql
shadow_risk TEXT,
shadow_detail TEXT
```

In the `insert_lot` function, add `shadow_risk` and `shadow_detail` to the INSERT column list and VALUES list:

```python
conn.execute("""
    INSERT OR REPLACE INTO lots (
        bbl, borough, block, lot, address, owner_name, owner_agency,
        lot_area, lot_front, lot_depth, land_use, zoning,
        resid_far, built_far, irr_lot_code, compactness,
        easement_count, fail_reasons, flags,
        shadow_risk, shadow_detail
    ) VALUES (
        :bbl, :borough, :block, :lot, :address, :owner_name, :owner_agency,
        :lot_area, :lot_front, :lot_depth, :land_use, :zoning,
        :resid_far, :built_far, :irr_lot_code, :compactness,
        :easement_count, :fail_reasons, :flags,
        :shadow_risk, :shadow_detail
    )
""", lot_data)
```

- [ ] **Step 4: Update `_make_lot` helper in test file**

In `tests/test_db.py`, add defaults to the `_make_lot` function:

```python
"shadow_risk": None,
"shadow_detail": None,
```

These go after the `"wkt"` key in the `defaults` dict.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_db.py -v`
Expected: All tests pass including the new one.

- [ ] **Step 6: Commit**

```bash
git add src/db.py tests/test_db.py
git commit -m "feat: add shadow_risk and shadow_detail columns to lots table"
```

---

### Task 1: Solar module — spatial grid index

**Files:**
- Create: `src/solar.py`
- Create: `tests/test_solar.py`

- [ ] **Step 1: Write the failing test for `build_shadow_index`**

Create `tests/test_solar.py`:

```python
"""Tests for shadow risk assessment."""

from src.solar import build_shadow_index


def test_build_index_buckets_by_grid_cell():
    records = [
        {"xcoord": "150", "ycoord": "250", "numfloors": "3.0000000"},
        {"xcoord": "160", "ycoord": "260", "numfloors": "5.0000000"},
    ]
    index = build_shadow_index(records)
    # Both records fall in grid cell (1, 2) at GRID_CELL_FT=100
    assert (1, 2) in index
    assert len(index[(1, 2)]) == 2


def test_build_index_skips_missing_coords():
    records = [
        {"xcoord": "", "ycoord": "250", "numfloors": "3"},
        {"xcoord": "150", "ycoord": "", "numfloors": "3"},
        {"ownername": "SMITH"},  # no xcoord/ycoord at all
        {"xcoord": "150", "ycoord": "250", "numfloors": ""},
    ]
    index = build_shadow_index(records)
    assert len(index) == 0


def test_build_index_different_cells():
    records = [
        {"xcoord": "50", "ycoord": "50", "numfloors": "2"},
        {"xcoord": "500", "ycoord": "500", "numfloors": "10"},
    ]
    index = build_shadow_index(records)
    assert (0, 0) in index
    assert (5, 5) in index
    assert len(index[(0, 0)]) == 1
    assert len(index[(5, 5)]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_solar.py -v`
Expected: FAIL — `src.solar` module does not exist.

- [ ] **Step 3: Implement `build_shadow_index`**

Create `src/solar.py`:

```python
"""Shadow risk assessment using spatial neighbor analysis."""

import math
from typing import Optional

# Physics constants for NYC winter solstice (December 21)
FLOOR_HEIGHT_FT = 10
GRID_CELL_FT = 100
SEARCH_RADIUS_FT = 200
MANHATTAN_GRID_ANGLE_DEG = 29

# Solar elevation angles at NYC (40.7°N) on winter solstice
# These determine shadow length: shadow = height / tan(elevation)
_SOLAR_ELEVATIONS = {
    "8am": 12.0,
    "10am": 20.0,
    "noon": 25.5,
}

# Precompute shadow multipliers: shadow_reach = height * multiplier
_SHADOW_MULTIPLIERS = {
    slot: 1.0 / math.tan(math.radians(elev))
    for slot, elev in _SOLAR_ELEVATIONS.items()
}


def build_shadow_index(raw_data) -> dict:
    """Build a spatial grid index from raw MapPLUTO records.

    Args:
        raw_data: List of flat MapPLUTO JSON records.

    Returns:
        Dict mapping (grid_x, grid_y) to list of (xcoord, ycoord, numfloors).
        Skips records with missing or non-numeric coordinates/floors.
    """
    index = {}
    for record in raw_data:
        try:
            x = float(record.get("xcoord", ""))
            y = float(record.get("ycoord", ""))
            floors = float(record.get("numfloors", ""))
        except (ValueError, TypeError):
            continue
        if x == 0 or y == 0 or floors <= 0:
            continue
        cell = (int(x // GRID_CELL_FT), int(y // GRID_CELL_FT))
        index.setdefault(cell, []).append((x, y, floors))
    return index
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_solar.py -v`
Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/solar.py tests/test_solar.py
git commit -m "feat: spatial grid index for shadow neighbor lookup"
```

---

### Task 2: Solar module — shadow risk computation

**Files:**
- Modify: `src/solar.py`
- Modify: `tests/test_solar.py`

- [ ] **Step 1: Write failing tests for `compute_shadow_risk`**

Add to `tests/test_solar.py`:

```python
from src.solar import build_shadow_index, compute_shadow_risk, GRID_CELL_FT


def _index_with_building(candidate_x, candidate_y, bldg_x, bldg_y, bldg_floors):
    """Helper: build an index with the candidate lot (0 floors) and one building."""
    records = [
        {"xcoord": str(candidate_x), "ycoord": str(candidate_y), "numfloors": "0"},
        {"xcoord": str(bldg_x), "ycoord": str(bldg_y), "numfloors": str(bldg_floors)},
    ]
    return build_shadow_index(records)


def test_tall_building_close_south_is_high_risk():
    # 10-story building 50ft to the south
    # height=100ft, noon shadow reach = 100 * 2.1 = 210ft > 50ft → high
    idx = _index_with_building(1000, 1000, 1000, 950, 10)
    result = compute_shadow_risk(1000, 1000, "2", idx)
    assert result["shadow_risk"] == "high"


def test_short_building_far_south_is_low_risk():
    # 2-story building 150ft to the south
    # height=20ft, 8am shadow reach = 20 * 4.7 = 94ft < 150ft → low
    idx = _index_with_building(1000, 1000, 1000, 850, 2)
    result = compute_shadow_risk(1000, 1000, "2", idx)
    assert result["shadow_risk"] == "low"


def test_medium_building_moderate_distance():
    # 5-story building 80ft to the south
    # height=50ft, noon shadow = 50*2.1 = 105ft > 80 → no
    # height=50ft, 10am shadow = 50*2.7 = 137ft > 80 → yes
    # noon clears, 10am doesn't → medium
    # Wait: 105 > 80, so noon shadow DOES reach. That's high.
    # Use 6-story 130ft away instead:
    # height=60ft, noon shadow = 60*2.1 = 126ft < 130 → clears at noon
    # height=60ft, 10am shadow = 60*2.7 = 164ft > 130 → shadowed at 10am
    # → medium
    idx = _index_with_building(1000, 1000, 1000, 870, 6)
    result = compute_shadow_risk(1000, 1000, "2", idx)
    assert result["shadow_risk"] == "medium"


def test_no_neighbors_is_low_risk():
    index = {}
    result = compute_shadow_risk(1000, 1000, "2", index)
    assert result["shadow_risk"] == "low"


def test_building_to_north_is_low_risk():
    # Building to the north (higher y) should not cause shadow
    idx = _index_with_building(1000, 1000, 1000, 1050, 20)
    result = compute_shadow_risk(1000, 1000, "2", idx)
    assert result["shadow_risk"] == "low"


def test_missing_coords_returns_unknown():
    result = compute_shadow_risk(None, None, "2", {})
    assert result["shadow_risk"] == "unknown"


def test_manhattan_rotation():
    # In Manhattan (borocode "1"), south is rotated 29° clockwise.
    # A building at true SSW should register as "grid south" in Manhattan.
    # Place building 100ft away at 209° from candidate (true bearing).
    # 209° = 180° + 29°, which is "grid south" in Manhattan's rotated system.
    import math
    angle_rad = math.radians(209)
    bldg_x = 1000 + 100 * math.sin(angle_rad)  # ~952
    bldg_y = 1000 + 100 * math.cos(angle_rad)  # ~912
    idx = _index_with_building(1000, 1000, bldg_x, bldg_y, 15)
    result = compute_shadow_risk(1000, 1000, "1", idx)
    # 15 floors * 10ft = 150ft. Distance ~100ft.
    # noon shadow = 150 * 2.1 = 315ft >> 100ft → high
    assert result["shadow_risk"] == "high"


def test_shadow_detail_contains_south_info():
    idx = _index_with_building(1000, 1000, 1000, 950, 8)
    result = compute_shadow_risk(1000, 1000, "2", idx)
    detail = result["shadow_detail"]
    assert "south" in detail
    assert detail["south"]["numfloors"] == 8
    assert detail["south"]["height_ft"] == 80
    assert detail["south"]["distance_ft"] > 0
    assert "shadow_reach_8am" in detail["south"]
    assert "shadow_reach_noon" in detail["south"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_solar.py -v`
Expected: FAIL — `compute_shadow_risk` not found.

- [ ] **Step 3: Implement `compute_shadow_risk`**

Add to `src/solar.py`:

```python
def _rotate_point(dx, dy, angle_deg):
    """Rotate a (dx, dy) vector clockwise by angle_deg."""
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return dx * cos_a + dy * sin_a, -dx * sin_a + dy * cos_a


def _find_tallest_neighbor(x, y, grid_index, direction, rotation_deg):
    """Find the tallest building in the given direction within SEARCH_RADIUS_FT.

    Args:
        x, y: Candidate lot coordinates (State Plane feet).
        grid_index: Spatial grid index from build_shadow_index.
        direction: "south" or "east".
        rotation_deg: Grid rotation to apply (29° for Manhattan, 0 otherwise).

    Returns:
        (numfloors, distance_ft) of the tallest qualifying neighbor, or (0, 0).
    """
    cells_to_check = int(SEARCH_RADIUS_FT / GRID_CELL_FT) + 1
    center_cx = int(x // GRID_CELL_FT)
    center_cy = int(y // GRID_CELL_FT)

    best_floors = 0
    best_dist = 0

    for dcx in range(-cells_to_check, cells_to_check + 1):
        for dcy in range(-cells_to_check, cells_to_check + 1):
            cell = (center_cx + dcx, center_cy + dcy)
            for nx, ny, nfloors in grid_index.get(cell, []):
                if nfloors <= 0:
                    continue
                dx = nx - x
                dy = ny - y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < 1 or dist > SEARCH_RADIUS_FT:
                    continue

                # Rotate to grid-relative coordinates
                rdx, rdy = _rotate_point(dx, dy, rotation_deg)

                if direction == "south" and rdy >= 0:
                    continue  # Not to the south (south = negative rdy)
                if direction == "east" and rdx <= 0:
                    continue  # Not to the east (east = positive rdx)

                if nfloors > best_floors:
                    best_floors = nfloors
                    best_dist = dist

    return best_floors, best_dist


def _classify_risk(floors, distance_ft):
    """Classify shadow risk for a single direction.

    Returns "high", "medium", or "low".
    """
    if floors <= 0 or distance_ft <= 0:
        return "low"
    height = floors * FLOOR_HEIGHT_FT
    reach_noon = height * _SHADOW_MULTIPLIERS["noon"]
    reach_10am = height * _SHADOW_MULTIPLIERS["10am"]

    if reach_noon >= distance_ft:
        return "high"
    if reach_10am >= distance_ft:
        return "medium"
    return "low"


def _make_detail(floors, distance_ft):
    """Build the detail dict for one direction."""
    if floors <= 0:
        return None
    height = floors * FLOOR_HEIGHT_FT
    return {
        "numfloors": floors,
        "height_ft": height,
        "distance_ft": round(distance_ft, 1),
        "shadow_reach_8am": round(height * _SHADOW_MULTIPLIERS["8am"], 1),
        "shadow_reach_noon": round(height * _SHADOW_MULTIPLIERS["noon"], 1),
    }


def compute_shadow_risk(
    xcoord: Optional[float],
    ycoord: Optional[float],
    borocode: str,
    grid_index: dict,
) -> dict:
    """Compute shadow risk for a candidate lot.

    Args:
        xcoord, ycoord: Lot coordinates in NY State Plane (feet).
        borocode: Borough code ("1" for Manhattan, etc.).
        grid_index: Spatial grid from build_shadow_index.

    Returns:
        {"shadow_risk": "low"|"medium"|"high"|"unknown",
         "shadow_detail": {...}}
    """
    if xcoord is None or ycoord is None:
        return {"shadow_risk": "unknown", "shadow_detail": {}}
    try:
        x, y = float(xcoord), float(ycoord)
    except (ValueError, TypeError):
        return {"shadow_risk": "unknown", "shadow_detail": {}}

    rotation = MANHATTAN_GRID_ANGLE_DEG if borocode == "1" else 0

    s_floors, s_dist = _find_tallest_neighbor(x, y, grid_index, "south", rotation)
    e_floors, e_dist = _find_tallest_neighbor(x, y, grid_index, "east", rotation)

    south_risk = _classify_risk(s_floors, s_dist)
    east_risk = _classify_risk(e_floors, e_dist)

    # South risk is primary. East can elevate by at most one level.
    risk_levels = {"low": 0, "medium": 1, "high": 2}
    level_names = {0: "low", 1: "medium", 2: "high"}
    combined = risk_levels[south_risk]
    if risk_levels[east_risk] > 0:
        combined = min(combined + 1, 2)
    final_risk = level_names[combined]

    detail = {"risk": final_risk}
    south_detail = _make_detail(s_floors, s_dist)
    east_detail = _make_detail(e_floors, e_dist)
    if south_detail:
        detail["south"] = south_detail
    if east_detail:
        detail["east"] = east_detail

    return {"shadow_risk": final_risk, "shadow_detail": detail}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_solar.py -v`
Expected: All 10 tests pass (3 from Task 1 + 7 new).

- [ ] **Step 5: Commit**

```bash
git add src/solar.py tests/test_solar.py
git commit -m "feat: compute shadow risk from neighbor height and distance"
```

---

### Task 3: Filter integration — wire shadow risk into process_lots

**Files:**
- Modify: `src/filter.py`

- [ ] **Step 1: Import and build the shadow index after loading raw data**

In `src/filter.py`, add to the imports at the top:

```python
from src.solar import build_shadow_index, compute_shadow_risk
```

In `process_lots`, after `raw_data = json.load(f)` (line 116), add:

```python
    shadow_index = build_shadow_index(
        raw_data if isinstance(raw_data, list) else []
    )
```

The index is only built from flat JSON arrays (live API data). GeoJSON FeatureCollection data (from tests) doesn't have xcoord/ycoord fields, so we pass an empty list — candidates from tests will get `shadow_risk: "unknown"`.

- [ ] **Step 2: Compute shadow risk for each candidate and add to db_lot**

In `process_lots`, after the `db_lot` dict is built (before `insert_lot`), add:

```python
        shadow_result = compute_shadow_risk(
            props.get("xcoord"), props.get("ycoord"),
            str(props.get("borocode", "")), shadow_index,
        )
        db_lot["shadow_risk"] = shadow_result["shadow_risk"]
        db_lot["shadow_detail"] = json.dumps(shadow_result["shadow_detail"])
```

- [ ] **Step 3: Run all tests to verify nothing breaks**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests pass. Integration tests will produce `shadow_risk: "unknown"` since they use GeoJSON.

- [ ] **Step 4: Commit**

```bash
git add src/filter.py
git commit -m "feat: wire shadow risk computation into filter pipeline"
```

---

### Task 4: Stats — add shadow risk breakdown

**Files:**
- Modify: `scout.py`

- [ ] **Step 1: Add shadow risk query to `cmd_stats`**

In `scout.py`, in the `cmd_stats` function, after the fail reason block (after the `for key, count in sorted(all_reasons.items()...` loop), add:

```python
    print(f"\nBy shadow risk:")
    for row in conn.execute(
        "SELECT shadow_risk, COUNT(*) as c FROM lots GROUP BY shadow_risk ORDER BY c DESC"
    ):
        label = row["shadow_risk"] or "unknown"
        print(f"  {label:<20} {row['c']:>6,}")
```

- [ ] **Step 2: Run CLI to verify**

Run: `.venv/bin/python scout.py stats`
Expected: Shows "By shadow risk:" section (will show all "unknown" until we re-run the filter with real data).

- [ ] **Step 3: Commit**

```bash
git add scout.py
git commit -m "feat: add shadow risk breakdown to stats output"
```

---

### Task 5: Map — add shadow risk layer and update legend

**Files:**
- Modify: `src/mapgen.py`

- [ ] **Step 1: Add the shadow risk layer**

In `src/mapgen.py`, in `generate_map`, after the `broad_cluster.add_to(broad_group)` line, add:

```python
    shadow_group = folium.FeatureGroup(name="Shadow Risk", show=False)
    shadow_cluster = MarkerCluster()
    shadow_cluster.add_to(shadow_group)
```

Inside the `for lot in lots:` loop, after the existing marker is added to primary/broad cluster, add:

```python
        shadow_risk = lot.get("shadow_risk", "unknown")
        shadow_colors = {"low": "green", "medium": "orange", "high": "red"}
        shadow_color = shadow_colors.get(shadow_risk, "gray")
        shadow_marker = folium.Marker(
            location=coords,
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color=shadow_color, icon="sun-o", prefix="fa"),
        )
        shadow_marker.add_to(shadow_cluster)
```

After `broad_group.add_to(m)`, add:

```python
    shadow_group.add_to(m)
```

- [ ] **Step 2: Update the legend HTML**

In the legend HTML string, after the fail reasons `</div>`, add a new section:

```html
<div style="font-weight: bold; margin-top: 8px; margin-bottom: 4px;">Shadow Risk (toggle layer above)</div>
<div style="font-size: 12px;">
    <span style="display:inline-block;width:12px;height:12px;background:#38a143;border-radius:50%;vertical-align:middle;"></span>
        <b>Low</b> &mdash; Morning sun clears by 10AM<br>
    <span style="display:inline-block;width:12px;height:12px;background:#f0960f;border-radius:50%;vertical-align:middle;"></span>
        <b>Medium</b> &mdash; Shadowed at 10AM, clear by noon<br>
    <span style="display:inline-block;width:12px;height:12px;background:#d63e2a;border-radius:50%;vertical-align:middle;"></span>
        <b>High</b> &mdash; Shadowed through noon (winter solstice)
</div>
```

- [ ] **Step 3: Run existing map tests to verify nothing breaks**

Run: `.venv/bin/python -m pytest tests/test_mapgen.py -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/mapgen.py
git commit -m "feat: add toggleable shadow risk layer to map with legend"
```

---

### Task 6: Integration test — shadow fields in pipeline output

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add shadow field assertions to `test_full_pipeline`**

In `tests/test_integration.py`, inside `test_full_pipeline`, after the existing assertions on `hpd_lot`, add:

```python
    # Shadow risk should be present (unknown for GeoJSON test data without xcoord/ycoord)
    assert hpd_lot["shadow_risk"] is not None
```

- [ ] **Step 2: Add a new test with flat JSON data that has xcoord/ycoord**

Add a new test to `tests/test_integration.py`:

```python
def test_shadow_risk_with_flat_records(tmp_path):
    """Shadow risk is computed for flat JSON records with xcoord/ycoord."""
    records = [
        {
            "bbl": "2000010001", "borough": "BX", "borocode": "2",
            "block": "00001", "lot": "0001",
            "address": "1 TEST ST", "ownername": "NYC DEPT OF HOUSING PRESERVATION",
            "lotarea": "500", "lotfront": "15", "lotdepth": "33",
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
```

- [ ] **Step 3: Run integration tests**

Run: `.venv/bin/python -m pytest tests/test_integration.py -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration tests for shadow risk in pipeline output"
```

---

### Task 7: Smoke test — run on real data and verify distribution

- [ ] **Step 1: Re-run the filter on existing data**

Run: `.venv/bin/python scout.py filter`

Expected: Filter completes, shows candidate count.

- [ ] **Step 2: Check shadow risk distribution**

Run: `.venv/bin/python scout.py stats`

Expected: Shows "By shadow risk:" with a reasonable distribution across low/medium/high. If all lots show "unknown", check that `xcoord`/`ycoord` are being read from the raw data.

- [ ] **Step 3: Regenerate the map and open it**

Run: `.venv/bin/python scout.py map && open output/scout_map.html`

Expected: Map shows the new "Shadow Risk" layer in the layer control (off by default). Toggle it on — green/orange/red markers should appear. Legend should include shadow risk explanation.

- [ ] **Step 4: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 5: Commit any adjustments**

```bash
git add -A
git commit -m "chore: verify shadow risk smoke test on real data"
```
