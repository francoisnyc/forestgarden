import pytest
import yaml
from src.zoning import get_zoning_minimums


@pytest.fixture
def config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def test_exact_match_r6(config):
    result = get_zoning_minimums("R6", config["zoning_minimums"])
    assert result == {"area": 1700, "frontage": 18}


def test_exact_match_r1_1(config):
    result = get_zoning_minimums("R1-1", config["zoning_minimums"])
    assert result == {"area": 7125, "frontage": 75}


def test_subdistrict_match_r6a(config):
    result = get_zoning_minimums("R6A", config["zoning_minimums"])
    assert result == {"area": 1700, "frontage": 18}


def test_subdistrict_match_r5b(config):
    result = get_zoning_minimums("R5B", config["zoning_minimums"])
    assert result == {"area": 2375, "frontage": 25}


def test_manufacturing_zone_returns_none(config):
    result = get_zoning_minimums("M1-2", config["zoning_minimums"])
    assert result is None


def test_commercial_zone_returns_none(config):
    result = get_zoning_minimums("C4-4A", config["zoning_minimums"])
    assert result is None


def test_park_zone_returns_none(config):
    result = get_zoning_minimums("PARK", config["zoning_minimums"])
    assert result is None


def test_empty_string_returns_default(config):
    result = get_zoning_minimums("", config["zoning_minimums"])
    assert result == {"area": 1700, "frontage": 18}


def test_none_returns_default(config):
    result = get_zoning_minimums(None, config["zoning_minimums"])
    assert result == {"area": 1700, "frontage": 18}
