# Shadow Risk Heuristic — Phase 1A Design

## Overview

Add a shadow risk assessment to the Scout & Vector pipeline that flags candidate lots based on whether nearby buildings to the south or east cast shadows that reach the lot during winter morning hours. This is a coarse heuristic using MapPLUTO data only — no additional datasets, no new dependencies.

Phase 1B (separate spec, future) will replace this with precise shadow computation using NYC Building Footprints and `pybdshadow`.

## Motivation

A containerized forest garden needs morning sun. A lot next to a 2-story house in Staten Island has very different sun exposure than one shadowed by a 15-story tower in Manhattan. The current pipeline identifies unbuildable city-owned lots but says nothing about whether they can actually grow food.

## Approach

### Solar geometry

Use winter solstice (December 21) as the worst-case test. If a lot gets sun in December, it gets sun year-round. Three time slots define the morning window:

| Time | Solar elevation (NYC, Dec 21) | Shadow multiplier (1/tan) |
|------|-------------------------------|---------------------------|
| 8:00 AM | ~12° | ~4.7× building height |
| 10:00 AM | ~20° | ~2.7× building height |
| 12:00 PM (noon) | ~25.5° | ~2.1× building height |

Shadow reach = `building_height / tan(elevation)`. A 50ft building casts a 235ft shadow at 8AM, 137ft at 10AM, 105ft at noon.

Building height is estimated as `numfloors × 10` feet.

### Spatial grid index

Scan all 858K MapPLUTO records during the filter step. Extract `xcoord`, `ycoord`, `numfloors` per lot. Build an in-memory spatial index bucketed by 100ft grid cells using NY State Plane coordinates (feet):

```
grid[(xcoord // 100, ycoord // 100)] → [(xcoord, ycoord, numfloors), ...]
```

Memory footprint: ~50MB for three numbers per lot.

### Neighbor lookup

For each candidate lot, query nearby grid cells within a 200ft radius to find buildings to the south and east:

- **South** = lower ycoord (State Plane Y increases northward)
- **East** = higher xcoord (State Plane X increases eastward)

For Manhattan lots (borocode "1"), apply a 29° clockwise rotation to align with the street grid before determining south/east. This accounts for Manhattan's tilted grid where "downtown" is SSW rather than true south.

The lookup finds the **tallest** building to the south and east within the search radius. This catches cross-street neighbors (which are the primary shadow source) because they're on adjacent blocks but within 200ft.

### Shadow risk classification

For the tallest south neighbor:

1. Compute shadow reach at each time slot (8AM, 10AM, noon)
2. Compare to the actual distance between the candidate and the neighbor

Classification:

| Risk | Condition |
|------|-----------|
| **high** | Shadow reaches lot at noon (worst case clears never) |
| **medium** | Shadow reaches lot at 10AM but not noon |
| **low** | Shadow clears by 10AM, or no tall neighbor to the south |

The east neighbor is checked the same way but can only elevate risk by one level — e.g., if south says "low" but a tall building is immediately to the east, the final risk becomes "medium" (not "high"). East shadows only block early morning sun and clear as the sun moves south.

### Output fields

Two new columns on the `lots` table:

- `shadow_risk` TEXT — "low", "medium", or "high"
- `shadow_detail` TEXT — JSON object:
  ```json
  {
    "south": {"numfloors": 6, "height_ft": 60, "distance_ft": 85, "shadow_reach_8am": 282, "shadow_reach_noon": 126},
    "east": {"numfloors": 3, "height_ft": 30, "distance_ft": 120, "shadow_reach_8am": 141, "shadow_reach_noon": 63},
    "risk": "medium",
    "note": "shadowed at 8AM, clear by noon"
  }
  ```

## Module: `src/solar.py`

Functions:

- `build_shadow_index(raw_data) -> dict` — Scans raw MapPLUTO JSON, returns the spatial grid index. Skips records with missing or non-numeric `xcoord`/`ycoord`/`numfloors`.
- `compute_shadow_risk(xcoord, ycoord, borocode, grid_index) -> dict` — Returns `{"shadow_risk": "...", "shadow_detail": {...}}` for a single lot. Returns `{"shadow_risk": "unknown", "shadow_detail": {}}` if xcoord/ycoord are missing.

Constants (hardcoded, not configurable — these are physics):

- `FLOOR_HEIGHT_FT = 10`
- `SEARCH_RADIUS_FT = 200`
- `GRID_CELL_FT = 100`
- `MANHATTAN_GRID_ANGLE_DEG = 29`
- Solar elevations for NYC winter solstice: 8AM=12°, 10AM=20°, noon=25.5°

## Pipeline integration

### Filter step (`src/filter.py`)

1. After loading the raw MapPLUTO JSON, call `build_shadow_index(raw_data)` once.
2. During the candidate loop, extract `xcoord` and `ycoord` from the current record's properties.
3. Call `compute_shadow_risk()` and add `shadow_risk` and `shadow_detail` to the lot record before inserting into SQLite.

### Database (`src/db.py`)

Add two nullable columns to the `lots` table:

```sql
shadow_risk TEXT,
shadow_detail TEXT
```

### Map (`src/mapgen.py`)

Add a third toggleable FeatureGroup layer: "Shadow Risk". Off by default.

Markers colored by risk:
- Green = low risk (good morning sun)
- Orange = medium risk
- Red = high risk

Update the legend to explain the shadow risk colors and what they mean.

### Stats (`scout.py`)

Add shadow risk distribution to the stats output:

```
By shadow risk:
  low                    2,100
  medium                   800
  high                   2,100
```

### Fetch (`src/fetch.py`)

No changes. `xcoord`, `ycoord`, `numfloors` are already in the raw MapPLUTO data we download.

### Config (`config.yaml`)

No changes. Solar constants are physics, not policy.

## Known limitations

- **Floor height assumed at 10ft.** Real NYC floors vary 9-15ft (ground floor retail is often taller). Produces ~10-20% error in shadow reach.
- **Point-to-point distance.** We measure centroid-to-centroid, not edge-to-edge. This overestimates distance for large lots and underestimates shadow risk slightly.
- **Single tallest neighbor only.** Doesn't account for cumulative shadowing from multiple buildings of moderate height.
- **No lot orientation.** We use cardinal directions (with Manhattan grid correction) not actual lot frontage. A lot facing east on a north-south street has different exposure than one facing south on an east-west street.
- **No building position within the lot.** A building could be at the far end of a neighboring lot, not at the lot line. We assume worst case (building at the lot line).
- **2D analysis only.** No terrain elevation, no reflected light, no gaps between buildings.

## Phase 1B (future, separate spec)

Phase 1B replaces this heuristic with measured shadow computation:

- Fetch NYC Building Footprints dataset (`qb5r-6dgf`) — actual building polygon geometry
- Combine with `numfloors` from MapPLUTO for 3D building envelopes
- Use `pybdshadow` to compute shadow polygons at 30-minute intervals across the morning window (8AM-1PM)
- Calculate actual `morning_sun_hours` on three seasonal dates: spring equinox (Mar 20), summer solstice (Jun 21), autumn equinox (Sep 22)
- Replace `shadow_risk` with measured `viable_morning_sun` boolean and `average_morning_sun_hours` float
- Filter out lots below 3 hours of morning sun

## Testing

- Unit tests for `build_shadow_index` (correct bucketing, handles missing xcoord/ycoord/numfloors)
- Unit tests for `compute_shadow_risk`:
  - Tall building 50ft to the south → high risk
  - Short building 150ft to the south → low risk
  - No neighbor to the south → low risk
  - Manhattan lot with 29° rotation → correct south direction
  - Building to the north only → low risk (north buildings don't shadow)
- Integration test with synthetic MapPLUTO data: verify shadow fields appear in SQLite output
- Smoke test on real data: verify risk distribution is reasonable (not all high, not all low)
