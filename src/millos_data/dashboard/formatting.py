"""Shared display formatting for the dashboard: friendly labels/colors for
raw column values (W/D/L, Local/Visitante) and the brand color palette used
across every Plotly chart, so the whole app reads as one consistent system
instead of each tab picking its own defaults.

Kept separate from app.py so the mapping lives in one place -- if a label
changes, it changes everywhere at once.
"""

from __future__ import annotations

# Millonarios FC brand blue, plus a small accent set reused across every
# chart instead of Plotly's default rainbow palette.
PRIMARY_COLOR = "#0A3D91"
ACCENT_COLOR = "#5B9BD5"
WIN_COLOR = "#1E8E3E"
DRAW_COLOR = "#B08900"
LOSS_COLOR = "#C5221F"

RESULT_COLORS = {"W": WIN_COLOR, "D": DRAW_COLOR, "L": LOSS_COLOR}
RESULT_LABELS = {"W": "🟢 Ganó", "D": "🟡 Empató", "L": "🔴 Perdió"}
CONDITION_LABELS = {"Local": "🏠 Local", "Visitante": "✈️ Visitante"}

# API-Football's single-letter position codes, translated to Spanish. The
# underlying data (filtering, joins like position_averages) always keeps the
# raw code -- only display (tables, the sidebar filter) goes through
# position_label().
POSITION_LABELS = {"D": "Defensa", "F": "Delantero", "G": "Arquero", "M": "Mediocampista"}

# Raw column names should never leak into the UI as labels (a legend/axis
# reading "goles_favor" instead of "Goles a Favor"). RENAME maps the source
# column to its display name; COLORS is keyed by that *display* name so both
# can be used together: df.rename(columns=GOALS_FOR_AGAINST_RENAME) then
# color_discrete_map=GOALS_FOR_AGAINST_COLORS.
GOALS_FOR_LABEL = "Goles a Favor"
GOALS_AGAINST_LABEL = "Goles en Contra"
GOALS_FOR_AGAINST_RENAME = {"goles_favor": GOALS_FOR_LABEL, "goles_contra": GOALS_AGAINST_LABEL}
GOALS_FOR_AGAINST_COLORS = {GOALS_FOR_LABEL: PRIMARY_COLOR, GOALS_AGAINST_LABEL: LOSS_COLOR}

# Light-to-dark blue so the most recent year reads as the most prominent line
# in the year-over-year comparison chart; a 5th warm color as a safety net
# past 4 years so lines stay distinguishable.
YEAR_COLOR_SEQUENCE = ["#A9C6E8", "#5B9BD5", "#0A3D91", "#062754", "#F2A65A"]

# 1-indexed by calendar month (MES_ABBR[0] is January), used to label the
# points-race chart's x-axis alongside the jornada number.
MES_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def result_label(value: str) -> str:
    return RESULT_LABELS.get(value, value)


def condition_label(value: str) -> str:
    return CONDITION_LABELS.get(value, value)


def position_label(value: str) -> str:
    return POSITION_LABELS.get(value, value)
