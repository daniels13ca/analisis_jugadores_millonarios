from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


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
        passes = performance.get("pases", {})
        defense = performance.get("defensa", {})
        duels = performance.get("duelos", {})
        fouls = performance.get("faltas", {})
        cards = performance.get("tarjetas", {})

        row = {
            "match_id": match_id,
            "source_file": path.name,
            "fecha": metadata.get("fecha"),
            "campeonato": metadata.get("campeonato") or metadata.get("liga"),
            "rival": metadata.get("rival"),
            "condicion": metadata.get("condicion"),
            "resultado": metadata.get("resultado"),
            "jugador": player.get("nombre"),
            "posicion": player.get("posicion"),
            "minutos": normalize_nullable(player.get("minutos")),
            "calificacion": pd.to_numeric(player.get("calificacion"), errors="coerce"),
            "titular": player.get("titular"),
            "goles": normalize_nullable(performance.get("goles")),
            "asistencias": normalize_nullable(performance.get("asistencias")),
            "remates_totales": normalize_nullable(performance.get("remates_totales")),
            "remates_al_arco": normalize_nullable(performance.get("remates_al_arco")),
            "pases_totales": normalize_nullable(passes.get("totales")),
            "pases_precision": normalize_nullable(passes.get("precision")),
            "entradas": normalize_nullable(defense.get("entradas")),
            "intercepciones": normalize_nullable(defense.get("intercepciones")),
            "despejes": normalize_nullable(defense.get("despejes")),
            "duelos_totales": normalize_nullable(duels.get("totales")),
            "duelos_ganados": normalize_nullable(duels.get("ganados")),
            "faltas_cometidas": normalize_nullable(fouls.get("cometidas")),
            "faltas_recibidas": normalize_nullable(fouls.get("recibidas")),
            "amarillas": normalize_nullable(cards.get("amarilla")),
            "rojas": normalize_nullable(cards.get("roja")),
        }
        rows.append(row)

    return rows


def normalize_nullable(value: Any) -> Any:
    if value in (None, ""):
        return pd.NA
    return value
