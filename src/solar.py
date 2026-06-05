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
    height = int(floors * FLOOR_HEIGHT_FT)
    return {
        "numfloors": int(floors),
        "height_ft": height,
        "distance_ft": round(distance_ft, 1),
        "shadow_reach_8am": round(height * _SHADOW_MULTIPLIERS["8am"], 1),
        "shadow_reach_10am": round(height * _SHADOW_MULTIPLIERS["10am"], 1),
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

    # Human-readable note
    notes = {
        "high": "shadowed through noon (winter solstice)",
        "medium": "shadowed at 10AM, clear by noon",
        "low": "morning sun clears by 10AM",
    }

    detail = {"risk": final_risk, "note": notes[final_risk]}
    south_detail = _make_detail(s_floors, s_dist)
    east_detail = _make_detail(e_floors, e_dist)
    if south_detail:
        detail["south"] = south_detail
    if east_detail:
        detail["east"] = east_detail

    return {"shadow_risk": final_risk, "shadow_detail": detail}
