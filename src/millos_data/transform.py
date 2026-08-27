from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .schema import extract_performance, normalize_nullable


def read_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_match_id(metadata: dict[str, Any], source_path: Path | None = None) -> str:
    fixture_id = metadata.get("fixture_id")
    if fixture_id not in (None, ""):
        return f"fixture:{fixture_id}"

    date = str(metadata.get("fecha", "")).strip()
    rival = str(metadata.get("rival", "")).strip()
    condition = str(metadata.get("condicion", "")).strip()

    if date and rival and condition:
        rival_slug = rival.lower().replace(" ", "_")
        condition_slug = condition.lower().replace(" ", "_")
        return f"match:{date}:{condition_slug}:{rival_slug}"

    if source_path is not None:
        return f"file:{source_path.stem.lower()}"

    return "match:unknown"


def flatten_match_file(path: Path) -> list[dict[str, Any]]:
    data = read_json_file(path)
    metadata = data.get("metadata", {})
    players = data.get("jugadores") or data.get("plantilla") or []
    match_id = build_match_id(metadata, path)

    rows: list[dict[str, Any]] = []
    for player in players:
        performance = player.get("rendimiento", {})

        row = {
            "match_id": match_id,
            "source_file": path.name,
            "fecha": metadata.get("fecha"),
            "campeonato": metadata.get("campeonato") or metadata.get("liga"),
            "rival": metadata.get("rival"),
            "condicion": metadata.get("condicion"),
            "resultado": metadata.get("resultado"),
            "jugador": player.get("nombre"),
            "jugador_id": normalize_nullable(player.get("jugador_id")),
            "posicion": player.get("posicion"),
            "minutos": normalize_nullable(player.get("minutos")),
            "calificacion": pd.to_numeric(player.get("calificacion"), errors="coerce"),
            "titular": player.get("titular"),
            **extract_performance(performance),
        }
        rows.append(row)

    return rows
