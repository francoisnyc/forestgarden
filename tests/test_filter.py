import json
import pytest
import yaml
from src.filter import match_agency, compute_compactness, run_buildability_tests
from shapely.geometry import Polygon, box


@pytest.fixture
def config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


# --- Agency matching ---

def test_match_agency_hpd():
    assert match_agency("NYC DEPT OF HOUSING PRESERVATION & DEVELOPMENT", ["HPD", "DCAS", "MTA"]) == "HPD"


def test_match_agency_dcas():
    assert match_agency("DEPT OF CITYWIDE ADMIN SERVICES", ["HPD", "DCAS", "MTA"]) == "DCAS"


def test_match_agency_mta():
    assert match_agency("METROPOLITAN TRANSPORTATION AUTHORITY", ["HPD", "DCAS", "MTA"]) == "MTA"


def test_match_agency_dot():
    assert match_agency("NYC DEPARTMENT OF TRANSPORTATION", ["DOT", "DEP"]) == "DOT"


def test_match_agency_no_match():
    assert match_agency("JOHN SMITH", ["HPD", "DCAS"]) is None


def test_match_agency_none_input():
    assert match_agency(None, ["HPD"]) is None


def test_match_agency_fire_dept_not_dep():
    """FIRE DEPARTMENT should not match DEP."""
    assert match_agency("FIRE DEPARTMENT OF NEW YORK", ["DEP", "DOT"]) is None


def test_match_agency_police_dept_not_dep():
    """NYC POLICE DEPARTMENT should not match DEP."""
    assert match_agency("NYC POLICE DEPARTMENT", ["DEP"]) is None


def test_match_agency_private_name_not_sca():
    """Private names containing 'SCA' should not match SCA."""
    assert match_agency("SCACCIA PROPERTY HOLDINGS VI, LLC", ["SCA"]) is None
    assert match_agency("OSCAR REYES", ["SCA"]) is None
    assert match_agency("FRANCESCA OLIVERI", ["SCA"]) is None


def test_match_agency_private_name_not_parks():
    """Private names containing 'PARKS' should not match PARKS."""
    assert match_agency("3920 PARKS CORP", ["PARKS"]) is None
    assert match_agency("LARRY PARKS", ["PARKS"]) is None


def test_match_agency_mta_lirr():
    """MTA - LIRR should match MTA."""
    assert match_agency("MTA - LIRR", ["MTA"]) == "MTA"
    assert match_agency("MTA-BRIDGES AND TUNNELS", ["MTA"]) == "MTA"


def test_match_agency_private_name_not_mta():
    """Private names containing 'MTA' substring should not match MTA."""
    assert match_agency("MUMTAZ, CHAUDHARY FARRUKH", ["MTA"]) is None


# --- Compactness ---

def test_compactness_square():
    """A square has compactness 1.0."""
    poly = box(0, 0, 10, 10)
    assert compute_compactness(poly) == pytest.approx(1.0)


def test_compactness_triangle():
    """A triangle inside a bounding box has compactness 0.5."""
    poly = Polygon([(0, 0), (10, 0), (5, 10), (0, 0)])
    assert compute_compactness(poly) == pytest.approx(0.5)


def test_compactness_narrow_sliver():
    """A very thin L-shaped lot has low compactness."""
    # A thin L-shape: occupies only a fraction of its bounding box
    poly = Polygon([(0, 0), (100, 0), (100, 1), (1, 1), (1, 10), (0, 10), (0, 0)])
    result = compute_compactness(poly)
    assert result < 0.4


# --- Buildability tests ---

def test_fails_area_below_zoning_min(config):
    lot = {
        "lot_area": 500, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("below_zoning_min_area" in r for r in reasons)


def test_fails_frontage_below_zoning_min(config):
    lot = {
        "lot_area": 5000, "lot_front": 10, "resid_far": 2.0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("below_zoning_min_frontage" in r for r in reasons)


def test_fails_no_resid_far(config):
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("no_residential_far" in r for r in reasons)


def test_fails_irregular_geometry(config):
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": "Y", "compactness": 0.3, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("irregular_geometry" in r for r in reasons)


def test_irregular_needs_both_flags(config):
    """Irregular lot code alone is not enough — compactness must also be low."""
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": "Y", "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert not any("irregular_geometry" in r for r in reasons)


def test_fails_has_easements(config):
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 2,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("has_easements" in r for r in reasons)


def test_passes_all_buildability(config):
    """A lot that passes all tests should return empty list."""
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 2.0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "R6",
    }
    reasons = run_buildability_tests(lot, config)
    assert reasons == []


def test_manufacturing_zone_fails_far(config):
    """M-zoned lots have no residential FAR."""
    lot = {
        "lot_area": 5000, "lot_front": 25, "resid_far": 0,
        "irr_lot_code": None, "compactness": 0.8, "easement_count": 0,
        "zoning": "M1-2",
    }
    reasons = run_buildability_tests(lot, config)
    assert any("no_residential_far" in r for r in reasons)
