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


def load_config(path):
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
    except (OSError, sqlite3.OperationalError, AttributeError):
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
    all_reasons = {}
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

    print(f"\nBy shadow risk:")
    for row in conn.execute(
        "SELECT shadow_risk, COUNT(*) as c FROM lots GROUP BY shadow_risk ORDER BY c DESC"
    ):
        label = row["shadow_risk"] or "unknown"
        print(f"  {label:<20} {row['c']:>6,}")

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
    sub.add_parser("run", help="Run full pipeline: fetch -> filter -> map")
    sub.add_parser("stats", help="Print summary statistics from database")

    args = parser.parse_args()
    commands = {
        "fetch": cmd_fetch, "filter": cmd_filter, "map": cmd_map,
        "run": cmd_run, "stats": cmd_stats,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
