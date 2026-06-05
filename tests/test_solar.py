"""Tests for shadow risk assessment."""

import math
from src.solar import build_shadow_index, compute_shadow_risk, GRID_CELL_FT


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


def _index_with_building(candidate_x, candidate_y, bldg_x, bldg_y, bldg_floors):
    """Helper: build an index with the candidate lot (0 floors) and one building."""
    records = [
        {"xcoord": str(candidate_x), "ycoord": str(candidate_y), "numfloors": "0"},
        {"xcoord": str(bldg_x), "ycoord": str(bldg_y), "numfloors": str(bldg_floors)},
    ]
    return build_shadow_index(records)


def test_tall_building_close_south_is_high_risk():
    # 10-story building 50ft to the south
    # height=100ft, noon shadow reach = 100 * 2.1 = 210ft > 50ft -> high
    idx = _index_with_building(1000, 1000, 1000, 950, 10)
    result = compute_shadow_risk(1000, 1000, "2", idx)
    assert result["shadow_risk"] == "high"


def test_short_building_far_south_is_low_risk():
    # 2-story building 150ft to the south
    # height=20ft, 8am shadow reach = 20 * 4.7 = 94ft < 150ft -> low
    idx = _index_with_building(1000, 1000, 1000, 850, 2)
    result = compute_shadow_risk(1000, 1000, "2", idx)
    assert result["shadow_risk"] == "low"


def test_medium_building_moderate_distance():
    # 6-story building 130ft to the south
    # height=60ft, noon shadow = 60*2.1 = 126ft < 130 -> clears at noon
    # height=60ft, 10am shadow = 60*2.7 = 164ft > 130 -> shadowed at 10am
    # -> medium
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
    # In Manhattan (borocode "1"), south is rotated 29 deg clockwise.
    # Place building 100ft away at 209 deg from candidate (true bearing).
    # 209 = 180 + 29, which is "grid south" in Manhattan's rotated system.
    angle_rad = math.radians(209)
    bldg_x = 1000 + 100 * math.sin(angle_rad)
    bldg_y = 1000 + 100 * math.cos(angle_rad)
    idx = _index_with_building(1000, 1000, bldg_x, bldg_y, 15)
    result = compute_shadow_risk(1000, 1000, "1", idx)
    # 15 floors * 10ft = 150ft. Distance ~100ft.
    # noon shadow = 150 * 2.1 = 315ft >> 100ft -> high
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
