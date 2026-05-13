from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .config import ApiConfig


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
    return pd.DataFrame(rows)


def download_season_matches(config: ApiConfig, season: int, output_dir: Path) -> dict[str, int]:
    fixtures = fetch_json(
        config,
        "/fixtures",
        params={"team": config.team_id, "season": season, "status": "FT"},
    ).get("response", [])

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

    downloaded = 0
    skipped = 0

    for fixture in fixtures:
        file_path = build_fixture_filename(output_dir, config.team_id, fixture)
        if file_path.exists():
            skipped += 1
            continue

        file_payload = build_fixture_payload(config, fixture)
        file_path.write_text(file_payload, encoding="utf-8")
        downloaded += 1
        time.sleep(config.request_delay_seconds)

    return {
        "fixtures_found": len(fixtures),
        "downloaded": downloaded,
        "skipped_existing": skipped,
    }


def build_fixture_payload(config: ApiConfig, fixture: dict[str, Any]) -> str:
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
            statistics = player["statistics"][0]
            players.append(
                {
                    "nombre": player["player"]["name"],
                    "posicion": statistics["games"]["position"],
                    "minutos": statistics["games"]["minutes"] or 0,
                    "calificacion": statistics["games"]["rating"],
                    "titular": not statistics["games"]["substitute"],
                    "rendimiento": {
                        "remates_totales": statistics["shots"]["total"] or 0,
                        "remates_al_arco": statistics["shots"]["on"] or 0,
                        "goles": statistics["goals"]["total"] or 0,
                        "asistencias": statistics["goals"]["assists"] or 0,
                        "pases": {
                            "totales": statistics["passes"]["total"] or 0,
                            "precision": (
                                f"{statistics['passes']['accuracy']}%"
                                if statistics["passes"]["accuracy"]
                                else "0%"
                            ),
                        },
                        "defensa": {
                            "entradas": statistics["tackles"]["total"] or 0,
                            "intercepciones": statistics["tackles"]["interceptions"] or 0,
                            "despejes": statistics["tackles"]["blocks"] or 0,
                        },
                        "duelos": {
                            "totales": statistics["duels"]["total"] or 0,
                            "ganados": statistics["duels"]["won"] or 0,
                        },
                        "faltas": {
                            "cometidas": statistics["fouls"]["committed"] or 0,
                            "recibidas": statistics["fouls"]["drawn"] or 0,
                        },
                        "tarjetas": {
                            "amarilla": statistics["cards"]["yellow"],
                            "roja": statistics["cards"]["red"],
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

    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_fixture_filename(output_dir: Path, team_id: int, fixture: dict[str, Any]) -> Path:
    date = fixture["fixture"]["date"].split("T")[0]
    is_home = fixture["teams"]["home"]["id"] == team_id
    condition = "Local" if is_home else "Visitante"
    rival_name = fixture["teams"]["away"]["name"] if is_home else fixture["teams"]["home"]["name"]
    rival_slug = rival_name.replace(" ", "_")
    return output_dir / f"{date}_{condition}_{rival_slug}.json"


def fetch_json(config: ApiConfig, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        f"{config.base_url}{endpoint}",
        headers=config.headers,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
