"""Single source of truth for the shape of a player-match row.

Previously the list of output columns was duplicated by hand in three
places (the CSV column list, the JSON-to-row flattening logic, and — only
implicitly — the shape written by `extract.py`). Adding or renaming a stat
meant remembering to update all of them, with no error if you missed one.

`PERFORMANCE_FIELDS` is now the single place that maps a flat CSV column
name to its path inside a player's nested `rendimiento` dict. Both
`transform.flatten_match_file` (JSON -> row) and `consolidate.DEFAULT_OUTPUT_COLUMNS`
(the CSV column order) are derived from it.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# Columns that describe the match itself, shared by every player row.
MATCH_COLUMNS: list[str] = [
    "match_id",
    "source_file",
    "fecha",
    "campeonato",
    "rival",
    "condicion",
    "resultado",
]

# Columns that describe the player, independent of their performance stats.
PLAYER_COLUMNS: list[str] = [
    "jugador",
    "posicion",
    "minutos",
    "calificacion",
    "titular",
]

# (output_column, path_within_player["rendimiento"]).
PERFORMANCE_FIELDS: list[tuple[str, tuple[str, ...]]] = [
    ("goles", ("goles",)),
    ("asistencias", ("asistencias",)),
    ("remates_totales", ("remates_totales",)),
    ("remates_al_arco", ("remates_al_arco",)),
    ("pases_totales", ("pases", "totales")),
    ("pases_precision", ("pases", "precision")),
    ("entradas", ("defensa", "entradas")),
    ("intercepciones", ("defensa", "intercepciones")),
    ("despejes", ("defensa", "despejes")),
    ("duelos_totales", ("duelos", "totales")),
    ("duelos_ganados", ("duelos", "ganados")),
    ("faltas_cometidas", ("faltas", "cometidas")),
    ("faltas_recibidas", ("faltas", "recibidas")),
    ("amarillas", ("tarjetas", "amarilla")),
    ("rojas", ("tarjetas", "roja")),
]

OUTPUT_COLUMNS: list[str] = (
    MATCH_COLUMNS + PLAYER_COLUMNS + [column for column, _ in PERFORMANCE_FIELDS]
)


def normalize_nullable(value: Any) -> Any:
    if value in (None, ""):
        return pd.NA
    return value


def _read_path(source: dict[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = source
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def extract_performance(performance: dict[str, Any]) -> dict[str, Any]:
    """Flatten a player's nested `rendimiento` dict per PERFORMANCE_FIELDS."""
    return {
        column: normalize_nullable(_read_path(performance, path))
        for column, path in PERFORMANCE_FIELDS
    }
