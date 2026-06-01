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
