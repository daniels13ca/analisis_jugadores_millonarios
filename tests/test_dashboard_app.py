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
            "match_id": ["m1", "m2", "m1"],
            "fecha": ["2024-01-01", "2024-01-08", "2024-01-01"],
            "anio": [2024, 2024, 2024],
            "rival": ["Junior", "Santa Fe", "Junior"],
            "condicion": ["Local", "Visitante", "Local"],
            "resultado": ["2 - 1", "1 - 1", "2 - 1"],
            "jugador": ["Jugador A", "Jugador A", "Jugador B"],
            "posicion": ["F", "F", "M"],
            "titular": [True, True, False],
            "minutos": [90, 45, 20],
            "calificacion": [7.5, 7.0, 6.0],
            "jugo": [True, True, True],
            "goles": [1, 0, 0],
            "asistencias": [0, 0, 0],
            "remates_totales": [2, 1, 0],
            "remates_al_arco": [1, 0, 0],
            "pases_totales": [30, 15, 10],
            "pases_precision": ["80%", "70%", "50%"],
            "pases_precision_num": [0.8, 0.7, 0.5],
            "entradas": [0, 0, 0],
            "intercepciones": [0, 0, 0],
            "despejes": [0, 0, 0],
            "duelos_totales": [4, 2, 2],
            "duelos_ganados": [2, 1, 1],
            "faltas_cometidas": [1, 0, 0],
            "faltas_recibidas": [2, 1, 0],
            "amarillas": [0, 0, 0],
            "rojas": [0, 0, 0],
        }
    )
    # Jugador B: a single-match cameo, on purpose -- exercises the
    # "mínimo de partidos" low-sample warnings (default threshold is 3).
    player_season_summary = pd.DataFrame(
        {
            "jugador": ["Jugador A", "Jugador B"],
            "anio": [2024, 2024],
            "posicion": ["F", "M"],
            "partidos_jugados": [2, 1],
            "minutos_totales": [135, 20],
            "goles": [1, 0],
            "asistencias": [0, 0],
            "goles_por90": [1 / 135 * 90, 0.0],
            "asistencias_por90": [0.0, 0.0],
            "calificacion_promedio": [7.25, 6.0],
            "duelos_ganados_pct": [0.5, 0.5],
            "pases_precision_promedio": [0.7, 0.5],
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


def test_comparison_tab_renders_with_a_selection(analytics_dir: Path) -> None:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    # "Jugadores (Ficha / Comparativa)" has no format_func, unlike "Posición
    # (Ranking)" -- see test_dashboard_ranking.py's module docstring for why
    # that matters for AppTest's .set_value().
    jugadores_widget = next(m for m in at.sidebar.multiselect if m.label == "Jugadores (Ficha / Comparativa)")
    jugadores_widget.set_value(["Jugador A"])
    at.run(timeout=30)

    assert not at.exception
    tab_comparativa = at.tabs[4]
    assert any("Comparativa de jugadores" in h.value for h in tab_comparativa.header)
    assert len(tab_comparativa.dataframe) == 1
    assert any("Jugador A" in m.value for m in tab_comparativa.markdown)


def test_glossary_expander_present(analytics_dir: Path) -> None:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    assert not at.exception
    assert any(e.label == "❓ Glosario de métricas" for e in at.expander)


def test_csv_download_buttons_present_across_tabs(analytics_dir: Path) -> None:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    assert not at.exception
    assert any("Descargar partidos con forma" in d.label for d in at.tabs[0].download_button)
    assert any("Descargar histórico" in d.label for d in at.tabs[1].download_button)
    assert any("Descargar planilla" in d.label for d in at.tabs[1].download_button)
    assert any("Descargar resumen por temporada" in d.label for d in at.tabs[3].download_button)
    assert any("Descargar historial partido a partido" in d.label for d in at.tabs[3].download_button)


def test_min_partidos_slider_drives_ficha_low_sample_warning(analytics_dir: Path) -> None:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    min_slider = next(s for s in at.sidebar.slider if "Mínimo de partidos" in s.label)
    assert min_slider.value == 3  # DEFAULT_MIN_PARTIDOS

    jugadores_widget = next(m for m in at.sidebar.multiselect if m.label == "Jugadores (Ficha / Comparativa)")
    jugadores_widget.set_value(["Jugador B"])  # 1 partido jugado, below the default of 3
    at.run(timeout=30)

    assert not at.exception
    tab_ficha = at.tabs[3]
    assert any("por debajo del mínimo configurado" in c.value for c in tab_ficha.caption)


def test_comparativa_flags_low_sample_players(analytics_dir: Path) -> None:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    jugadores_widget = next(m for m in at.sidebar.multiselect if m.label == "Jugadores (Ficha / Comparativa)")
    jugadores_widget.set_value(["Jugador A", "Jugador B"])
    at.run(timeout=30)

    assert not at.exception
    tab_comparativa = at.tabs[4]
    assert any("Jugador B" in c.value and "menos de 3 partido" in c.value for c in tab_comparativa.caption)


def test_ranking_vista_toggle_switches_periodo_column(analytics_dir: Path) -> None:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    tab_ranking = at.tabs[2]
    assert "anio" in tab_ranking.dataframe[0].value.columns

    vista_radio = next(r for r in tab_ranking.radio if r.label == "Vista")
    vista_radio.set_value("Agregado por jugador")
    at.run(timeout=30)

    assert not at.exception
    tab_ranking = at.tabs[2]
    assert "temporadas" in tab_ranking.dataframe[0].value.columns


def test_ranking_ver_ficha_button_preselects_player_in_sidebar(analytics_dir: Path) -> None:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    tab_ranking = at.tabs[2]
    boton = next(b for b in tab_ranking.button if "Jugador A" in b.label)
    boton.click()
    at.run(timeout=30)

    assert not at.exception
    jugadores_widget = next(m for m in at.sidebar.multiselect if m.label == "Jugadores (Ficha / Comparativa)")
    assert jugadores_widget.value == ["Jugador A"]


def test_deep_link_query_params_preselect_jugador_and_anio(analytics_dir: Path) -> None:
    at = AppTest.from_file(APP_PATH)
    at.query_params["jugador"] = "Jugador B"
    at.run(timeout=30)

    assert not at.exception
    jugadores_widget = next(m for m in at.sidebar.multiselect if m.label == "Jugadores (Ficha / Comparativa)")
    assert jugadores_widget.value == ["Jugador B"]


def test_app_shows_error_when_analytics_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILLOS_ANALYTICS_DIR", str(tmp_path / "no_analytics_here"))

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    assert not at.exception
    assert any("build-analytics" in error.value for error in at.error)
