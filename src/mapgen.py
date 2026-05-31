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


def _get_geometry_wkt(conn, bbl):
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


def _wkt_to_coords(wkt):
    try:
        from shapely import wkt as shapely_wkt
        geom = shapely_wkt.loads(wkt)
        centroid = geom.centroid
        return [centroid.y, centroid.x]
    except Exception:
        return None


def generate_map(conn, output_path, primary_agencies):
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


def export_geojson(conn, output_path):
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

        properties = {k: v for k, v in lot.items() if k != "geometry"}

        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": geometry,
        })

    collection = {"type": "FeatureCollection", "features": features}

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(collection, f, indent=2)

    log.info("GeoJSON exported to %s (%d features)", output_path, len(features))
    return len(features)
