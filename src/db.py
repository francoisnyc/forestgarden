"""SpatiaLite database schema and helpers."""

import sqlite3


def create_database(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

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
            pass
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lots_geometry_fallback (
                bbl TEXT PRIMARY KEY REFERENCES lots(bbl),
                wkt TEXT
            )
        """)

    conn.commit()
    return conn


def _has_spatialite(conn):
    try:
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='geometry_columns'"
        ).fetchone()
        return result is not None
    except sqlite3.OperationalError:
        return False


def insert_lot(conn, lot):
    lot = dict(lot)
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


def insert_deed_restriction(conn, record):
    conn.execute("""
        INSERT INTO deed_restrictions (bbl, restriction, detail)
        VALUES (:bbl, :restriction, :detail)
    """, record)
    conn.commit()


def get_lot_by_bbl(conn, bbl):
    row = conn.execute("SELECT * FROM lots WHERE bbl = ?", (bbl,)).fetchone()
    if row is None:
        return None
    return dict(row)


def get_all_lots(conn):
    rows = conn.execute("SELECT * FROM lots").fetchall()
    return [dict(r) for r in rows]
