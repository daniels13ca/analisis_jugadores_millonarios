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
            "titular": [True, False, True, False],
            "minutos": [90, 90, 45, 0],
            "calificacion": [7.5, 6.8, 7.0, None],
            "jugo": [True, True, True, False],
            "goles": [1, 0, 0, 0],
            "asistencias": [0, 1, 0, 0],
            "remates_totales": [2, 0, 1, 0],
            "remates_al_arco": [1, 0, 0, 0],
            "pases_totales": [30, 40, 15, 0],
            "pases_precision": ["80%", "90%", "70%", "0%"],
            "pases_precision_num": [0.8, 0.9, 0.7, 0.0],
            "anio": [2024, 2024, 2024, 2024],
            "entradas": [0, 2, 0, 0],
            "intercepciones": [0, 1, 0, 0],
            "despejes": [0, 0, 0, 0],
            "duelos_totales": [4, 5, 2, 0],
            "duelos_ganados": [2, 3, 1, 0],
            "faltas_cometidas": [1, 0, 0, 0],
            "faltas_recibidas": [2, 0, 1, 0],
            "amarillas": [0, 0, 0, 0],
            "rojas": [0, 0, 0, 0],
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


def test_list_match_years(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    # match_results in this fixture are all dated 2024, unlike
    # player_season_summary above which also has a 2023 row.
    assert dashboard_data.list_match_years(con) == [2024]


def test_match_results_with_form_computes_cumulative_points(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    result = dashboard_data.match_results_with_form(con)

    assert list(result["fecha"]) == ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"]
    assert list(result["puntos_acumulados"]) == [3, 4, 4, 4]
    # rolling window of 5 with only 4 rows -> average over all rows seen so far
    assert result["forma_reciente"].iloc[-1] == pytest.approx(4 / 4)


def test_points_race_by_year_resets_cumulative_per_year(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    race = dashboard_data.points_race_by_year(con)

    # The shared fixture's 4 matches are all in 2024 (puntos: 3, 1, 0, 0).
    assert set(race["anio"]) == {2024}
    assert list(race["jornada"]) == [1, 2, 3, 4]
    assert list(race["puntos_acumulados"]) == [3, 4, 4, 4]


def _write_match_results_only(tmp_path: Path, match_results: pd.DataFrame) -> Path:
    """Analytics dir with a custom match_results.csv (the other two tables
    empty) -- for tests that only exercise match_results-based queries.
    """
    directory = tmp_path / "analytics"
    directory.mkdir()
    match_results.to_csv(directory / "match_results.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(columns=["jugador"]).to_csv(
        directory / "player_match_features.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(columns=["jugador", "anio"]).to_csv(
        directory / "player_season_summary.csv", index=False, encoding="utf-8-sig"
    )
    return directory


def _multi_year_match_results() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "match_id": ["a1", "a2", "b1", "b2", "b3"],
            "fecha": ["2023-02-01", "2023-02-08", "2024-02-01", "2024-02-08", "2024-02-15"],
            "campeonato": ["Primera A"] * 5,
            "rival": ["X", "Y", "X", "Y", "Z"],
            "condicion": ["Local"] * 5,
            "resultado": ["1 - 0"] * 5,
            "goles_favor": [1] * 5,
            "goles_contra": [0] * 5,
            "resultado_partido": ["W"] * 5,
            "puntos": [3, 3, 3, 0, 1],
            "tiene_datos_jugadores": [True] * 5,
        }
    )


def test_points_race_by_year_multi_year_resets_and_aligns_by_jornada(tmp_path: Path) -> None:
    directory = _write_match_results_only(tmp_path, _multi_year_match_results())

    con = dashboard_data.get_connection(directory)
    race = dashboard_data.points_race_by_year(con).set_index(["anio", "jornada"])

    assert race.loc[(2023, 1), "puntos_acumulados"] == 3
    assert race.loc[(2023, 2), "puntos_acumulados"] == 6
    # 2024 resets to 0 instead of continuing from 2023's 6.
    assert race.loc[(2024, 1), "puntos_acumulados"] == 3
    assert race.loc[(2024, 2), "puntos_acumulados"] == 3
    assert race.loc[(2024, 3), "puntos_acumulados"] == 4


def test_points_race_by_year_filters_by_anios(tmp_path: Path) -> None:
    directory = _write_match_results_only(tmp_path, _multi_year_match_results())
    con = dashboard_data.get_connection(directory)

    race = dashboard_data.points_race_by_year(con, anios=[2024])
    assert set(race["anio"]) == {2024}
    assert len(race) == 3


def test_match_results_with_form_filters_by_anios(tmp_path: Path) -> None:
    directory = _write_match_results_only(tmp_path, _multi_year_match_results())
    con = dashboard_data.get_connection(directory)

    result = dashboard_data.match_results_with_form(con, anios=[2023])
    assert list(result["fecha"]) == ["2023-02-01", "2023-02-08"]


def test_matches_filtered_by_anios(tmp_path: Path) -> None:
    directory = _write_match_results_only(tmp_path, _multi_year_match_results())
    con = dashboard_data.get_connection(directory)

    result = dashboard_data.matches_filtered(con, anios=[2023])
    assert set(result["match_id"]) == {"a1", "a2"}


def test_team_summary_filters_by_anios(tmp_path: Path) -> None:
    directory = _write_match_results_only(tmp_path, _multi_year_match_results())
    con = dashboard_data.get_connection(directory)

    summary = dashboard_data.team_summary(con, group_by="condicion", anios=[2023])
    assert summary.loc[0, "partidos"] == 2


def test_jornada_calendar_labels_picks_most_common_month(tmp_path: Path) -> None:
    match_results = pd.DataFrame(
        {
            "match_id": ["a1", "a2", "a3", "b1", "b2"],
            # jornada 1: Jan/Jan -> Jan. jornada 2: Jul/Jun tie -> lower month
            # (Jun) wins the tiebreak. jornada 3: only 2023 has one -> Dec.
            "fecha": ["2023-01-15", "2023-07-01", "2023-12-01", "2024-01-20", "2024-06-25"],
            "campeonato": ["Primera A"] * 5,
            "rival": ["X"] * 5,
            "condicion": ["Local"] * 5,
            "resultado": ["1 - 0"] * 5,
            "goles_favor": [1] * 5,
            "goles_contra": [0] * 5,
            "resultado_partido": ["W"] * 5,
            "puntos": [3] * 5,
            "tiene_datos_jugadores": [True] * 5,
        }
    )
    directory = _write_match_results_only(tmp_path, match_results)

    con = dashboard_data.get_connection(directory)
    labels = dashboard_data.jornada_calendar_labels(con).set_index("jornada")["mes"]

    assert labels.loc[1] == 1
    assert labels.loc[2] == 6
    assert labels.loc[3] == 12


def test_jornada_calendar_labels_filters_by_anios(tmp_path: Path) -> None:
    directory = _write_match_results_only(tmp_path, _multi_year_match_results())
    con = dashboard_data.get_connection(directory)

    labels = dashboard_data.jornada_calendar_labels(con, anios=[2023]).set_index("jornada")["mes"]

    # 2023-only has 2 matches (jornada 1-2), unlike the unfiltered 3.
    assert set(labels.index) == {1, 2}


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


def test_player_summary_aggregate_collapses_years_into_one_row(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    summary = dashboard_data.player_summary_aggregate(con, jugadores=["Jugador A", "Jugador B"]).set_index("jugador")

    assert list(summary.index) == ["Jugador A", "Jugador B"]

    # Jugador A played m1 (90') and m2 (45'); m4 is excluded (jugo=False).
    a = summary.loc["Jugador A"]
    assert a["partidos_jugados"] == 2
    assert a["minutos_totales"] == 135
    assert a["goles"] == 1
    assert a["calificacion_promedio"] == pytest.approx(7.25)
    assert a["goles_por90"] == pytest.approx(1 / 135 * 90)
    assert a["duelos_ganados_pct"] == pytest.approx(3 / 6)
    assert a["anio_min"] == 2024
    assert a["anio_max"] == 2024

    b = summary.loc["Jugador B"]
    assert b["partidos_jugados"] == 1
    assert b["asistencias_por90"] == pytest.approx(1.0)


def test_player_summary_aggregate_empty_when_no_jugadores(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    assert dashboard_data.player_summary_aggregate(con, jugadores=[]).empty


def test_player_summary_aggregate_empty_when_year_excludes_everything(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    assert dashboard_data.player_summary_aggregate(con, jugadores=["Jugador A"], anios=[2099]).empty


def test_player_match_history_ordered_by_fecha(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    history = dashboard_data.player_match_history(con, "Jugador A")

    assert list(history["fecha"]) == ["2024-01-01", "2024-01-08", "2024-01-22"]
    assert history["jugador"].eq("Jugador A").all()


def test_player_match_history_joins_resultado_partido(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    history = dashboard_data.player_match_history(con, "Jugador A").set_index("match_id")

    # m1 -> W, m2 -> D, m4 -> L per the shared match_results fixture.
    assert history.loc["m1", "resultado_partido"] == "W"
    assert history.loc["m1", "puntos"] == 3
    assert history.loc["m4", "resultado_partido"] == "L"


def test_player_match_history_filters_by_anios(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)

    assert len(dashboard_data.player_match_history(con, "Jugador A", anios=[2024])) == 3
    # This fixture's player_match_features rows are all dated 2024.
    assert dashboard_data.player_match_history(con, "Jugador A", anios=[2023]).empty


def test_matches_filtered_defaults_to_most_recent_first(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    matches = dashboard_data.matches_filtered(con)

    assert list(matches["fecha"]) == ["2024-01-22", "2024-01-15", "2024-01-08", "2024-01-01"]
    assert len(matches) == 4


def test_matches_filtered_by_resultado(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    losses = dashboard_data.matches_filtered(con, resultados=["L"])

    assert list(losses["rival"]) == ["America", "Nacional"]


def test_matches_filtered_combines_filters(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    matches = dashboard_data.matches_filtered(
        con, campeonatos=["Primera A"], condiciones=["Local"]
    )

    assert list(matches["rival"]) == ["Junior"]


def test_match_lineup_orders_by_position_then_titular(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    lineup = dashboard_data.match_lineup(con, "m1")

    # m1 has "Jugador A" (posicion F) and "Jugador B" (posicion M); M ranks
    # before F in the arquero/defensa/mediocampista/delantero order.
    assert list(lineup["jugador"]) == ["Jugador B", "Jugador A"]
    assert list(lineup["posicion"]) == ["M", "F"]


def test_match_lineup_full_position_order(tmp_path: Path) -> None:
    match_results = pd.DataFrame(
        {
            "match_id": ["m1"],
            "fecha": ["2024-01-01"],
            "campeonato": ["Primera A"],
            "rival": ["Junior"],
            "condicion": ["Local"],
            "resultado": ["1 - 0"],
            "goles_favor": [1],
            "goles_contra": [0],
            "resultado_partido": ["W"],
            "puntos": [3],
            "tiene_datos_jugadores": [True],
        }
    )
    player_match_features = pd.DataFrame(
        {
            "match_id": ["m1", "m1", "m1", "m1"],
            "jugador": ["Delantero1", "Arquero1", "Defensa1", "Mediocampista1"],
            "posicion": ["F", "G", "D", "M"],
            "titular": [True, True, True, True],
            "minutos": [90, 90, 90, 90],
            "calificacion": [7.0, 7.0, 7.0, 7.0],
            "goles": [0, 0, 0, 0],
            "asistencias": [0, 0, 0, 0],
            "remates_totales": [0, 0, 0, 0],
            "remates_al_arco": [0, 0, 0, 0],
            "pases_totales": [0, 0, 0, 0],
            "pases_precision": ["0%", "0%", "0%", "0%"],
            "entradas": [0, 0, 0, 0],
            "intercepciones": [0, 0, 0, 0],
            "despejes": [0, 0, 0, 0],
            "duelos_totales": [0, 0, 0, 0],
            "duelos_ganados": [0, 0, 0, 0],
            "faltas_cometidas": [0, 0, 0, 0],
            "faltas_recibidas": [0, 0, 0, 0],
            "amarillas": [0, 0, 0, 0],
            "rojas": [0, 0, 0, 0],
        }
    )
    directory = tmp_path / "analytics"
    directory.mkdir()
    match_results.to_csv(directory / "match_results.csv", index=False, encoding="utf-8-sig")
    player_match_features.to_csv(
        directory / "player_match_features.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(columns=["jugador", "anio"]).to_csv(
        directory / "player_season_summary.csv", index=False, encoding="utf-8-sig"
    )

    con = dashboard_data.get_connection(directory)
    lineup = dashboard_data.match_lineup(con, "m1")

    assert list(lineup["posicion"]) == ["G", "D", "M", "F"]
    assert list(lineup["jugador"]) == ["Arquero1", "Defensa1", "Mediocampista1", "Delantero1"]


def test_match_lineup_empty_for_match_without_player_data(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    lineup = dashboard_data.match_lineup(con, "m3")  # m3 has tiene_datos_jugadores=False
    assert lineup.empty


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


def test_latest_match_date(analytics_dir: Path) -> None:
    con = dashboard_data.get_connection(analytics_dir)
    assert dashboard_data.latest_match_date(con) == "2024-01-22"
