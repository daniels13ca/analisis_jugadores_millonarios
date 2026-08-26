"""Unit tests for the pitch-diagram layout logic in dashboard/app.py.

These are plain functions with no Streamlit widgets involved, so -- unlike
the rest of app.py, exercised through Streamlit's AppTest in
test_dashboard_app.py -- they're testable with a direct import.
"""

import pandas as pd

from millos_data.dashboard.app import PITCH_WIDTH, _lineup_pitch_positions, _spread_along_width


def _titular(jugador: str, posicion: str) -> dict:
    return {
        "jugador": jugador,
        "posicion": posicion,
        "titular": True,
        "minutos": 90,
        "calificacion": 7.0,
        "goles": 0,
        "asistencias": 0,
    }


def test_spread_along_width_single_value_is_centered() -> None:
    assert _spread_along_width(1, low=0, high=10) == [5.0]


def test_spread_along_width_multiple_values_evenly_spaced() -> None:
    assert _spread_along_width(3, low=0, high=10) == [0.0, 5.0, 10.0]


def test_spread_along_width_zero_is_empty() -> None:
    assert _spread_along_width(0) == []


def test_lineup_pitch_positions_builds_442_shape() -> None:
    titulares = pd.DataFrame(
        [
            _titular("Arquero1", "G"),
            _titular("Defensa1", "D"),
            _titular("Defensa2", "D"),
            _titular("Defensa3", "D"),
            _titular("Defensa4", "D"),
            _titular("Medio1", "M"),
            _titular("Medio2", "M"),
            _titular("Medio3", "M"),
            _titular("Medio4", "M"),
            _titular("Delantero1", "F"),
            _titular("Delantero2", "F"),
        ]
    )

    positions = _lineup_pitch_positions(titulares)

    assert len(positions) == 11
    # Rows ordered G -> D -> M -> F, each at a distinct, increasing x.
    x_by_posicion = positions.groupby("posicion")["pitch_x"].first()
    assert x_by_posicion["G"] < x_by_posicion["D"] < x_by_posicion["M"] < x_by_posicion["F"]
    # Every player in the same row shares the same x.
    assert positions[positions["posicion"] == "D"]["pitch_x"].nunique() == 1
    # Players within a row get distinct y positions, within pitch bounds.
    defensa_ys = positions[positions["posicion"] == "D"]["pitch_y"]
    assert defensa_ys.nunique() == 4
    assert defensa_ys.between(0, PITCH_WIDTH).all()


def test_lineup_pitch_positions_handles_unexpected_position_code() -> None:
    titulares = pd.DataFrame([_titular("Comodin", "X")])
    positions = _lineup_pitch_positions(titulares)
    assert len(positions) == 1
    assert positions.iloc[0]["pitch_y"] is not None


def test_lineup_pitch_positions_empty_input() -> None:
    empty = pd.DataFrame(columns=["jugador", "posicion", "titular", "minutos", "calificacion", "goles", "asistencias"])
    positions = _lineup_pitch_positions(empty)
    assert positions.empty
