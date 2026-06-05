"""Map generation and GeoJSON export."""

import html
import json
import logging
import os
import sqlite3
from typing import Optional

import folium
from folium.plugins import MarkerCluster

from src.db import get_all_lots

log = logging.getLogger(__name__)

_NYC_CENTER = [40.7128, -74.0060]
_NYC_ZOOM = 11


def _get_geometry_wkt(conn: sqlite3.Connection, bbl: str) -> Optional[str]:
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


def _wkt_to_coords(wkt: str) -> Optional[list]:
    """Extract centroid coordinates from a WKT POLYGON string."""
    try:
        from shapely import wkt as shapely_wkt
        geom = shapely_wkt.loads(wkt)
        centroid = geom.centroid
        return [centroid.y, centroid.x]
    except Exception:
        return None


def generate_map(conn: sqlite3.Connection, output_path: str, primary_agencies: list) -> None:
    """Generate an interactive Folium HTML map of candidate lots."""
    lots = get_all_lots(conn)
    m = folium.Map(location=_NYC_CENTER, zoom_start=_NYC_ZOOM, tiles="CartoDB positron")
    primary_group = folium.FeatureGroup(name="Primary Targets (HPD/DCAS/MTA)", show=True)
    broad_group = folium.FeatureGroup(name="Broad Net (other agencies)", show=True)
    primary_cluster = MarkerCluster()
    broad_cluster = MarkerCluster()
    primary_cluster.add_to(primary_group)
    broad_cluster.add_to(broad_group)
    shadow_group = folium.FeatureGroup(name="Shadow Risk", show=False)
    shadow_cluster = MarkerCluster()
    shadow_cluster.add_to(shadow_group)

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

        reasons_html = "<br>".join(f"&bull; {html.escape(str(r))}" for r in reasons_list)
        popup_html = f"""
        <div style="min-width:200px">
            <b>BBL:</b> {html.escape(str(lot['bbl']))}<br>
            <b>Address:</b> {html.escape(str(lot.get('address', 'N/A')))}<br>
            <b>Agency:</b> {html.escape(str(lot.get('owner_agency', 'N/A')))}<br>
            <b>Lot Area:</b> {lot.get('lot_area', 0):,.0f} sq ft<br>
            <b>Zoning:</b> {html.escape(str(lot.get('zoning', 'N/A')))}<br>
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

        shadow_risk = lot.get("shadow_risk", "unknown")
        shadow_colors = {"low": "green", "medium": "orange", "high": "red"}
        shadow_color = shadow_colors.get(shadow_risk, "gray")
        shadow_marker = folium.Marker(
            location=coords,
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color=shadow_color, icon="sun-o", prefix="fa"),
        )
        shadow_marker.add_to(shadow_cluster)

    primary_group.add_to(m)
    broad_group.add_to(m)
    shadow_group.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    legend_html = """
    <div style="
        position: fixed; bottom: 30px; right: 10px; z-index: 1000;
        background: white; padding: 14px 18px; border-radius: 6px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-size: 13px;
        line-height: 1.6; max-width: 340px;
    ">
        <div style="font-weight: bold; font-size: 14px; margin-bottom: 8px;">
            Forest Garden Scout
        </div>
        <div style="margin-bottom: 8px;">
            <span style="display:inline-block;width:12px;height:12px;background:#38a143;border-radius:50%;vertical-align:middle;"></span>
                <b>Green</b> &mdash; Primary targets (HPD, DCAS, MTA)<br>
            <span style="display:inline-block;width:12px;height:12px;background:#38a0d0;border-radius:50%;vertical-align:middle;"></span>
                <b>Blue</b> &mdash; Broad net (DOT, DEP, NYCHA, SCA, DOE, PARKS)
        </div>
        <div style="font-weight: bold; margin-bottom: 4px;">Fail Reasons (why it's a candidate)</div>
        <div style="font-size: 12px;">
            <b>below_zoning_min_area</b><br>
            Lot is smaller than the zoning district's minimum lot size<br>
            <b>below_zoning_min_frontage</b><br>
            Street frontage is narrower than the zoning minimum<br>
            <b>no_residential_far</b><br>
            Zoning doesn't allow any residential floor area<br>
            <b>irregular_geometry</b><br>
            Lot is flagged as irregularly shaped with low compactness<br>
            <b>has_easements</b><br>
            Lot has easement restrictions limiting use
        </div>
        <div style="font-weight: bold; margin-top: 8px; margin-bottom: 4px;">Shadow Risk (toggle layer above)</div>
        <div style="font-size: 12px;">
            <span style="display:inline-block;width:12px;height:12px;background:#38a143;border-radius:50%;vertical-align:middle;"></span>
                <b>Low</b> &mdash; Morning sun clears by 10AM<br>
            <span style="display:inline-block;width:12px;height:12px;background:#f0960f;border-radius:50%;vertical-align:middle;"></span>
                <b>Medium</b> &mdash; Shadowed at 10AM, clear by noon<br>
            <span style="display:inline-block;width:12px;height:12px;background:#d63e2a;border-radius:50%;vertical-align:middle;"></span>
                <b>High</b> &mdash; Shadowed through noon (winter solstice)
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
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

        properties = {k: v for k, v in lot.items() if k != "geometry"}
        features.append({"type": "Feature", "properties": properties, "geometry": geometry})

    collection = {"type": "FeatureCollection", "features": features}
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(collection, f, indent=2)

    log.info("GeoJSON exported to %s (%d features)", output_path, len(features))
    return len(features)
