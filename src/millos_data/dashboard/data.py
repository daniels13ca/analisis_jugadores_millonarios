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


def _year_condition(fecha_column: str, anios: list[int] | None) -> tuple[str | None, list[int]]:
    """SQL condition + params for filtering `fecha_column` by year, or (None, [])
    if `anios` is falsy. Shared by every match_results/player_match_features
    query so the global year-range filter (see app.py) behaves identically
    everywhere.
    """
    if not anios:
        return None, []
    placeholders = ",".join(["?"] * len(anios))
    return f"EXTRACT(YEAR FROM CAST({fecha_column} AS DATE)) IN ({placeholders})", list(anios)


# --- distinct-value helpers, for populating filter widgets -----------------


def list_match_years(con: duckdb.DuckDBPyConnection) -> list[int]:
    """Every year with at least one match, from match_results (which -- unlike
    player_season_summary -- also covers matches with no player stats). Used
    to size the global year-range filter.
    """
    rows = con.execute(
        "SELECT DISTINCT EXTRACT(YEAR FROM CAST(fecha AS DATE))::INTEGER AS anio "
        "FROM match_results WHERE fecha IS NOT NULL ORDER BY 1"
    ).df()
    return [int(value) for value in rows["anio"]]


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
    anios: list[int] | None = None,
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
    year_sql, year_params = _year_condition("fecha", anios)
    if year_sql:
        where_clauses.append(year_sql)
        params.extend(year_params)
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


def points_race_by_year(
    con: duckdb.DuckDBPyConnection,
    campeonatos: list[str] | None = None,
    anios: list[int] | None = None,
) -> pd.DataFrame:
    """Cumulative points per year, indexed by jornada (matchday-within-year)
    instead of calendar date.

    A single "all-time" cumulative line (mixing years and competitions) only
    ever goes up and doesn't say much on its own. Resetting the cumulative
    sum at the start of each year and aligning by jornada instead of date
    turns it into something you can actually compare: "at this point in the
    season, are we ahead of or behind last year's pace?".
    """
    where_clauses = []
    params: list = []
    if campeonatos:
        where_clauses.append(f"campeonato IN ({','.join(['?'] * len(campeonatos))})")
        params.extend(campeonatos)
    year_sql, year_params = _year_condition("fecha", anios)
    if year_sql:
        where_clauses.append(year_sql)
        params.extend(year_params)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    query = f"""
        WITH partidos AS (
            SELECT
                fecha,
                puntos,
                EXTRACT(YEAR FROM CAST(fecha AS DATE))::INTEGER AS anio
            FROM match_results
            {where_sql}
        )
        SELECT
            anio,
            fecha,
            ROW_NUMBER() OVER (PARTITION BY anio ORDER BY fecha) AS jornada,
            SUM(puntos) OVER (
                PARTITION BY anio ORDER BY fecha
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS puntos_acumulados
        FROM partidos
        ORDER BY anio, fecha
    """
    return con.execute(query, params).df()


def jornada_calendar_labels(
    con: duckdb.DuckDBPyConnection,
    campeonatos: list[str] | None = None,
    anios: list[int] | None = None,
) -> pd.DataFrame:
    """For each jornada (matchday-within-year, see points_race_by_year), the
    most common calendar month across all years present.

    Used to label the year-over-year points-race chart's x-axis with "which
    month is this, roughly" context alongside the jornada number, and to
    place a first/second-half-of-the-year divider. The exact month for a
    given jornada can drift a bit year to year (schedule isn't identical),
    so this reports the *typical* one rather than claiming per-year
    precision.
    """
    where_clauses = []
    params: list = []
    if campeonatos:
        where_clauses.append(f"campeonato IN ({','.join(['?'] * len(campeonatos))})")
        params.extend(campeonatos)
    year_sql, year_params = _year_condition("fecha", anios)
    if year_sql:
        where_clauses.append(year_sql)
        params.extend(year_params)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    query = f"""
        WITH partidos AS (
            SELECT
                fecha,
                EXTRACT(YEAR FROM CAST(fecha AS DATE))::INTEGER AS anio,
                EXTRACT(MONTH FROM CAST(fecha AS DATE))::INTEGER AS mes
            FROM match_results
            {where_sql}
        ),
        con_jornada AS (
            SELECT mes, ROW_NUMBER() OVER (PARTITION BY anio ORDER BY fecha) AS jornada
            FROM partidos
        ),
        conteo AS (
            SELECT jornada, mes, COUNT(*) AS n
            FROM con_jornada
            GROUP BY jornada, mes
        )
        SELECT jornada, mes
        FROM conteo
        QUALIFY ROW_NUMBER() OVER (PARTITION BY jornada ORDER BY n DESC, mes) = 1
        ORDER BY jornada
    """
    return con.execute(query, params).df()


def matches_filtered(
    con: duckdb.DuckDBPyConnection,
    campeonatos: list[str] | None = None,
    condiciones: list[str] | None = None,
    resultados: list[str] | None = None,
    anios: list[int] | None = None,
) -> pd.DataFrame:
    """Match log (fecha, rival, condicion, resultado, ...), most recent first.

    This is the "match detail" view: browsing individual matches rather than
    an aggregate. `resultados` filters on resultado_partido (W/D/L).
    """
    where_clauses = []
    params: list = []
    if campeonatos:
        where_clauses.append(f"campeonato IN ({','.join(['?'] * len(campeonatos))})")
        params.extend(campeonatos)
    if condiciones:
        where_clauses.append(f"condicion IN ({','.join(['?'] * len(condiciones))})")
        params.extend(condiciones)
    if resultados:
        where_clauses.append(f"resultado_partido IN ({','.join(['?'] * len(resultados))})")
        params.extend(resultados)
    year_sql, year_params = _year_condition("fecha", anios)
    if year_sql:
        where_clauses.append(year_sql)
        params.extend(year_params)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    query = f"SELECT * FROM match_results {where_sql} ORDER BY fecha DESC"
    return con.execute(query, params).df()


def match_lineup(con: duckdb.DuckDBPyConnection, match_id: str) -> pd.DataFrame:
    """Player-by-player stats for one match (the "planilla").

    Ordered by position in the classic back-to-front sequence (arquero,
    defensa, mediocampista, delantero), starters before substitutes within
    each position.
    """
    query = """
        SELECT
            jugador, posicion, titular, minutos, calificacion, goles, asistencias,
            remates_totales, remates_al_arco, pases_totales, pases_precision,
            entradas, intercepciones, despejes, duelos_totales, duelos_ganados,
            faltas_cometidas, faltas_recibidas, amarillas, rojas
        FROM player_match_features
        WHERE match_id = ?
        ORDER BY
            CASE posicion
                WHEN 'G' THEN 0
                WHEN 'D' THEN 1
                WHEN 'M' THEN 2
                WHEN 'F' THEN 3
                ELSE 4
            END,
            titular DESC,
            minutos DESC
    """
    return con.execute(query, [match_id]).df()


_TEAM_SUMMARY_GROUP_COLUMNS = {"condicion", "campeonato"}


def team_summary(
    con: duckdb.DuckDBPyConnection,
    group_by: str = "condicion",
    campeonatos: list[str] | None = None,
    anios: list[int] | None = None,
) -> pd.DataFrame:
    """Win/draw/loss record and average points/goals, grouped by condicion or campeonato."""
    if group_by not in _TEAM_SUMMARY_GROUP_COLUMNS:
        raise ValueError(f"group_by debe ser uno de {_TEAM_SUMMARY_GROUP_COLUMNS}")

    where_clauses = []
    params: list = []
    if campeonatos:
        where_clauses.append(f"campeonato IN ({','.join(['?'] * len(campeonatos))})")
        params.extend(campeonatos)
    year_sql, year_params = _year_condition("fecha", anios)
    if year_sql:
        where_clauses.append(year_sql)
        params.extend(year_params)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

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


def player_summary_aggregate(
    con: duckdb.DuckDBPyConnection,
    jugadores: list[str],
    anios: list[int] | None = None,
) -> pd.DataFrame:
    """One row per jugador, aggregating every match they played within the
    filtered year range -- unlike player_season_summary_filtered (one row
    per jugador x anio), this collapses seasons into a single summary per
    player, since the sidebar's year range is what controls that window;
    a jugador-vs-jugador comparison shouldn't fragment into one row per
    year it played. Also reports anio_min/anio_max so the UI can show what
    season span each player's row actually covers (a player who only
    joined partway through the filtered range won't cover all of it).

    Rates are recomputed from the aggregated totals -- same approach as
    analytics.build_player_season_summary -- so a season with few minutes
    doesn't skew the combined rate the way averaging per-season rates
    would.
    """
    if not jugadores:
        return pd.DataFrame()

    placeholders = ", ".join("?" for _ in jugadores)
    where_clauses = [f"jugador IN ({placeholders})", "jugo"]
    params: list = list(jugadores)
    year_sql, year_params = _year_condition("fecha", anios)
    if year_sql:
        where_clauses.append(year_sql)
        params.extend(year_params)

    query = f"SELECT * FROM player_match_features WHERE {' AND '.join(where_clauses)}"
    played = con.execute(query, params).df()
    if played.empty:
        return played

    grouped = played.groupby("jugador", dropna=False)
    summary = grouped.agg(
        posicion=("posicion", lambda s: s.mode().iat[0] if not s.mode().empty else pd.NA),
        partidos_jugados=("match_id", "nunique"),
        titularidades=("titular", "sum"),
        minutos_totales=("minutos", "sum"),
        goles=("goles", "sum"),
        asistencias=("asistencias", "sum"),
        duelos_totales=("duelos_totales", "sum"),
        duelos_ganados=("duelos_ganados", "sum"),
        amarillas=("amarillas", "sum"),
        rojas=("rojas", "sum"),
        calificacion_promedio=("calificacion", "mean"),
        pases_precision_promedio=("pases_precision_num", "mean"),
        anio_min=("anio", "min"),
        anio_max=("anio", "max"),
    ).reset_index()

    minutos = summary["minutos_totales"].replace(0, pd.NA)
    summary["goles_por90"] = summary["goles"] / minutos * 90
    summary["asistencias_por90"] = summary["asistencias"] / minutos * 90
    summary["duelos_ganados_pct"] = summary["duelos_ganados"] / summary["duelos_totales"].replace(0, pd.NA)

    return summary.sort_values("jugador").reset_index(drop=True)


def player_match_history(
    con: duckdb.DuckDBPyConnection,
    jugador: str,
    anios: list[int] | None = None,
) -> pd.DataFrame:
    """A player's match-by-match rows, plus resultado_partido/puntos joined
    in from match_results -- the team's W/D/L outcome for that match, reused
    (not recomputed) so the Ficha de jugador form chart can color by result
    consistently with the rest of the dashboard.
    """
    where_clauses = ["p.jugador = ?"]
    params: list = [jugador]
    year_sql, year_params = _year_condition("p.fecha", anios)
    if year_sql:
        where_clauses.append(year_sql)
        params.extend(year_params)
    query = f"""
        SELECT p.*, m.resultado_partido, m.puntos
        FROM player_match_features p
        LEFT JOIN match_results m ON p.match_id = m.match_id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY p.fecha
    """
    return con.execute(query, params).df()


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


def latest_match_date(con: duckdb.DuckDBPyConnection) -> str | None:
    """Most recent match date across the whole dataset (unfiltered).

    Shown next to dataset_last_updated in the sidebar -- together they
    answer "how current is this data" (when was it refreshed) and "how
    current is the season" (when was the last match played).
    """
    row = con.execute("SELECT MAX(fecha) FROM match_results WHERE fecha IS NOT NULL").fetchone()
    return row[0] if row else None
