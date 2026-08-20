from pathlib import Path

import pandas as pd
import pytest

from millos_data.dashboard import data as dashboard_data


@pytest.fixture
def analytics_dir(tmp_path: Path) -> Path:
    match_results = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4"],
            "source_file": ["m1.json", "m2.json", "m3.json", "m4.json"],
            "fecha": ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"],
            "campeonato": ["Primera A", "Primera A", "Copa", "Primera A"],
            "rival": ["Junior", "Santa Fe", "Nacional", "America"],
            "condicion": ["Local", "Visitante", "Local", "Visitante"],
            "resultado": ["2 - 1", "1 - 1", "0 - 1", "3 - 0"],
            "goles_favor": [2, 1, 0, 0],
            "goles_contra": [1, 1, 1, 3],
            "resultado_partido": ["W", "D", "L", "L"],
            "puntos": [3, 1, 0, 0],
            "tiene_datos_jugadores": [True, True, False, True],
        }
    )

    player_match_features = pd.DataFrame(
        {
            "match_id": ["m1", "m1", "m2", "m4"],
            "fecha": ["2024-01-01", "2024-01-01", "2024-01-08", "2024-01-22"],
            "jugador": ["Jugador A", "Jugador B", "Jugador A", "Jugador A"],
            "posicion": ["F", "M", "F", "F"],
            "minutos": [90, 90, 45, 0],
            "calificacion": [7.5, 6.8, 7.0, None],
            "jugo": [True, True, True, False],
            "goles": [1, 0, 0, 0],
            "asistencias": [0, 1, 0, 0],
        }
    )

    player_season_summary = pd.DataFrame(
        {
            "jugador": ["Jugador A", "Jugador A", "Jugador B"],
            "anio": [2024, 2023, 2024],
            "posicion": ["F", "F", "M"],
            "partidos_jugados": [2, 10, 1],
            "minutos_totales": [135, 800, 90],
            "goles": [1, 5, 0],
            "asistencias": [0, 2, 1],
            "goles_por90": [1 / 135 * 90, 5 / 800 * 90, 0.0],
            "asistencias_por90": [0.0, 2 / 800 * 90, 1.0],
            "calificacion_promedio": [7.25, 6.9, 6.8],
            "duelos_ganados_pct": [0.5, 0.6, 0.4],
            "pases_precision_promedio": [0.7, 0.75, 0.65],
        }
    )

    directory = tmp_path / "analytics"
    directory.mkdir()
    match_results.to_csv(directory / "match_results.csv", index=False, encoding="utf-8-sig")
    player_match_features.to_csv(
        directory / "player_match_features.csv", index=False, encoding="utf-8-sig"
    )
    player_season_summary.to_csv(
        directory / "player_season_summary.csv", index=False, encoding="utf-8-sig"
    )
    return directory


def test_load_tables_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        dashboard_data.load_tables(tmp_path / "does_not_exist")


def test_get_connection_registers_all_tables(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert {"match_results", "player_match_features", "player_season_summary"} <= tables


def test_list_helpers(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    assert dashboard_data.list_campeonatos(con) == ["Copa", "Primera A"]
    assert dashboard_data.list_condiciones(con) == ["Local", "Visitante"]
    assert dashboard_data.list_anios(con) == [2023, 2024]
    assert dashboard_data.list_posiciones(con) == ["F", "M"]
    assert dashboard_data.list_jugadores(con) == ["Jugador A", "Jugador B"]


def test_match_results_with_form_computes_cumulative_points(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    result = dashboard_data.match_results_with_form(con)

    assert list(result["fecha"]) == ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"]
    assert list(result["puntos_acumulados"]) == [3, 4, 4, 4]
    # rolling window of 5 with only 4 rows -> average over all rows seen so far
    assert result["forma_reciente"].iloc[-1] == pytest.approx(4 / 4)


def test_match_results_with_form_filters_by_campeonato(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    result = dashboard_data.match_results_with_form(con, campeonatos=["Copa"])
    assert len(result) == 1
    assert result.iloc[0]["rival"] == "Nacional"


def test_team_summary_by_condicion(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    summary = dashboard_data.team_summary(con, group_by="condicion").set_index("condicion")

    assert summary.loc["Local", "partidos"] == 2
    assert summary.loc["Local", "victorias"] == 1
    assert summary.loc["Local", "derrotas"] == 1
    assert summary.loc["Visitante", "partidos"] == 2


def test_team_summary_rejects_invalid_group_by(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    with pytest.raises(ValueError):
        dashboard_data.team_summary(con, group_by="rival")


def test_player_season_summary_filtered(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)

    only_2024 = dashboard_data.player_season_summary_filtered(con, anios=[2024])
    assert set(only_2024["jugador"]) == {"Jugador A", "Jugador B"}
    assert len(only_2024) == 2

    only_player_a = dashboard_data.player_season_summary_filtered(con, jugadores=["Jugador A"])
    assert len(only_player_a) == 2  # 2023 and 2024 rows


def test_player_match_history_ordered_by_fecha(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    history = dashboard_data.player_match_history(con, "Jugador A")

    assert list(history["fecha"]) == ["2024-01-01", "2024-01-08", "2024-01-22"]
    assert history["jugador"].eq("Jugador A").all()


def test_position_averages_groups_by_posicion(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    averages = dashboard_data.position_averages(con).set_index("posicion")

    # posicion "F" only has Jugador A (2 rows: 2023 and 2024).
    expected_f = (1 / 135 * 90 + 5 / 800 * 90) / 2
    assert averages.loc["F", "goles_por90"] == pytest.approx(expected_f)
    # posicion "M" only has Jugador B (1 row).
    assert averages.loc["M", "goles_por90"] == pytest.approx(0.0)


def test_position_averages_filters_by_anio(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    averages = dashboard_data.position_averages(con, anios=[2024]).set_index("posicion")

    # With only 2024, "F" reduces to Jugador A's single 2024 row.
    assert averages.loc["F", "goles_por90"] == pytest.approx(1 / 135 * 90)


def test_dataset_last_updated_returns_mtime(analytics_dir: Path) -> None:
    mtime = dashboard_data.dataset_last_updated(analytics_dir)
    assert mtime is not None
    assert mtime == pytest.approx((analytics_dir / "match_results.csv").stat().st_mtime)


def test_dataset_last_updated_missing_directory(tmp_path: Path) -> None:
    assert dashboard_data.dataset_last_updated(tmp_path / "nope") is None
