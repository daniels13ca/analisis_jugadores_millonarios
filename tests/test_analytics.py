from pathlib import Path

import pandas as pd
import pytest

from conftest import make_match_payload, make_player, write_match_json

from millos_data.analytics import (
    PLAYER_NAME_ALIASES,
    build_match_results,
    build_player_match_features,
    build_player_season_summary,
    canonicalize_player_names,
    derive_match_outcome,
    normalize_name_key,
    parse_pass_accuracy,
    per_90,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("80%", 0.80),
        ("0%", 0.0),
        ("100%", 1.0),
        (80, 0.80),
        (0.8, 0.8),
        (None, "NA"),
        ("", "NA"),
        ("n/a", "NA"),
    ],
)
def test_parse_pass_accuracy(value, expected) -> None:
    result = parse_pass_accuracy(value)
    if expected == "NA":
        assert pd.isna(result)
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    ("resultado", "condicion", "expected"),
    [
        ("2 - 1", "Local", {"goles_favor": 2, "goles_contra": 1, "resultado_partido": "W", "puntos": 3}),
        ("2 - 1", "Visitante", {"goles_favor": 1, "goles_contra": 2, "resultado_partido": "L", "puntos": 0}),
        ("1 - 1", "Local", {"goles_favor": 1, "goles_contra": 1, "resultado_partido": "D", "puntos": 1}),
        ("0 - 3", "Visitante", {"goles_favor": 3, "goles_contra": 0, "resultado_partido": "W", "puntos": 3}),
    ],
)
def test_derive_match_outcome_from_home_away_perspective(resultado, condicion, expected) -> None:
    assert derive_match_outcome(resultado, condicion) == expected


def test_derive_match_outcome_handles_malformed_input() -> None:
    result = derive_match_outcome("suspendido", "Local")
    assert all(pd.isna(value) for value in result.values())

    result = derive_match_outcome("1 - 1", None)
    assert all(pd.isna(value) for value in result.values())


def test_per_90_is_na_when_no_minutes_played() -> None:
    df = pd.DataFrame({"minutos": [90, 45, 0, None], "goles": [1, 1, 0, 0]})
    result = per_90(df, ["goles"])

    assert result.loc[0, "goles_por90"] == pytest.approx(1.0)
    assert result.loc[1, "goles_por90"] == pytest.approx(2.0)
    assert pd.isna(result.loc[2, "goles_por90"])
    assert pd.isna(result.loc[3, "goles_por90"])
    # per_90 must not mutate the input
    assert "goles_por90" not in df.columns


def test_build_match_results_includes_matches_without_player_stats(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2024_Stats_Detalladas"

    write_match_json(
        stats_dir / "2024-01-19_Visitante_Junior.json",
        make_match_payload(
            # "0 - 1" is home(Junior) - away(Millonarios): an away win.
            "2024-01-19", "Visitante", "0 - 1", rival="Junior", jugadores=[make_player("Jugador Uno")]
        ),
    )
    # A match with no player stats captured (e.g. lineup wasn't tracked yet).
    write_match_json(
        stats_dir / "2024-01-25_Local_Junior.json",
        make_match_payload("2024-01-25", "Local", "0 - 2", rival="Junior", jugadores=[]),
    )

    results = build_match_results(tmp_path)

    assert len(results) == 2
    assert set(results["tiene_datos_jugadores"]) == {True, False}

    empty_match_row = results[results["fecha"] == "2024-01-25"].iloc[0]
    assert bool(empty_match_row["tiene_datos_jugadores"]) is False
    assert empty_match_row["resultado_partido"] == "L"
    assert empty_match_row["goles_favor"] == 0
    assert empty_match_row["goles_contra"] == 2

    win_row = results[results["fecha"] == "2024-01-19"].iloc[0]
    assert win_row["resultado_partido"] == "W"
    assert win_row["puntos"] == 3


def test_build_player_match_features_adds_derived_columns() -> None:
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m1"],
            "fecha": ["2024-01-19", "2024-01-19"],
            "jugador": ["Titular", "Suplente"],
            "minutos": [90, 0],
            "calificacion": ["7.5", None],
            "titular": [True, False],
            "goles": [1, 0],
            "asistencias": [0, 0],
            "remates_totales": [3, 0],
            "remates_al_arco": [2, 0],
            "duelos_totales": [4, 0],
            "duelos_ganados": [2, 0],
            "faltas_cometidas": [1, 0],
            "pases_precision": ["75%", None],
        }
    )

    features = build_player_match_features(df)

    titular = features[features["jugador"] == "Titular"].iloc[0]
    suplente = features[features["jugador"] == "Suplente"].iloc[0]

    assert bool(titular["jugo"]) is True
    assert bool(suplente["jugo"]) is False
    assert titular["pases_precision_num"] == pytest.approx(0.75)
    assert pd.isna(suplente["pases_precision_num"])
    assert titular["goles_por90"] == pytest.approx(1.0)
    assert pd.isna(suplente["goles_por90"])
    assert features["anio"].iloc[0] == 2024


def test_build_player_season_summary_aggregates_totals_not_averaged_rates() -> None:
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "fecha": ["2024-01-19", "2024-02-02"],
            "jugador": ["Jugador Uno", "Jugador Uno"],
            "posicion": ["F", "F"],
            "minutos": [90, 45],
            "calificacion": ["7.0", "8.0"],
            "titular": [True, False],
            "goles": [1, 1],
            "asistencias": [0, 1],
            "remates_totales": [3, 2],
            "remates_al_arco": [2, 1],
            "duelos_totales": [4, 2],
            "duelos_ganados": [2, 2],
            "faltas_cometidas": [1, 0],
            "amarillas": [0, 1],
            "rojas": [0, 0],
            "pases_precision": ["70%", "90%"],
        }
    )

    features = build_player_match_features(df)
    summary = build_player_season_summary(features)

    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["partidos_jugados"] == 2
    assert row["minutos_totales"] == 135
    assert row["goles"] == 2
    # 2 goals in 135 minutes -> 90-minute rate, computed from totals.
    assert row["goles_por90"] == pytest.approx(2 / 135 * 90)
    assert row["calificacion_promedio"] == pytest.approx(7.5)
    assert row["duelos_ganados_pct"] == pytest.approx(4 / 6)


def test_normalize_name_key_ignores_accents_case_and_spacing() -> None:
    assert normalize_name_key("Daniel Ruíz") == normalize_name_key("daniel  ruiz")


def test_canonicalize_player_names_picks_most_frequent_variant() -> None:
    df = pd.DataFrame({"jugador": ["Daniel Ruiz"] * 3 + ["Daniel Ruíz"] * 2 + ["Andrés Llinás"]})

    result = canonicalize_player_names(df)

    assert set(result["jugador"]) == {"Daniel Ruiz", "Andrés Llinás"}
    assert (result["jugador"] == "Daniel Ruiz").sum() == 5


def test_canonicalize_player_names_applies_manual_aliases() -> None:
    # "David Silva" / "David Macalister Silva" is a real case in the dataset:
    # not an accent variant, so the frequency-based logic alone can't merge
    # it -- it needs the explicit PLAYER_NAME_ALIASES entry.
    assert "David Silva" in PLAYER_NAME_ALIASES
    df = pd.DataFrame({"jugador": ["David Silva", "David Macalister Silva", "David Macalister Silva"]})

    result = canonicalize_player_names(df)

    assert set(result["jugador"]) == {"David Macalister Silva"}
    assert (result["jugador"] == "David Macalister Silva").sum() == 3


def test_build_player_match_features_merges_name_variants() -> None:
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "fecha": ["2024-01-19", "2024-01-25"],
            "jugador": ["Daniel Ruiz", "Daniel Ruíz"],
            "posicion": ["M", "M"],
            "minutos": [90, 90],
            "calificacion": ["7.0", "7.5"],
            "titular": [True, True],
            "goles": [0, 1],
            "asistencias": [0, 0],
            "remates_totales": [0, 0],
            "remates_al_arco": [0, 0],
            "duelos_totales": [0, 0],
            "duelos_ganados": [0, 0],
            "faltas_cometidas": [0, 0],
            "amarillas": [0, 0],
            "rojas": [0, 0],
            "pases_precision": ["70%", "70%"],
        }
    )

    features = build_player_match_features(df)
    summary = build_player_season_summary(features)

    assert features["jugador"].nunique() == 1
    assert len(summary) == 1
    assert summary.iloc[0]["partidos_jugados"] == 2
    assert summary.iloc[0]["goles"] == 1
