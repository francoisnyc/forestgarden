# Scout & Vector — Phase 1 Design Spec

**Project:** Containerized Urban Forest Garden (NYC)
**Phase:** 1 — Scout and Vector
**Date:** 2026-05-31

## Purpose

Build an automated pipeline that identifies vacant, city-owned parcels in NYC that are poor candidates for housing development but viable candidates for containerized forest gardens. The tool downloads municipal land use data, applies buildability filters, and produces a searchable database and interactive map of candidate lots.

## Architecture

### Pipeline Design

Stage-based CLI pipeline. Each stage is independently re-runnable.

```
scout.py fetch    →  downloads raw data to data/raw/
scout.py filter   →  applies buildability tests, writes to SpatiaLite DB
scout.py map      →  generates interactive HTML map + GeoJSON export
scout.py run      →  runs all three in sequence
scout.py stats    →  prints summary statistics from database
```

### Project Layout

```
forestgarden/
  scout.py                 # CLI entry point (argparse)
  config.yaml              # thresholds, API endpoints, agency list
  src/
    fetch.py               # SODA API downloads
    filter.py              # ownership + buildability tests
    mapgen.py              # Folium map + GeoJSON export
    db.py                  # SpatiaLite schema + helpers
    zoning.py              # zoning min lot size lookup table
  data/
    raw/                   # downloaded GeoJSON/CSV (gitignored)
    scout.db               # SpatiaLite database (gitignored)
  output/
    candidates.geojson     # filtered lots for GIS tools
    scout_map.html         # interactive Folium map
  CLAUDE.md                # project context for future sessions
  requirements.txt         # Python dependencies
```

### Language & Dependencies

- **Language:** Python 3.10+
- **Key packages:** requests, geopandas, shapely, spatialite, folium, pyyaml
- **Storage:** SpatiaLite (SQLite + spatial extension)
- **No framework overhead** — standard library argparse for CLI, no workflow engines

## Data Sources

### MapPLUTO (Primary)

- **Source:** NYC Department of City Planning
- **Access:** NYC Open Data SODA API
- **Endpoint:** `https://data.cityofnewyork.us/resource/f888-ni5f.geojson`
- **Format:** GeoJSON via API (paginated, batch_size 5000)
- **Update frequency:** Quarterly
- **Key fields used:** BBL, Borough, Block, Lot, Address, OwnerName, LotArea, LotFront, LotDepth, LandUse, ZoneDist1, ResidFAR, BuiltFAR, IrrLotCode, Easements, the_geom

### DCAS Deed Restriction Database

- **Source:** NYC DCAS (Local Law 176 of 2016)
- **Access:** NYC Open Data SODA API
- **Dataset ID:** `rfu7-paqe`
- **Endpoint:** `https://data.cityofnewyork.us/resource/rfu7-paqe.json`
- **Format:** JSON
- **Purpose:** Enrichment — join by BBL to add deed restriction details to candidate lots

## Agency Scope

### Ownership Filter Strategy

All publicly-owned lots are fetched and tagged by agency. No lots are discarded at fetch time — filtering happens at query time.

### Primary Targets

- **HPD** — Housing Preservation & Development. Manages vacant city-owned lots often slated for housing. "Unbuildable" rejects are prime candidates.
- **DCAS** — Citywide Administrative Services. Manages city real property. Holds surplus parcels.
- **MTA** — Metropolitan Transportation Authority. Remnant parcels near transit infrastructure.

### Broad Public Net (also included, tagged)

- **DOT** — Traffic triangles, road remnants, pedestrian plazas
- **DEP** — Utility strips, reservoir buffers
- **Parks** — Flagged for potential conflict with existing programs (e.g., GreenThumb)
- **NYCHA** — Flagged for separate governance
- **SCA / DOE** — School-related parcels, flagged for separate governance

### Deferred (Phase 2+)

- **Port Authority, NYCEDC, Trust for Governors Island** — Quasi-public entities with inconsistent MapPLUTO coverage and different approval paths
- **State-level agencies (DASNY, OGS)** — Governed by Albany, not City Hall

## Filter Logic

### Buildability Tests

A lot is a **forest garden candidate** if it is publicly owned AND fails **at least one** of the following buildability tests:

| # | Test | Field(s) | Threshold |
|---|------|----------|-----------|
| 1 | Below zoning minimum lot area | `LotArea`, `ZoneDist1` | `lot_area < zoning_minimums[zoning].area` (1,700–7,125 sq ft depending on zone) |
| 2 | Below zoning minimum frontage | `LotFront`, `ZoneDist1` | `lot_front < zoning_minimums[zoning].frontage` (18–75 ft depending on zone) |
| 3 | No residential FAR allowed | `ResidFAR` | `resid_far == 0` |
| 4 | Irregular geometry | `IrrLotCode`, computed compactness | `irr_lot_code` flagged AND `compactness < 0.4` (area / bounding box area) |
| 5 | Has easements | `Easements` | `easement_count > 0` |

### Additional Signals (not disqualifying, but tracked)

- `LandUse == '11'` (Vacant Land) — strong positive signal, stored as a flag
- Deed restrictions from DCAS dataset — joined and stored for reference

### Fail Reasons

Each candidate lot stores a `fail_reasons` field — a JSON array recording which tests it failed and the specific values. Example:

```json
["below_zoning_min_area: 1200 < 1700 (R6)", "irregular_geometry: compactness 0.31"]
```

This makes every inclusion auditable.

## Configuration

All thresholds, endpoints, and agency lists live in `config.yaml`:

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

## Data Model

### SpatiaLite Schema

**Table: `lots`** — one row per candidate lot

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `bbl` | TEXT (PK) | MapPLUTO | Borough+Block+Lot identifier |
| `borough` | TEXT | MapPLUTO | Borough name |
| `block` | TEXT | MapPLUTO | Tax block |
| `lot` | TEXT | MapPLUTO | Tax lot |
| `address` | TEXT | MapPLUTO | Street address |
| `owner_name` | TEXT | MapPLUTO | Raw owner name |
| `owner_agency` | TEXT | Parsed | Normalized agency abbreviation |
| `lot_area` | REAL | MapPLUTO | Lot area in sq ft |
| `lot_front` | REAL | MapPLUTO | Lot frontage in ft |
| `lot_depth` | REAL | MapPLUTO | Lot depth in ft |
| `land_use` | TEXT | MapPLUTO | 2-digit land use code |
| `zoning` | TEXT | MapPLUTO | Primary zoning district |
| `resid_far` | REAL | MapPLUTO | Max allowed residential FAR |
| `built_far` | REAL | MapPLUTO | Current built FAR |
| `irr_lot_code` | TEXT | MapPLUTO | Irregular lot flag |
| `compactness` | REAL | Computed | area / bounding box area |
| `easement_count` | INT | MapPLUTO | Number of easements |
| `fail_reasons` | TEXT | Computed | JSON array of failed buildability tests |
| `flags` | TEXT | Computed | JSON — conflicts, notes (e.g., "Parks: GreenThumb active") |
| `geometry` | GEOMETRY | MapPLUTO | Lot polygon (SRID 4326) |

**Table: `deed_restrictions`** — joined from DCAS dataset

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `id` | INTEGER (PK) | Auto | Row ID |
| `bbl` | TEXT (FK) | DCAS | Links to lots.bbl |
| `restriction` | TEXT | DCAS | Description of restriction |
| `detail` | TEXT | DCAS | Extended description |

## Map Output

### Interactive HTML Map (Folium)

- Centered on NYC with borough boundaries
- **Color coding:** Green markers for primary targets (HPD/DCAS/MTA), blue for broad-net agencies
- **Click popup:** BBL, address, owner agency, lot area, zoning, fail_reasons
- **Layer controls:** Toggle primary vs broad net, toggle by borough, toggle by fail reason type
- **Marker clustering** at low zoom levels for performance

### GeoJSON Export

`output/candidates.geojson` includes all lot fields for use in QGIS, kepler.gl, or other GIS tools.

### Stats Output

`scout.py stats` prints:
- Total lots fetched → public-owned → candidates (funnel)
- Breakdown by borough
- Breakdown by fail reason
- Breakdown by agency

## Validation Strategy

### Data Source Validation
- MapPLUTO is the authoritative NYC land use dataset, published by DCP
- Pipeline logs record counts at each stage (fetched → ownership match → candidates) for sanity checking

### Filter Verification
- Spot-check against known HPD vacant lots to verify they appear in output
- `fail_reasons` field makes every inclusion auditable
- `stats` command provides distribution breakdowns for anomaly detection

### Geometry Accuracy
- Uses MapPLUTO's official polygons (the_geom), not computed coordinates
- Compactness ratio calculated from these polygons via Shapely
- Interactive map enables visual verification

### Known Limitations
- MapPLUTO updates quarterly — lots may have been transferred since last release
- Easement details from DCAS dataset may not cover all easement types
- Owner name matching is string-based — agency abbreviations may vary in MapPLUTO

## Execution Model

- **One-shot CLI** — run the full pipeline or individual stages
- **No incremental updates** — each run downloads fresh data and rebuilds the database
- **Standard tools only** — relies on requests (HTTP), no browser automation or scraping

## Project Journal

Project journal and decision log maintained in Obsidian vault at:
`~/Library/CloudStorage/OneDrive-Personal/amofati26/forestgarden/`

Subfolders: `journal/`, `lots/`, `research/`

GitHub repo used for code version control and issue tracking only.

## Future Considerations (not in Phase 1 scope)

- Quasi-public agency data (Port Authority, NYCEDC)
- State-level agency parcels (DASNY, OGS)
- Incremental updates / change detection between MapPLUTO releases
- Automated scoring/ranking of candidates (sun exposure, soil, water proximity)
- Integration with permit application workflows
- Cross-reference with GreenThumb active sites
