import json
import os
import pytest
from unittest.mock import patch, MagicMock
from src.fetch import fetch_mappluto, fetch_deed_restrictions, _build_soda_url


def test_build_soda_url_first_page():
    url = _build_soda_url(
        base_url="https://data.cityofnewyork.us/resource/f888-ni5f.geojson",
        limit=5000,
        offset=0,
    )
    assert "$limit=5000" in url
    assert "$offset=0" in url


def test_build_soda_url_with_offset():
    url = _build_soda_url(
        base_url="https://data.cityofnewyork.us/resource/f888-ni5f.geojson",
        limit=5000,
        offset=10000,
    )
    assert "$offset=10000" in url


@patch("src.fetch.requests.get")
def test_fetch_mappluto_saves_file(mock_get, tmp_path):
    # SODA API returns flat JSON arrays, not GeoJSON
    record = {"bbl": "1000010001", "ownername": "HPD", "latitude": "40.7", "longitude": "-74.0"}

    response_1 = MagicMock()
    response_1.status_code = 200
    response_1.json.return_value = [record]

    response_2 = MagicMock()
    response_2.status_code = 200
    response_2.json.return_value = []

    mock_get.side_effect = [response_1, response_2]

    config = {
        "sources": {
            "mappluto": {
                "base_url": "https://data.cityofnewyork.us/resource/64uk-42ks.json",
                "batch_size": 5000,
            }
        }
    }

    output_path = str(tmp_path / "mappluto.json")
    count = fetch_mappluto(config, output_path)
    assert count == 1
    assert os.path.exists(output_path)

    with open(output_path) as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["bbl"] == "1000010001"


@patch("src.fetch.requests.get")
def test_fetch_deed_restrictions_saves_file(mock_get, tmp_path):
    records = [
        {"borough": "MANHATTAN", "block": "00001", "lot": "0001",
         "description_of_restriction": "Height limit", "description_of_restriction_continued": "Max 3 stories"}
    ]

    response_1 = MagicMock()
    response_1.status_code = 200
    response_1.json.return_value = records

    response_2 = MagicMock()
    response_2.status_code = 200
    response_2.json.return_value = []

    mock_get.side_effect = [response_1, response_2]

    config = {
        "sources": {
            "deed_restrictions": {
                "base_url": "https://data.cityofnewyork.us/resource/rfu7-paqe.json",
            }
        }
    }

    output_path = str(tmp_path / "deed_restrictions.json")
    count = fetch_deed_restrictions(config, output_path)
    assert count == 1
    assert os.path.exists(output_path)
