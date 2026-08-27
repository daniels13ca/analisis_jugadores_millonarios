from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .config import ApiConfig

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

logger = logging.getLogger(__name__)


def search_teams(config: ApiConfig, query: str) -> pd.DataFrame:
    response = fetch_json(
        config,
        "/teams",
        params={"search": query},
    )
    rows = []
    for item in response.get("response", []):
        team = item.get("team", {})
        rows.append(
            {
                "team_id": team.get("id"),
                "name": team.get("name"),
                "country": team.get("country"),
                "code": team.get("code"),
                "founded": team.get("founded"),
            }
        )
    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return dataframe

    dataframe["is_supported_target"] = (
        (dataframe["team_id"] == config.expected_team_id)
        & (dataframe["code"].fillna("").str.upper() == config.expected_team_code)
    )
    return dataframe.sort_values(
        by=["is_supported_target", "name"],
        ascending=[False, True],
    ).reset_index(drop=True)


def download_season_matches(config: ApiConfig, season: int, output_dir: Path) -> dict[str, Any]:
    fixtures = fetch_json(
        config,
        "/fixtures",
        params={"team": config.team_id, "season": season, "status": "FT"},
    ).get("response", [])

    fixtures = filter_supported_team_fixtures(config, fixtures)

    return _download_fixture_stats(
        config=config,
        fixtures=fixtures,
        output_dir=output_dir,
    )


def _download_fixture_stats(
    config: ApiConfig,
    fixtures: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_fixture_ids = _collect_existing_fixture_ids(output_dir)

    downloaded = 0
    skipped = 0
    already_downloaded_files: list[str] = []
    total = len(fixtures)

    for index, fixture in enumerate(fixtures, start=1):
        fixture_id = fixture["fixture"]["id"]
        file_path = build_fixture_filename(output_dir, config.team_id, fixture)

        # Skip if we already have this exact file OR if we already have this
        # fixture under a different filename (e.g. the API renamed the rival
        # team between downloads). Relying on the filename alone caused the
        # same match to be downloaded twice under different names.
        if file_path.exists() or fixture_id in existing_fixture_ids:
            skipped += 1
            already_downloaded_files.append(file_path.name)
            logger.info("(%d/%d) omitido, ya existe: %s", index, total, file_path.name)
            continue

        file_payload = build_fixture_payload(config, fixture)
        file_path.write_text(file_payload, encoding="utf-8")
        existing_fixture_ids.add(fixture_id)
        downloaded += 1
        logger.info("(%d/%d) descargado: %s", index, total, file_path.name)
        time.sleep(config.request_delay_seconds)

    return {
        "team_id": config.team_id,
        "team_code": config.expected_team_code,
        "team_name": config.expected_team_name,
        "fixtures_found": len(fixtures),
        "already_downloaded": skipped,
        "pending_before_download": downloaded,
        "downloaded": downloaded,
        "skipped_existing": skipped,
        "existing_files_sample": already_downloaded_files[:5],
    }


def _collect_existing_fixture_ids(output_dir: Path) -> set[int]:
    """Read fixture_id from every JSON already saved in output_dir.

    Used to detect a fixture that was already downloaded even if its
    filename would no longer match (e.g. the rival team was renamed by
    the API after the first download).
    """
    fixture_ids: set[int] = set()
    for json_path in output_dir.glob("*.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fixture_id = data.get("metadata", {}).get("fixture_id")
        if fixture_id not in (None, ""):
            try:
                fixture_ids.add(int(fixture_id))
            except (TypeError, ValueError):
                continue
    return fixture_ids


def _stat(source: dict[str, Any] | None, key: str, default: Any = 0) -> Any:
    if not isinstance(source, dict):
        return default
    value = source.get(key)
    return default if value is None else value


def build_fixture_payload(config: ApiConfig, fixture: dict[str, Any]) -> str:
    validate_fixture_team(config, fixture)
    fixture_id = fixture["fixture"]["id"]
    stats = fetch_json(
        config,
        "/fixtures/players",
        params={"fixture": fixture_id, "team": config.team_id},
    )

    is_home = fixture["teams"]["home"]["id"] == config.team_id
    rival_name = fixture["teams"]["away"]["name"] if is_home else fixture["teams"]["home"]["name"]

    players = []
    if stats.get("response"):
        for player in stats["response"][0].get("players", []):
            # The API can omit stat blocks for players with no minutes played
            # or return an incomplete payload for some fixtures. Using .get()
            # throughout avoids aborting the whole season download on a
            # single malformed player record.
            player_info = player.get("player") or {}
            statistics = (player.get("statistics") or [{}])[0] or {}

            games = statistics.get("games") or {}
            shots = statistics.get("shots") or {}
            goals = statistics.get("goals") or {}
            passes = statistics.get("passes") or {}
            tackles = statistics.get("tackles") or {}
            duels = statistics.get("duels") or {}
            fouls = statistics.get("fouls") or {}
            cards = statistics.get("cards") or {}

            accuracy = passes.get("accuracy")

            players.append(
                {
                    "nombre": player_info.get("name"),
                    # API-Football's stable numeric player id -- captured so a
                    # future name typo/rename in the API doesn't fragment a
                    # player's history the way a bare-name mismatch already
                    # has for some pre-existing downloads (see
                    # analytics.PLAYER_NAME_ALIASES for the manual fix).
                    "jugador_id": player_info.get("id"),
                    "posicion": games.get("position"),
                    "minutos": _stat(games, "minutes"),
                    "calificacion": games.get("rating"),
                    "titular": not games.get("substitute", False),
                    "rendimiento": {
                        "remates_totales": _stat(shots, "total"),
                        "remates_al_arco": _stat(shots, "on"),
                        "goles": _stat(goals, "total"),
                        "asistencias": _stat(goals, "assists"),
                        "pases": {
                            "totales": _stat(passes, "total"),
                            "precision": f"{accuracy}%" if accuracy else "0%",
                        },
                        "defensa": {
                            "entradas": _stat(tackles, "total"),
                            "intercepciones": _stat(tackles, "interceptions"),
                            "despejes": _stat(tackles, "blocks"),
                        },
                        "duelos": {
                            "totales": _stat(duels, "total"),
                            "ganados": _stat(duels, "won"),
                        },
                        "faltas": {
                            "cometidas": _stat(fouls, "committed"),
                            "recibidas": _stat(fouls, "drawn"),
                        },
                        "tarjetas": {
                            "amarilla": cards.get("yellow"),
                            "roja": cards.get("red"),
                        },
                    },
                }
            )

    payload = {
        "metadata": {
            "fixture_id": fixture_id,
            "equipo": fixture["teams"]["home"]["name"] if is_home else fixture["teams"]["away"]["name"],
            "rival": rival_name,
            "condicion": "Local" if is_home else "Visitante",
            "campeonato": fixture["league"]["name"],
            "fecha": fixture["fixture"]["date"].split("T")[0],
            "resultado": f"{fixture['goals']['home']} - {fixture['goals']['away']}",
        },
        "jugadores": players,
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_fixture_filename(output_dir: Path, team_id: int, fixture: dict[str, Any]) -> Path:
    date = fixture["fixture"]["date"].split("T")[0]
    is_home = fixture["teams"]["home"]["id"] == team_id
    condition = "Local" if is_home else "Visitante"
    rival_name = fixture["teams"]["away"]["name"] if is_home else fixture["teams"]["home"]["name"]
    rival_slug = rival_name.replace(" ", "_")
    fixture_id = fixture["fixture"]["id"]
    # fixture_id is embedded so the filename stays unique and traceable even
    # if the API later renames the rival team (see _collect_existing_fixture_ids
    # for the accompanying dedup-by-content check).
    return output_dir / f"{date}_{condition}_{rival_slug}_{fixture_id}.json"


def filter_supported_team_fixtures(
    config: ApiConfig,
    fixtures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for fixture in fixtures:
        home = fixture["teams"]["home"]
        away = fixture["teams"]["away"]
        if home["id"] == config.team_id or away["id"] == config.team_id:
            filtered.append(fixture)
    return filtered


def validate_fixture_team(config: ApiConfig, fixture: dict[str, Any]) -> None:
    home = fixture["teams"]["home"]
    away = fixture["teams"]["away"]
    if home["id"] != config.team_id and away["id"] != config.team_id:
        raise ValueError(
            f"Fixture {fixture['fixture']['id']} does not belong to supported team_id={config.team_id}."
        )


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    # Exponential backoff with jitter: ~1s, 2s, 4s, ...
    return (2**attempt) + random.uniform(0, 1)


def fetch_json(
    config: ApiConfig,
    endpoint: str,
    params: dict[str, Any],
    max_retries: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        response: requests.Response | None = None
        try:
            response = requests.get(
                f"{config.base_url}{endpoint}",
                headers=config.headers,
                params=params,
                timeout=30,
            )
        except requests.exceptions.RequestException as exc:
            last_error = exc
        else:
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response.json()
            last_error = requests.exceptions.HTTPError(
                f"{response.status_code} error from {endpoint}", response=response
            )

        if attempt < max_retries:
            delay = _retry_delay(response, attempt)
            logger.warning(
                "%s failed (%s), retrying in %.1fs (attempt %d/%d)",
                endpoint,
                last_error,
                delay,
                attempt + 1,
                max_retries,
            )
            time.sleep(delay)

    assert last_error is not None
    raise last_error
