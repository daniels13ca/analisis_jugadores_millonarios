"""Unit tests for the Ranking-tab helper logic in dashboard/app.py that
doesn't touch Streamlit widgets directly (podium formatting, the
percent-column display fix). See test_dashboard_pitch.py for why a direct
import of app.py is safe here.
"""

import math

import pandas as pd
import pytest

from millos_data.dashboard.app import (
    PERCENT_COLUMNS,
    _format_metric_value,
    _metric_scale,
    _scale_percent_columns,
)


def test_percent_columns_are_the_ones_stored_as_fractions() -> None:
    assert PERCENT_COLUMNS == ["duelos_ganados_pct", "pases_precision_promedio"]


def test_scale_percent_columns_multiplies_by_100() -> None:
    df = pd.DataFrame({"duelos_ganados_pct": [0.5, 0.65], "goles": [1, 2]})
    scaled = _scale_percent_columns(df)

    assert scaled["duelos_ganados_pct"].tolist() == [50.0, 65.0]
    assert scaled["goles"].tolist() == [1, 2]  # untouched
    assert df["duelos_ganados_pct"].tolist() == [0.5, 0.65]  # original not mutated


def test_scale_percent_columns_skips_missing_columns() -> None:
    df = pd.DataFrame({"goles": [1, 2]})
    scaled = _scale_percent_columns(df)
    assert scaled["goles"].tolist() == [1, 2]


def test_metric_scale() -> None:
    assert _metric_scale("duelos_ganados_pct") == 100
    assert _metric_scale("pases_precision_promedio") == 100
    assert _metric_scale("goles_por90") == 1
    assert _metric_scale("minutos_totales") == 1


@pytest.mark.parametrize(
    ("metric", "value", "expected"),
    [
        ("duelos_ganados_pct", 0.6543, "65%"),
        ("pases_precision_promedio", 0.5, "50%"),
        ("minutos_totales", 1234.0, "1234"),
        ("goles_por90", 0.456, "0.46"),
        ("calificacion_promedio", 7.0, "7.00"),
    ],
)
def test_format_metric_value(metric, value, expected) -> None:
    assert _format_metric_value(metric, value) == expected


def test_format_metric_value_missing_data() -> None:
    assert _format_metric_value("goles_por90", math.nan) == "s/d"
    assert _format_metric_value("goles_por90", pd.NA) == "s/d"
