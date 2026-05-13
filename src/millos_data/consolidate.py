from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .transform import build_match_id, flatten_match_file, read_json_file

DEFAULT_OUTPUT_COLUMNS = [
    "match_id",
    "source_file",
    "fecha",
    "campeonato",
    "rival",
    "condicion",
    "resultado",
    "jugador",
    "posicion",
    "minutos",
    "calificacion",
    "titular",
    "goles",
    "asistencias",
    "remates_totales",
    "remates_al_arco",
    "pases_totales",
    "pases_precision",
    "entradas",
    "intercepciones",
    "despejes",
    "duelos_totales",
    "duelos_ganados",
    "faltas_cometidas",
    "faltas_recibidas",
    "amarillas",
    "rojas",
]


@dataclass
class ConsolidationResult:
    dataframe: pd.DataFrame
    scanned_files: int
    skipped_existing_matches: int
    empty_matches: int
    new_rows: int


def discover_stats_directories(base_path: Path) -> list[Path]:
    return sorted(
        path
        for path in base_path.iterdir()
        if path.is_dir() and path.name.startswith("Millonarios_") and "Stats_Detalladas" in path.name
    )


def discover_json_files(base_path: Path) -> list[Path]:
    files: list[Path] = []
    for directory in discover_stats_directories(base_path):
        files.extend(sorted(directory.glob("*.json")))
    return files


def read_existing_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=DEFAULT_OUTPUT_COLUMNS)

    for encoding in ("utf-8", "utf-8-sig", "utf-16"):
        try:
            dataframe = pd.read_csv(path, encoding=encoding)
            break
        except UnicodeError:
            continue
    else:
        raise UnicodeError(f"Unable to read dataset using utf-8/utf-8-sig/utf-16: {path}")

    if "match_id" not in dataframe.columns:
        dataframe["match_id"] = dataframe.apply(
            lambda row: build_match_id(
                {
                    "fecha": row.get("fecha"),
                    "rival": row.get("rival"),
                    "condicion": row.get("condicion"),
                }
            ),
            axis=1,
        )

    if "source_file" not in dataframe.columns:
        dataframe["source_file"] = pd.NA

    return ensure_output_columns(dataframe)


def ensure_output_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    for column in DEFAULT_OUTPUT_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = pd.NA
    return dataframe.loc[:, DEFAULT_OUTPUT_COLUMNS]


def consolidate_dataset(
    base_path: Path,
    output_path: Path,
    write_output: bool = True,
) -> ConsolidationResult:
    existing_df = read_existing_dataset(output_path)
    processed_match_ids = set(existing_df["match_id"].dropna().astype(str))

    scanned_files = 0
    skipped_existing_matches = 0
    empty_matches = 0
    new_rows: list[dict] = []

    for json_file in discover_json_files(base_path):
        scanned_files += 1
        data = read_json_file(json_file)
        metadata = data.get("metadata", {})
        players = data.get("jugadores") or data.get("plantilla") or []
        match_id = build_match_id(metadata, json_file)

        if match_id in processed_match_ids:
            skipped_existing_matches += 1
            continue

        if not players:
            empty_matches += 1
            continue

        new_rows.extend(flatten_match_file(json_file))
        processed_match_ids.add(match_id)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        final_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        final_df = existing_df.copy()

    final_df = ensure_output_columns(final_df)
    final_df = final_df.sort_values(["fecha", "rival", "jugador"], na_position="last").reset_index(drop=True)

    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        final_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    return ConsolidationResult(
        dataframe=final_df,
        scanned_files=scanned_files,
        skipped_existing_matches=skipped_existing_matches,
        empty_matches=empty_matches,
        new_rows=len(new_rows),
    )
