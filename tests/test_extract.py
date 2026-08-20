from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from millos_data.config import ApiConfig
from millos_data.extract import (
    _collect_existing_fixture_ids,
    build_fixture_filename,
    build_fixture_payload,
    fetch_json,
)


def make_config() -> ApiConfig:
    return ApiConfig(api_key="test-key", request_delay_seconds=0)


def make_response(status_code: int, json_data: dict | None = None) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.headers = {}
    response.json.return_value = json_data or {}
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=response)
    else:
        response.raise_for_status.side_effect = None
    return response


def test_fetch_json_retries_on_429_then_succeeds() -> None:
    config = make_config()
    responses = [make_response(429), make_response(200, {"response": []})]

    with patch("millos_data.extract.requests.get", side_effect=responses) as mock_get, \
         patch("millos_data.extract.time.sleep") as mock_sleep:
        result = fetch_json(config, "/fixtures", params={})

    assert result == {"response": []}
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once()


def test_fetch_json_raises_after_exhausting_retries() -> None:
    config = make_config()
    responses = [make_response(503) for _ in range(4)]

    with patch("millos_data.extract.requests.get", side_effect=responses), \
         patch("millos_data.extract.time.sleep"):
        with pytest.raises(requests.exceptions.HTTPError):
            fetch_json(config, "/fixtures", params={}, max_retries=3)


def test_fetch_json_does_not_retry_on_client_error() -> None:
    config = make_config()
    responses = [make_response(404)]

    with patch("millos_data.extract.requests.get", side_effect=responses) as mock_get, \
         patch("millos_data.extract.time.sleep") as mock_sleep:
        with pytest.raises(requests.exceptions.HTTPError):
            fetch_json(config, "/fixtures", params={})

    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


def make_fixture(fixture_id: int = 1, home_id: int = 1125) -> dict:
    return {
        "fixture": {"id": fixture_id, "date": "2025-03-01T20:00:00+00:00"},
        "teams": {
            "home": {"id": home_id, "name": "Millonarios FC"},
            "away": {"id": 999, "name": "Rival FC"},
        },
        "league": {"name": "Primera A"},
        "goals": {"home": 2, "away": 1},
    }


def test_build_fixture_payload_handles_incomplete_player_stats() -> None:
    config = make_config()
    fixture = make_fixture()

    # Missing "shots"/"passes"/etc blocks entirely, and a player with no
    # "statistics" list at all: this used to raise KeyError and abort the
    # whole season download.
    incomplete_response = {
        "response": [
            {
                "players": [
                    {
                        "player": {"name": "Jugador Incompleto"},
                        "statistics": [{"games": {"position": "M", "minutes": None, "substitute": True}}],
                    },
                    {
                        "player": {"name": "Sin Estadisticas"},
                        "statistics": [],
                    },
                ]
            }
        ]
    }

    with patch("millos_data.extract.fetch_json", return_value=incomplete_response):
        payload = build_fixture_payload(config, fixture)

    assert "Jugador Incompleto" in payload
    assert "Sin Estadisticas" in payload


def test_build_fixture_filename_includes_fixture_id() -> None:
    fixture = make_fixture(fixture_id=42)
    path = build_fixture_filename(Path("out"), team_id=1125, fixture=fixture)
    assert path.name == "2025-03-01_Local_Rival_FC_42.json"


def test_collect_existing_fixture_ids_reads_metadata(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text('{"metadata": {"fixture_id": 10}}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"metadata": {"fixture_id": "20"}}', encoding="utf-8")
    (tmp_path / "c.json").write_text('{"metadata": {}}', encoding="utf-8")
    (tmp_path / "not_json.json").write_text("not valid json", encoding="utf-8")

    assert _collect_existing_fixture_ids(tmp_path) == {10, 20}
