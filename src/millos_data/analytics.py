"""Analytics layer: derived, dashboard-ready tables built on top of the
consolidated player-match dataset and the raw match JSON files.

This module is intentionally storage/BI-tool agnostic (plain pandas
DataFrames in, DataFrames out) so the choice of dashboard stack (Streamlit,
Power BI, DuckDB, ...) can be made independently later.

Three tables are produced:

- `build_match_results`: one row per match (fecha, rival, condicion,
  resultado), including matches that have no player-level stats. The
  regular `consolidate_dataset` pipeline silently drops those ("empty
  matches") because it only cares about player rows; team-performance
  analysis needs the final score even when the lineup wasn't captured.
- `build_player_match_features`: the player-match dataset with a few
  analysis-ready columns added (numeric pass accuracy, per-90 rates, a
  "jugo" flag for bench players with 0 minutes).
- `build_player_season_summary`: player-match features aggregated by
  player and calendar year.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from .consolidate import discover_json_files
from .transform import build_match_id, read_json_file

RESULT_PATTERN = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")

# Columns from the player-match dataset that make sense to normalize "per 90
# minutes played" for comparing players with very different playing time.
PER_90_SOURCE_COLUMNS = [
    "goles",
    "asistencias",
    "remates_totales",
    "remates_al_arco",
    "duelos_ganados",
    "faltas_cometidas",
]


def parse_pass_accuracy(value: Any) -> float:
    """Convert a pass-accuracy value like "80%" (or 80, or 0.8) to a 0-1 float.

    Returns pd.NA for missing/unparseable values instead of raising, since
    this runs over a whole DataFrame column via .apply().
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NA
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        if not stripped:
            return pd.NA
        try:
            number = float(stripped)
        except ValueError:
            return pd.NA
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return pd.NA

    # Accuracy is stored as a percentage ("80" meaning 80%); normalize to a
    # 0-1 fraction. A value already <= 1 is assumed to already be a fraction.
    return number / 100 if number > 1 else number


def derive_match_outcome(resultado: Any, condicion: Any) -> dict[str, Any]:
    """Turn "home - away" + Local/Visitante into Millonarios' perspective.

    Returns goles_favor/goles_contra/resultado_partido (W/D/L)/puntos. All
    values are pd.NA if `resultado` or `condicion` can't be parsed, so this
    degrades gracefully on malformed metadata instead of raising.
    """
    empty = {
        "goles_favor": pd.NA,
        "goles_contra": pd.NA,
        "resultado_partido": pd.NA,
        "puntos": pd.NA,
    }

    match = RESULT_PATTERN.match(str(resultado)) if resultado is not None else None
    if not match or condicion not in ("Local", "Visitante"):
        return empty

    home_goals, away_goals = int(match.group(1)), int(match.group(2))
    goles_favor, goles_contra = (
        (home_goals, away_goals) if condicion == "Local" else (away_goals, home_goals)
    )

    if goles_favor > goles_contra:
        outcome, points = "W", 3
    elif goles_favor == goles_contra:
        outcome, points = "D", 1
    else:
        outcome, points = "L", 0

    return {
        "goles_favor": goles_favor,
        "goles_contra": goles_contra,
        "resultado_partido": outcome,
        "puntos": points,
    }


def build_match_results(base_path: Path) -> pd.DataFrame:
    """One row per match, including matches with no player stats captured.

    Unlike consolidate_dataset (which only ever emits player rows and
    silently skips matches with an empty "jugadores" list), this reads
    match metadata directly so team-level results are never lost.
    """
    rows: list[dict[str, Any]] = []
    seen_match_ids: set[str] = set()

    for json_file in discover_json_files(base_path):
        data = read_json_file(json_file)
        metadata = data.get("metadata", {})
        players = data.get("jugadores") or data.get("plantilla") or []
        match_id = build_match_id(metadata, json_file)

        if match_id in seen_match_ids:
            continue
        seen_match_ids.add(match_id)

        row = {
            "match_id": match_id,
            "source_file": json_file.name,
            "fecha": metadata.get("fecha"),
            "campeonato": metadata.get("campeonato") or metadata.get("liga"),
            "rival": metadata.get("rival"),
            "condicion": metadata.get("condicion"),
            "resultado": metadata.get("resultado"),
            "tiene_datos_jugadores": bool(players),
            **derive_match_outcome(metadata.get("resultado"), metadata.get("condicion")),
        }
        rows.append(row)

    columns = [
        "match_id",
        "source_file",
        "fecha",
        "campeonato",
        "rival",
        "condicion",
        "resultado",
        "goles_favor",
        "goles_contra",
        "resultado_partido",
        "puntos",
        "tiene_datos_jugadores",
    ]
    dataframe = pd.DataFrame(rows, columns=columns)
    return dataframe.sort_values("fecha", na_position="last").reset_index(drop=True)


def per_90(dataframe: pd.DataFrame, columns: list[str], minutes_col: str = "minutos") -> pd.DataFrame:
    """Add `{column}_por90` for each column, NA where minutes played is 0/NA.

    Returns a copy; does not mutate the input DataFrame.
    """
    result = dataframe.copy()
    minutes = pd.to_numeric(result[minutes_col], errors="coerce")

    for column in columns:
        values = pd.to_numeric(result[column], errors="coerce")
        rate = values / minutes * 90
        result[f"{column}_por90"] = rate.where(minutes > 0, pd.NA)

    return result


def normalize_name_key(name: Any) -> str:
    """Accent/case/whitespace-insensitive key for matching name variants.

    Used to detect (validate.check_player_name_variants) and fix
    (canonicalize_player_names) the same player being written two different
    ways across matches, e.g. "Daniel Ruiz" / "Daniel Ruíz".
    """
    ascii_name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return " ".join(ascii_name.lower().split())


def canonicalize_player_names(dataframe: pd.DataFrame, column: str = "jugador") -> pd.DataFrame:
    """Collapse spelling variants of the same name to one canonical spelling.

    Without this, the same person can silently fragment into two different
    `jugador` values across matches, undercounting them in
    build_player_season_summary (see docs/analytics_kpis.md and
    validate.check_player_name_variants, which flags this instead of fixing
    it). The most frequent variant in the dataset is picked as canonical --
    simple and, empirically on this dataset, correct: the accented "proper"
    spelling loses to a plain-ASCII typo/shorthand more often than not.
    """
    result = dataframe.copy()
    names = result[column].dropna()
    if names.empty:
        return result

    # value_counts() is sorted descending, so the first name seen for a
    # given key is already the most frequent one.
    canonical_by_key: dict[str, str] = {}
    for name in names.value_counts().index:
        canonical_by_key.setdefault(normalize_name_key(name), name)

    result[column] = result[column].map(
        lambda name: canonical_by_key.get(normalize_name_key(name), name) if pd.notna(name) else name
    )
    return result


def build_player_match_features(player_match_df: pd.DataFrame) -> pd.DataFrame:
    """Add analysis-ready columns to the consolidated player-match dataset."""
    features = canonicalize_player_names(player_match_df)

    features["pases_precision_num"] = features["pases_precision"].apply(parse_pass_accuracy)
    features["minutos"] = pd.to_numeric(features["minutos"], errors="coerce")
    features["jugo"] = features["minutos"].fillna(0) > 0
    features["calificacion"] = pd.to_numeric(features["calificacion"], errors="coerce")

    features = per_90(features, PER_90_SOURCE_COLUMNS)

    # Calendar year as a first pass at "season" grouping. Colombian
    # football seasons (Apertura/Finalizacion) roughly track the calendar
    # year, but this is not exact for fixtures near year-end/new-year; treat
    # it as a coarse grouping key, not an official season label.
    features["anio"] = pd.to_datetime(features["fecha"], errors="coerce").dt.year

    return features


def build_player_season_summary(player_match_features: pd.DataFrame) -> pd.DataFrame:
    """Aggregate player-match features by jugador x anio.

    Rates (goles_por90, etc.) are recomputed from the season totals rather
    than averaged match-by-match, so a single high-rate substitute
    appearance doesn't skew the season number.
    """
    played = player_match_features[player_match_features["jugo"]].copy()

    grouped = played.groupby(["jugador", "anio"], dropna=False)

    summary = grouped.agg(
        posicion=("posicion", lambda s: s.mode().iat[0] if not s.mode().empty else pd.NA),
        partidos_jugados=("match_id", "nunique"),
        titularidades=("titular", "sum"),
        minutos_totales=("minutos", "sum"),
        goles=("goles", "sum"),
        asistencias=("asistencias", "sum"),
        remates_totales=("remates_totales", "sum"),
        remates_al_arco=("remates_al_arco", "sum"),
        duelos_totales=("duelos_totales", "sum"),
        duelos_ganados=("duelos_ganados", "sum"),
        amarillas=("amarillas", "sum"),
        rojas=("rojas", "sum"),
        calificacion_promedio=("calificacion", "mean"),
        pases_precision_promedio=("pases_precision_num", "mean"),
    ).reset_index()

    minutos = summary["minutos_totales"].replace(0, pd.NA)
    summary["goles_por90"] = summary["goles"] / minutos * 90
    summary["asistencias_por90"] = summary["asistencias"] / minutos * 90
    summary["duelos_ganados_pct"] = summary["duelos_ganados"] / summary["duelos_totales"].replace(0, pd.NA)

    return summary.sort_values(["anio", "jugador"]).reset_index(drop=True)
