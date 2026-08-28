"""Smoke tests for the Streamlit app: does it render without raising, for
each tab, given a small valid analytics/ directory. Not a test of visual
layout -- AppTest runs the script and lets us assert on exceptions and on
a handful of rendered elements.
"""

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "src" / "millos_data" / "dashboard" / "app.py")


@pytest.fixture
def analytics_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    match_results = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "source_file": ["m1.json", "m2.json"],
            "fecha": ["2024-01-01", "2024-01-08"],
            "campeonato": ["Primera A", "Primera A"],
            "rival": ["Junior", "Santa Fe"],
            "condicion": ["Local", "Visitante"],
            "resultado": ["2 - 1", "1 - 1"],
            "goles_favor": [2, 1],
            "goles_contra": [1, 1],
            "resultado_partido": ["W", "D"],
            "puntos": [3, 1],
            "tiene_datos_jugadores": [True, True],
        }
    )
    player_match_features = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "fecha": ["2024-01-01", "2024-01-08"],
            "rival": ["Junior", "Santa Fe"],
            "condicion": ["Local", "Visitante"],
            "resultado": ["2 - 1", "1 - 1"],
            "jugador": ["Jugador A", "Jugador A"],
            "posicion": ["F", "F"],
            "titular": [True, True],
            "minutos": [90, 45],
            "calificacion": [7.5, 7.0],
            "jugo": [True, True],
            "goles": [1, 0],
            "asistencias": [0, 0],
            "remates_totales": [2, 1],
            "remates_al_arco": [1, 0],
            "pases_totales": [30, 15],
            "pases_precision": ["80%", "70%"],
            "pases_precision_num": [0.8, 0.7],
            "entradas": [0, 0],
            "intercepciones": [0, 0],
            "despejes": [0, 0],
            "duelos_totales": [4, 2],
            "duelos_ganados": [2, 1],
            "faltas_cometidas": [1, 0],
            "faltas_recibidas": [2, 1],
            "amarillas": [0, 0],
            "rojas": [0, 0],
        }
    )
    player_season_summary = pd.DataFrame(
        {
            "jugador": ["Jugador A"],
            "anio": [2024],
            "posicion": ["F"],
            "partidos_jugados": [2],
            "minutos_totales": [135],
            "goles": [1],
            "asistencias": [0],
            "goles_por90": [1 / 135 * 90],
            "asistencias_por90": [0.0],
            "calificacion_promedio": [7.25],
            "duelos_ganados_pct": [0.5],
            "pases_precision_promedio": [0.7],
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

    monkeypatch.setenv("MILLOS_ANALYTICS_DIR", str(directory))
    return directory


def test_app_renders_without_exceptions(analytics_dir: Path) -> None:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    assert not at.exception
    assert any("Millonarios FC" in title.value for title in at.title)

    # "Partidos" is the 2nd tab: "Histórico de Partidos" (row-selectable) +
    # "Planilla individual de partido", defaulting to the most recent match.
    tab_partidos = at.tabs[1]
    assert len(tab_partidos.dataframe) == 2
    assert any("Histórico de Partidos" in s.value for s in tab_partidos.subheader)
    assert any("Planilla individual de partido" in s.value for s in tab_partidos.subheader)


def test_app_shows_error_when_analytics_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILLOS_ANALYTICS_DIR", str(tmp_path / "no_analytics_here"))

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    assert not at.exception
    assert any("build-analytics" in error.value for error in at.error)
