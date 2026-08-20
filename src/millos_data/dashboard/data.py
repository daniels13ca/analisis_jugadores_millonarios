"""DuckDB-backed data access for the dashboard.

Kept free of any Streamlit import so it can be unit-tested on its own and
reused from a notebook or another UI later. The three `analytics/*.csv`
tables (see analytics.py) are loaded once and registered as DuckDB views;
callers query through the functions below rather than writing raw SQL
in the UI layer.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

TABLE_FILES = {
    "match_results": "match_results.csv",
    "player_match_features": "player_match_features.csv",
    "player_season_summary": "player_season_summary.csv",
}


def load_tables(analytics_dir: Path) -> dict[str, pd.DataFrame]:
    """Read the CSVs produced by `python -m millos_data build-analytics`."""
    tables: dict[str, pd.DataFrame] = {}
    for name, filename in TABLE_FILES.items():
        path = analytics_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"{path} no existe. Corre `python -m millos_data build-analytics` primero."
            )
        tables[name] = pd.read_csv(path, encoding="utf-8-sig")
    return tables


def get_connection(analytics_dir: Path) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with the analytics tables registered as views."""
    con = duckdb.connect(database=":memory:")
    for name, dataframe in load_tables(analytics_dir).items():
        con.register(name, dataframe)
    return con


# --- distinct-value helpers, for populating filter widgets -----------------


def list_campeonatos(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT campeonato FROM match_results WHERE campeonato IS NOT NULL ORDER BY 1"
    ).df()
    return rows["campeonato"].tolist()


def list_condiciones(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT condicion FROM match_results WHERE condicion IS NOT NULL ORDER BY 1"
    ).df()
    return rows["condicion"].tolist()


def list_anios(con: duckdb.DuckDBPyConnection) -> list[int]:
    rows = con.execute(
        "SELECT DISTINCT anio FROM player_season_summary WHERE anio IS NOT NULL ORDER BY 1"
    ).df()
    return [int(value) for value in rows["anio"]]


def list_posiciones(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT posicion FROM player_season_summary WHERE posicion IS NOT NULL ORDER BY 1"
    ).df()
    return rows["posicion"].tolist()


def list_jugadores(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT jugador FROM player_season_summary WHERE jugador IS NOT NULL ORDER BY 1"
    ).df()
    return rows["jugador"].tolist()


# --- query functions used by the dashboard views ----------------------------


def match_results_with_form(
    con: duckdb.DuckDBPyConnection,
    campeonatos: list[str] | None = None,
    condiciones: list[str] | None = None,
    rolling_window: int = 5,
) -> pd.DataFrame:
    """Match results ordered by date, with cumulative points and a rolling
    "forma reciente" (average points over the last `rolling_window` games),
    both computed as SQL window functions.
    """
    where_clauses = []
    params: list[str] = []
    if campeonatos:
        where_clauses.append(f"campeonato IN ({','.join(['?'] * len(campeonatos))})")
        params.extend(campeonatos)
    if condiciones:
        where_clauses.append(f"condicion IN ({','.join(['?'] * len(condiciones))})")
        params.extend(condiciones)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    query = f"""
        SELECT
            *,
            SUM(puntos) OVER (
                ORDER BY fecha ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS puntos_acumulados,
            AVG(puntos) OVER (
                ORDER BY fecha ROWS BETWEEN {rolling_window - 1} PRECEDING AND CURRENT ROW
            ) AS forma_reciente
        FROM match_results
        {where_sql}
        ORDER BY fecha
    """
    return con.execute(query, params).df()


_TEAM_SUMMARY_GROUP_COLUMNS = {"condicion", "campeonato"}


def team_summary(
    con: duckdb.DuckDBPyConnection,
    group_by: str = "condicion",
    campeonatos: list[str] | None = None,
) -> pd.DataFrame:
    """Win/draw/loss record and average points/goals, grouped by condicion or campeonato."""
    if group_by not in _TEAM_SUMMARY_GROUP_COLUMNS:
        raise ValueError(f"group_by debe ser uno de {_TEAM_SUMMARY_GROUP_COLUMNS}")

    where_sql = ""
    params: list[str] = []
    if campeonatos:
        where_sql = f"WHERE campeonato IN ({','.join(['?'] * len(campeonatos))})"
        params = campeonatos

    query = f"""
        SELECT
            {group_by},
            COUNT(*) AS partidos,
            SUM(CASE WHEN resultado_partido = 'W' THEN 1 ELSE 0 END) AS victorias,
            SUM(CASE WHEN resultado_partido = 'D' THEN 1 ELSE 0 END) AS empates,
            SUM(CASE WHEN resultado_partido = 'L' THEN 1 ELSE 0 END) AS derrotas,
            AVG(puntos) AS puntos_promedio,
            AVG(goles_favor) AS goles_favor_promedio,
            AVG(goles_contra) AS goles_contra_promedio
        FROM match_results
        {where_sql}
        GROUP BY {group_by}
        ORDER BY puntos_promedio DESC
    """
    return con.execute(query, params).df()


def player_season_summary_filtered(
    con: duckdb.DuckDBPyConnection,
    anios: list[int] | None = None,
    posiciones: list[str] | None = None,
    jugadores: list[str] | None = None,
) -> pd.DataFrame:
    dataframe = con.table("player_season_summary").df()
    if anios:
        dataframe = dataframe[dataframe["anio"].isin(anios)]
    if posiciones:
        dataframe = dataframe[dataframe["posicion"].isin(posiciones)]
    if jugadores:
        dataframe = dataframe[dataframe["jugador"].isin(jugadores)]
    return dataframe.reset_index(drop=True)


def player_match_history(con: duckdb.DuckDBPyConnection, jugador: str) -> pd.DataFrame:
    query = "SELECT * FROM player_match_features WHERE jugador = ? ORDER BY fecha"
    return con.execute(query, [jugador]).df()


# Ranking metrics it makes sense to average by posicion for benchmarking
# ("Comparar jugadores de la misma posicion" in docs/analytics_kpis.md).
POSITION_BENCHMARK_METRICS = [
    "goles_por90",
    "asistencias_por90",
    "calificacion_promedio",
    "duelos_ganados_pct",
    "pases_precision_promedio",
    "minutos_totales",
]


def position_averages(con: duckdb.DuckDBPyConnection, anios: list[int] | None = None) -> pd.DataFrame:
    """Average of each ranking metric, grouped by posicion.

    Used to benchmark a player against their position instead of the whole
    squad -- a forward and a center-back shouldn't be judged on the same
    goles_por90 scale.
    """
    dataframe = con.table("player_season_summary").df()
    if anios:
        dataframe = dataframe[dataframe["anio"].isin(anios)]
    metrics = [m for m in POSITION_BENCHMARK_METRICS if m in dataframe.columns]
    return dataframe.groupby("posicion", dropna=True)[metrics].mean().reset_index()


def dataset_last_updated(analytics_dir: Path) -> float | None:
    """mtime (seconds since epoch) of the analytics tables, or None if missing.

    Used by the dashboard sidebar to show how stale the data might be --
    `refresh` is what updates it, this just reports the timestamp.
    """
    path = analytics_dir / TABLE_FILES["match_results"]
    if not path.exists():
        return None
    return path.stat().st_mtime
