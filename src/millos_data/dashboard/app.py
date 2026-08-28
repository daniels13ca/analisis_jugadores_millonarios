"""Streamlit dashboard: rendimiento de equipo y jugadores de Millonarios FC.

Run with:

    streamlit run src/millos_data/dashboard/app.py

or `python -m millos_data dashboard` (see cli.py), which also lets you point
at a different `analytics/` folder via --analytics-dir.

Data source: the tables written by `python -m millos_data build-analytics`
(see docs/analytics_kpis.md for what each column means). This file only
handles layout/widgets; every query goes through dashboard/data.py, and
every color/label goes through dashboard/formatting.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from millos_data.dashboard import data as dashboard_data
from millos_data.dashboard import formatting as fmt

DEFAULT_ANALYTICS_DIR = Path(__file__).resolve().parents[3] / "analytics"
ANALYTICS_DIR = Path(os.environ.get("MILLOS_ANALYTICS_DIR", str(DEFAULT_ANALYTICS_DIR)))

RANKING_METRICS = {
    "goles_por90": "Goles por 90'",
    "asistencias_por90": "Asistencias por 90'",
    "calificacion_promedio": "Calificación promedio",
    "minutos_totales": "Minutos totales",
    "duelos_ganados_pct": "% Duelos ganados",
    "pases_precision_promedio": "% Precisión de pase",
}

# Fractions (0-1) that need to be scaled to 0-100 before display -- unlike
# the special "percent" format keyword, a printf-style NumberColumn format
# like "%.0f%%" does not auto-multiply by 100, so a raw 0.65 would render as
# "0%" instead of "65%" if left unscaled.
PERCENT_COLUMNS = ["duelos_ganados_pct", "pases_precision_promedio"]

# column_config blocks reused across tables so the same raw column always
# gets the same header/format wherever it shows up.
RANKING_COLUMN_CONFIG = {
    "puesto": st.column_config.NumberColumn("#", format="%d"),
    "jugador": st.column_config.TextColumn("Jugador"),
    "anio": st.column_config.NumberColumn("Año", format="%d"),
    "posicion": st.column_config.TextColumn("Pos."),
    "partidos_jugados": st.column_config.NumberColumn("PJ", format="%d"),
    "titularidades": st.column_config.NumberColumn("Titular", format="%d"),
    "minutos_totales": st.column_config.NumberColumn("Minutos", format="%d"),
    "goles": st.column_config.NumberColumn("Goles", format="%d"),
    "asistencias": st.column_config.NumberColumn("Asist.", format="%d"),
    "goles_por90": st.column_config.NumberColumn("Goles/90'", format="%.2f"),
    "asistencias_por90": st.column_config.NumberColumn("Asist./90'", format="%.2f"),
    "calificacion_promedio": st.column_config.NumberColumn("Calif. prom.", format="%.2f"),
    "duelos_ganados_pct": st.column_config.NumberColumn("% Duelos", format="%.0f%%"),
    "pases_precision_promedio": st.column_config.NumberColumn("% Pases", format="%.0f%%"),
    "promedio_posicion": st.column_config.NumberColumn("Promedio posición", format="%.2f"),
    "vs_promedio_posicion": st.column_config.NumberColumn("vs. posición", format="%.2f"),
}


def _scale_percent_columns(df: pd.DataFrame) -> pd.DataFrame:
    """0-1 fractions -> 0-100, for columns displayed with a "%.0f%%" printf
    format (see PERCENT_COLUMNS). Safe to call on any dataframe; columns not
    present are skipped.
    """
    result = df.copy()
    for column in PERCENT_COLUMNS:
        if column in result.columns:
            result[column] = result[column] * 100
    return result


def _metric_scale(metric: str) -> float:
    """1, or 100 for a percent-type metric -- for scaling a *value in that
    metric's units* (not necessarily a column named `metric`, e.g.
    vs_promedio_posicion) before charting.
    """
    return 100 if metric in PERCENT_COLUMNS else 1


st.set_page_config(page_title="Millonarios FC: Rendimiento", layout="wide", page_icon="⚽")


def _inject_style() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        .stApp { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        .block-container { padding-top: 1.6rem; max-width: 1200px; }

        h1 {
            font-weight: 700 !important;
            letter-spacing: -0.02em;
        }
        h2 {
            font-weight: 700 !important;
            border-left: 4px solid var(--primary-color);
            padding-left: 0.65rem;
            margin-top: 1.4rem !important;
        }
        h3 { font-weight: 600 !important; text-align: center; }

        /* Pill-style tabs instead of the default underlined ones. */
        div[data-baseweb="tab-list"] {
            gap: 0.3rem;
            background-color: var(--secondary-background-color);
            padding: 0.3rem;
            border-radius: 999px;
            margin-bottom: 0.75rem;
        }
        button[data-baseweb="tab"] {
            border-radius: 999px !important;
            padding: 0.45rem 1.1rem !important;
        }
        button[data-baseweb="tab"] p { font-weight: 600; font-size: 0.92rem; }
        button[data-baseweb="tab"][aria-selected="true"] {
            background-color: var(--primary-color) !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] p { color: white !important; }
        div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] { display: none; }

        /* Stat cards: a row of simple cards, plus a wider "compound" card
           with nested mini-cards for win/draw/loss (see _wdl_card). */
        .stat-card-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin: 0.25rem 0 1.4rem 0;
        }
        .stat-card {
            flex: 1 1 130px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(10, 61, 145, 0.15);
            border-radius: 0.75rem;
            padding: 0.85rem 1rem;
        }
        .stat-value { display: block; font-size: 1.55rem; font-weight: 700; color: var(--primary-color); line-height: 1.15; }
        .stat-label { display: block; font-size: 0.68rem; font-weight: 600; text-transform: uppercase;
                       letter-spacing: 0.05em; opacity: 0.6; margin-top: 0.2rem; }

        .wdl-card { flex: 2 1 260px; padding: 0.7rem 0.85rem 0.85rem 0.85rem; }
        .wdl-card .stat-label { margin-bottom: 0.45rem; }
        .wdl-row { display: flex; gap: 0.5rem; width: 100%; }
        .wdl-item { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
                    text-align: center; border-radius: 0.55rem; padding: 0.4rem 0.25rem; }
        .wdl-value { display: block; font-size: 1.3rem; font-weight: 700; }
        .wdl-sub { display: block; font-size: 0.62rem; font-weight: 600; text-transform: uppercase;
                   letter-spacing: 0.03em; opacity: 0.8; margin-top: 0.1rem; }
        .wdl-win { background-color: rgba(30, 142, 62, 0.14); color: #1E8E3E; }
        .wdl-draw { background-color: rgba(176, 137, 0, 0.14); color: #B08900; }
        .wdl-loss { background-color: rgba(197, 34, 31, 0.14); color: #C5221F; }

        /* Fallback for the remaining native st.metric cards (Ficha de jugador). */
        div[data-testid="stMetric"] {
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(10, 61, 145, 0.15);
            border-radius: 0.6rem;
            padding: 0.9rem 1rem 0.6rem 1rem;
        }
        div[data-testid="stMetricLabel"] { font-weight: 600; }

        .stDownloadButton button, .stButton button {
            border-radius: 0.5rem;
            border: 1px solid var(--primary-color);
            color: var(--primary-color);
            font-weight: 600;
        }
        .stDownloadButton button:hover, .stButton button:hover {
            background-color: var(--primary-color);
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _stat_card_row(cards: list[dict]) -> None:
    """Render a row of simple `.stat-card` divs. Each card: label, value, icon (optional)."""
    parts = ['<div class="stat-card-row">']
    for card in cards:
        icon = f"{card['icon']} " if card.get("icon") else ""
        parts.append(
            f'<div class="stat-card"><span class="stat-value">{icon}{card["value"]}</span>'
            f'<span class="stat-label">{card["label"]}</span></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _stat_card_row_with_wdl(cards: list[dict], victorias: int, empates: int, derrotas: int) -> None:
    """Like _stat_card_row, but leads with a compound card with 3 nested W/D/L mini-cards.

    A single "12 / 8 / 5" metric label is hard to scan; nesting a nicely
    colored mini-card per outcome inside one wider card reads at a glance
    and matches the win/draw/loss color coding used everywhere else in the
    dashboard (see formatting.RESULT_COLORS). It leads the row since it's
    the compound/most-important card.
    """
    parts = [
        '<div class="stat-card-row">'
        '<div class="stat-card wdl-card"><span class="stat-label">Resultados</span>'
        '<div class="wdl-row">'
        f'<div class="wdl-item wdl-win"><span class="wdl-value">{victorias}</span>'
        '<span class="wdl-sub">Ganados</span></div>'
        f'<div class="wdl-item wdl-draw"><span class="wdl-value">{empates}</span>'
        '<span class="wdl-sub">Empatados</span></div>'
        f'<div class="wdl-item wdl-loss"><span class="wdl-value">{derrotas}</span>'
        '<span class="wdl-sub">Perdidos</span></div>'
        "</div></div>"
    ]
    for card in cards:
        icon = f"{card['icon']} " if card.get("icon") else ""
        parts.append(
            f'<div class="stat-card"><span class="stat-value">{icon}{card["value"]}</span>'
            f'<span class="stat-label">{card["label"]}</span></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


@st.cache_resource
def _connection(analytics_dir: str):
    return dashboard_data.get_connection(Path(analytics_dir))


def _render_chart(fig: go.Figure) -> None:
    """st.plotly_chart with the title centered -- Plotly left-aligns titles
    by default, which read as off-balance next to the rest of the (centered)
    UI.
    """
    fig.update_layout(title_x=0.5, title_xanchor="center")
    st.plotly_chart(fig, width="stretch")


@dataclass
class Filters:
    """Every filter selection from the sidebar, threaded down into each tab.

    Widgets live in the sidebar (one shared place, visible no matter which
    tab is open) instead of scattered across tabs. Campeonato/condicion are
    shared by the Equipo and Partidos tabs since they mean the same thing in
    both; the rest are specific to a single tab, tagged in their sidebar
    label to say so.
    """

    anios: list[int] | None
    campeonatos: list[str] | None
    condiciones: list[str] | None
    resultados: list[str] | None
    posiciones: list[str] | None
    jugador_ficha: str | None
    jugadores_comparador: list[str]
    goles_anio: int | None


def _render_sidebar(con) -> Filters:
    """Sidebar: a title, the two dataset-freshness dates, and every filter
    control -- grouped as team/match filters (which apply to Equipo and
    Partidos) then, past a divider, player filters (Ranking, Ficha,
    Comparador). No other text.
    """
    with st.sidebar:
        st.header("Análisis de rendimiento: Millonarios FC")

        last_updated = dashboard_data.dataset_last_updated(ANALYTICS_DIR)
        if last_updated is not None:
            st.caption(f"Última actualización: {datetime.fromtimestamp(last_updated):%Y-%m-%d %H:%M}")
        latest_match = dashboard_data.latest_match_date(con)
        if latest_match:
            st.caption(f"Fecha del último partido: {latest_match}")

        # --- Equipo / Partidos ---
        anios_disponibles = dashboard_data.list_match_years(con)
        if not anios_disponibles:
            anios = None
        elif len(anios_disponibles) == 1:
            anios = anios_disponibles
        else:
            anio_min, anio_max = min(anios_disponibles), max(anios_disponibles)
            anio_inicio, anio_fin = st.slider(
                "Rango de años",
                min_value=anio_min,
                max_value=anio_max,
                value=(anio_min, anio_max),
            )
            anios = list(range(anio_inicio, anio_fin + 1))

        campeonatos = dashboard_data.list_campeonatos(con)
        selected_campeonatos = st.multiselect("Campeonato", campeonatos, default=campeonatos)

        condiciones = dashboard_data.list_condiciones(con)
        selected_condiciones = st.multiselect("Condición", condiciones, default=condiciones)

        selected_resultados = st.multiselect(
            "Resultado (Partidos)",
            ["W", "D", "L"],
            default=["W", "D", "L"],
            format_func=fmt.result_label,
        )

        goles_anio = st.selectbox("Año (Gráfico de goles)", anios, index=len(anios) - 1) if anios else None

        st.divider()

        # --- Ranking / Ficha de jugador / Comparador ---
        posiciones = dashboard_data.list_posiciones(con)
        selected_posiciones = st.multiselect(
            "Posición (Ranking)", posiciones, default=posiciones, format_func=fmt.position_label
        )

        jugadores = dashboard_data.list_jugadores(con)
        jugador_ficha = st.selectbox("Jugador (Ficha)", jugadores) if jugadores else None
        jugadores_comparador = st.multiselect("Jugadores (Comparador)", jugadores)

        return Filters(
            anios=anios,
            campeonatos=selected_campeonatos or None,
            condiciones=selected_condiciones or None,
            resultados=selected_resultados or None,
            posiciones=selected_posiciones or None,
            jugador_ficha=jugador_ficha,
            jugadores_comparador=jugadores_comparador,
            goles_anio=goles_anio,
        )


def main() -> None:
    _inject_style()
    st.title("⚽ Millonarios FC: Rendimiento")

    if not (ANALYTICS_DIR / "match_results.csv").exists():
        st.error(
            f"No se encontraron las tablas de analítica en `{ANALYTICS_DIR}`. "
            "Corre `python -m millos_data build-analytics` primero."
        )
        st.stop()

    con = _connection(str(ANALYTICS_DIR))
    filters = _render_sidebar(con)

    tab_equipo, tab_partidos, tab_ranking, tab_jugador, tab_comparador = st.tabs(
        ["📊 Equipo", "📋 Partidos", "🏆 Ranking de jugadores", "🔎 Ficha de jugador", "⚖️ Comparador"]
    )

    with tab_equipo:
        _render_team_tab(con, filters)
    with tab_partidos:
        _render_matches_tab(con, filters)
    with tab_ranking:
        _render_ranking_tab(con, filters)
    with tab_jugador:
        _render_player_profile_tab(con, filters)
    with tab_comparador:
        _render_comparator_tab(con, filters)


FORM_ROLLING_WINDOW = 10


def _form_chart(resultados: pd.DataFrame) -> go.Figure:
    """Forma reciente (rolling average, 10-game window) as a single smoothed
    line, with each match's actual result colored on its marker.

    A bar per match (one earlier version of this chart) turns into a
    dense, hard-to-read blur once there are ~200 matches spanning several
    years -- there just isn't enough horizontal room per bar. A wider
    rolling window (10 games instead of 5) plus a single line keeps the
    trend readable at this density; the colored markers keep a hint of
    each match's actual result without reintroducing the clutter.
    """
    colors = resultados["resultado_partido"].map(fmt.RESULT_COLORS).fillna("#9AA5B1")
    hover_customdata = resultados[["rival", "resultado"]].to_numpy()

    fig = go.Figure()
    fig.add_scatter(
        x=resultados["fecha"],
        y=resultados["forma_reciente"],
        mode="lines+markers",
        name="Forma reciente",
        line=dict(color=fmt.PRIMARY_COLOR, width=3),
        marker=dict(color=colors, size=7, line=dict(width=1, color="white")),
        fill="tozeroy",
        fillcolor="rgba(10, 61, 145, 0.08)",
        customdata=hover_customdata,
        hovertemplate="%{x}<br>vs %{customdata[0]} (%{customdata[1]})<br>Forma: %{y:.2f}<extra></extra>",
    )
    fig.update_layout(
        title=f"Forma reciente (Promedio móvil, últimos {FORM_ROLLING_WINDOW} partidos)",
        yaxis_title="Puntos promedio",
        xaxis_title="",
        yaxis=dict(range=[0, 3.2]),
        showlegend=False,
        margin=dict(t=60),
    )
    return fig


def _points_race_chart(race: pd.DataFrame, calendar_labels: pd.DataFrame) -> go.Figure:
    """Cumulative points per year (see points_race_by_year), with the x-axis
    labeled by month (not jornada -- one tick per jornada was too cramped
    with up to ~77 of them), and a dashed divider marking the 30-jun
    boundary between first/second half of the year.
    """
    race = race.astype({"anio": str})
    fig = px.line(
        race,
        x="jornada",
        y="puntos_acumulados",
        color="anio",
        markers=True,
        title="Puntos acumulados por año (Comparación de ritmo)",
        labels={"jornada": "Jornada", "puntos_acumulados": "Puntos acumulados", "anio": "Año"},
        color_discrete_sequence=fmt.YEAR_COLOR_SEQUENCE,
    )
    fig.update_layout(legend_title_text="Año")

    if not calendar_labels.empty:
        calendar_labels = calendar_labels.sort_values("jornada")
        # One tick per jornada was too cramped to read; collapse consecutive
        # jornadas that share the same typical month into a single tick, at
        # the jornada where that month starts, labeled with only the month.
        month_starts = calendar_labels[calendar_labels["mes"] != calendar_labels["mes"].shift(1)]
        tickvals = month_starts["jornada"].tolist()
        ticktext = [fmt.MES_ABBR[mes - 1] for mes in month_starts["mes"]]
        fig.update_xaxes(tickvals=tickvals, ticktext=ticktext)

        primer_semestre = calendar_labels[calendar_labels["mes"] <= 6]
        if not primer_semestre.empty and len(primer_semestre) < len(calendar_labels):
            divider_x = primer_semestre["jornada"].max() + 0.5
            fig.add_vline(
                x=divider_x,
                line_dash="dash",
                line_color="rgba(0, 0, 0, 0.35)",
                annotation_text="30 jun",
                annotation_position="top",
            )

    return fig


def _render_team_tab(con, filters: Filters) -> None:
    st.header("Resumen de equipo")

    resultados = dashboard_data.match_results_with_form(
        con,
        campeonatos=filters.campeonatos,
        condiciones=filters.condiciones,
        anios=filters.anios,
        rolling_window=FORM_ROLLING_WINDOW,
    )

    if resultados.empty:
        st.info("No hay partidos para los filtros seleccionados.")
        return

    victorias = int((resultados["resultado_partido"] == "W").sum())
    empates = int((resultados["resultado_partido"] == "D").sum())
    derrotas = int((resultados["resultado_partido"] == "L").sum())

    _stat_card_row_with_wdl(
        [
            {"label": "Partidos", "value": len(resultados)},
            {"label": "Puntos", "value": int(resultados["puntos"].fillna(0).sum())},
            {"label": "Goles a favor", "value": int(resultados["goles_favor"].fillna(0).sum())},
            {"label": "Goles en contra", "value": int(resultados["goles_contra"].fillna(0).sum())},
        ],
        victorias=victorias,
        empates=empates,
        derrotas=derrotas,
    )

    _render_chart(_form_chart(resultados))

    race = dashboard_data.points_race_by_year(con, campeonatos=filters.campeonatos, anios=filters.anios)
    if race["anio"].nunique() > 1:
        calendar_labels = dashboard_data.jornada_calendar_labels(
            con, campeonatos=filters.campeonatos, anios=filters.anios
        )
        _render_chart(_points_race_chart(race, calendar_labels))
    else:
        st.caption(
            "La comparación de ritmo por año aparece cuando hay partidos de más de un año "
            "en los filtros seleccionados."
        )

    if filters.goles_anio is not None:
        goles_df = resultados[
            pd.to_datetime(resultados["fecha"], errors="coerce").dt.year == filters.goles_anio
        ]
        goles_titulo = f"Goles a favor / En contra por partido: {filters.goles_anio}"
    else:
        goles_df = resultados
        goles_titulo = "Goles a favor / En contra por partido"

    goles_df = goles_df.rename(columns=fmt.GOALS_FOR_AGAINST_RENAME)
    _render_chart(
        px.bar(
            goles_df,
            x="fecha",
            y=list(fmt.GOALS_FOR_AGAINST_RENAME.values()),
            barmode="stack",
            title=goles_titulo,
            color_discrete_map=fmt.GOALS_FOR_AGAINST_COLORS,
            labels={"value": "Goles", "variable": "", "fecha": "Fecha"},
        )
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Por condición")
        por_condicion = dashboard_data.team_summary(
            con, group_by="condicion", campeonatos=filters.campeonatos, anios=filters.anios
        )
        st.dataframe(
            por_condicion.assign(condicion=por_condicion["condicion"].map(fmt.condition_label)),
            width="stretch",
            hide_index=True,
            column_config=_team_summary_column_config("condicion", "Condición"),
        )
    with col2:
        st.subheader("Por campeonato")
        por_campeonato = dashboard_data.team_summary(con, group_by="campeonato", anios=filters.anios)
        st.dataframe(
            por_campeonato,
            width="stretch",
            hide_index=True,
            column_config=_team_summary_column_config("campeonato", "Campeonato"),
        )


def _team_summary_column_config(group_column: str, group_label: str) -> dict:
    return {
        group_column: st.column_config.TextColumn(group_label),
        "partidos": st.column_config.NumberColumn("PJ", format="%d"),
        "victorias": st.column_config.NumberColumn("🟢 G", format="%d"),
        "empates": st.column_config.NumberColumn("🟡 E", format="%d"),
        "derrotas": st.column_config.NumberColumn("🔴 P", format="%d"),
        "puntos_promedio": st.column_config.NumberColumn("Puntos/Partido", format="%.2f"),
        "goles_favor_promedio": st.column_config.NumberColumn("GF/Partido", format="%.2f"),
        "goles_contra_promedio": st.column_config.NumberColumn("GC/Partido", format="%.2f"),
    }


PITCH_LENGTH = 100
PITCH_WIDTH = 64
# x-position (own goal at 0, opponent goal at PITCH_LENGTH) for each position
# line. We only know the broad role (G/D/M/F), not real on-pitch coordinates
# or the actual tactical formation, so this draws an approximate "shape" --
# one horizontal line per role, evenly spread -- not a precise formation.
POSITION_ROW_X = {"G": 6, "D": 26, "M": 56, "F": 86}
POSITION_ROW_ORDER = ["G", "D", "M", "F"]


def _spread_along_width(count: int, low: float = 6, high: float = PITCH_WIDTH - 6) -> list[float]:
    """`count` evenly spaced y-positions between low and high (a single value
    centered if count == 1)."""
    if count <= 0:
        return []
    if count == 1:
        return [(low + high) / 2]
    step = (high - low) / (count - 1)
    return [low + i * step for i in range(count)]


def _lineup_pitch_positions(titulares: pd.DataFrame) -> pd.DataFrame:
    """Assign an approximate (pitch_x, pitch_y) to each starter, grouped into
    one row per position (arquero/defensa/mediocampista/delantero) and
    spread evenly across the pitch width within that row.
    """
    rows: list[pd.DataFrame] = []
    grouped = {code: group for code, group in titulares.groupby("posicion", sort=False)}
    ordered_codes = POSITION_ROW_ORDER + [c for c in grouped if c not in POSITION_ROW_ORDER]

    for codigo in ordered_codes:
        group = grouped.get(codigo)
        if group is None or group.empty:
            continue
        ys = _spread_along_width(len(group))
        x = POSITION_ROW_X.get(codigo, PITCH_LENGTH / 2)
        rows.append(group.assign(pitch_x=x, pitch_y=ys))

    if not rows:
        return titulares.assign(pitch_x=pd.Series(dtype=float), pitch_y=pd.Series(dtype=float))
    return pd.concat(rows, ignore_index=True)


def _pitch_hover_text(row: pd.Series) -> str:
    calificacion = f"{row['calificacion']:.1f}" if pd.notna(row["calificacion"]) else "s/d"
    minutos = int(row["minutos"]) if pd.notna(row["minutos"]) else 0
    goles = int(row["goles"]) if pd.notna(row["goles"]) else 0
    asistencias = int(row["asistencias"]) if pd.notna(row["asistencias"]) else 0
    return (
        f"<b>{row['jugador']}</b><br>{fmt.position_label(row['posicion'])}<br>"
        f"Minutos: {minutos}<br>Calificación: {calificacion}<br>"
        f"Goles: {goles} · Asistencias: {asistencias}"
    )


def _pitch_chart(titulares: pd.DataFrame) -> go.Figure:
    """Starting-lineup diagram: one marker per starter, arranged by position
    line on an approximate pitch (see POSITION_ROW_X -- not a real tactical
    formation, since the data only has broad position codes).
    """
    positions = _lineup_pitch_positions(titulares)

    fig = go.Figure()

    # Pitch outline and markings.
    half_length, half_width = PITCH_LENGTH / 2, PITCH_WIDTH / 2
    fig.add_shape(
        type="rect", x0=0, y0=0, x1=PITCH_LENGTH, y1=PITCH_WIDTH,
        line=dict(color=fmt.PITCH_LINE_COLOR, width=2), fillcolor=fmt.PITCH_GREEN, layer="below",
    )
    fig.add_shape(
        type="line", x0=half_length, y0=0, x1=half_length, y1=PITCH_WIDTH,
        line=dict(color=fmt.PITCH_LINE_COLOR, width=2),
    )
    fig.add_shape(
        type="circle", x0=half_length - 9, y0=half_width - 9, x1=half_length + 9, y1=half_width + 9,
        line=dict(color=fmt.PITCH_LINE_COLOR, width=2),
    )
    for x0, x1 in [(0, 16), (PITCH_LENGTH - 16, PITCH_LENGTH)]:
        fig.add_shape(
            type="rect", x0=x0, y0=half_width - 20, x1=x1, y1=half_width + 20,
            line=dict(color=fmt.PITCH_LINE_COLOR, width=2),
        )
    for x0, x1 in [(0, 6), (PITCH_LENGTH - 6, PITCH_LENGTH)]:
        fig.add_shape(
            type="rect", x0=x0, y0=half_width - 9, x1=x1, y1=half_width + 9,
            line=dict(color=fmt.PITCH_LINE_COLOR, width=2),
        )

    if not positions.empty:
        fig.add_scatter(
            x=positions["pitch_x"],
            y=positions["pitch_y"],
            mode="markers+text",
            text=positions["jugador"],
            textposition="bottom center",
            textfont=dict(color="white", size=11),
            marker=dict(size=30, color=fmt.PRIMARY_COLOR, line=dict(color="white", width=2)),
            hovertext=positions.apply(_pitch_hover_text, axis=1),
            hoverinfo="text",
            showlegend=False,
        )

    fig.update_xaxes(range=[-4, PITCH_LENGTH + 4], visible=False, fixedrange=True)
    fig.update_yaxes(
        range=[-8, PITCH_WIDTH + 8], visible=False, fixedrange=True,
        scaleanchor="x", scaleratio=1,
    )
    fig.update_layout(
        title="Alineación titular",
        plot_bgcolor=fmt.PITCH_GREEN,
        paper_bgcolor="rgba(0, 0, 0, 0)",
        margin=dict(l=10, r=10, t=50, b=10),
        height=440,
    )
    return fig


def _render_matches_tab(con, filters: Filters) -> None:
    st.header("Detalle de partidos")
    st.caption("Selecciona una fila en el histórico para ver su planilla individual abajo.")

    partidos = dashboard_data.matches_filtered(
        con,
        campeonatos=filters.campeonatos,
        condiciones=filters.condiciones,
        resultados=filters.resultados,
        anios=filters.anios,
    )

    if partidos.empty:
        st.info("No hay partidos para los filtros seleccionados.")
        return

    display = partidos.assign(
        condicion=partidos["condicion"].map(fmt.condition_label),
        resultado_partido=partidos["resultado_partido"].map(fmt.result_label),
    )[["fecha", "rival", "condicion", "resultado", "resultado_partido", "campeonato", "puntos"]]

    st.subheader("Histórico de Partidos")
    tabla_partidos = st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "rival": st.column_config.TextColumn("Rival"),
            "condicion": st.column_config.TextColumn("Condición"),
            "resultado": st.column_config.TextColumn("Marcador"),
            "resultado_partido": st.column_config.TextColumn("Resultado"),
            "campeonato": st.column_config.TextColumn("Campeonato"),
            "puntos": st.column_config.NumberColumn("Puntos", format="%d"),
        },
        on_select="rerun",
        selection_mode="single-row",
        key="partidos_historico",
    )
    st.caption(f"{len(partidos)} partido(s)")

    sin_datos = int((~partidos["tiene_datos_jugadores"]).sum())
    if sin_datos:
        st.caption(f"ℹ️ {sin_datos} de estos partidos no tienen planilla de jugadores registrada.")

    st.divider()
    st.subheader("Planilla individual de partido")

    con_datos = partidos[partidos["tiene_datos_jugadores"]]
    if con_datos.empty:
        st.info("Ninguno de los partidos filtrados tiene planilla de jugadores.")
        return

    selected_rows = tabla_partidos.selection.rows if tabla_partidos.selection else []
    if selected_rows:
        seleccionado = partidos.iloc[selected_rows[0]]
        if not seleccionado["tiene_datos_jugadores"]:
            st.info("El partido seleccionado no tiene planilla de jugadores registrada.")
            return
        match_id = seleccionado["match_id"]
    else:
        # Nothing clicked yet: default to the most recent match with a lineup.
        st.caption("Mostrando el partido más reciente. Selecciona otra fila arriba para cambiarlo.")
        match_id = con_datos.iloc[0]["match_id"]

    lineup = dashboard_data.match_lineup(con, match_id)
    if lineup.empty:
        st.info("No hay datos de jugadores para este partido.")
        return

    titulares = lineup[lineup["titular"]]
    if titulares.empty:
        st.info("No hay titulares registrados para este partido.")
    else:
        _render_chart(_pitch_chart(titulares))
        st.caption(
            "Formación aproximada por línea de posición (arquero, defensa, mediocampo, "
            "delantera): La API no expone la posición exacta en cancha ni el esquema táctico."
        )

    st.dataframe(
        lineup.assign(posicion=lineup["posicion"].map(fmt.position_label)),
        width="stretch",
        hide_index=True,
        column_config={
            "jugador": st.column_config.TextColumn("Jugador"),
            "posicion": st.column_config.TextColumn("Pos."),
            "titular": st.column_config.CheckboxColumn("Titular"),
            "minutos": st.column_config.NumberColumn("Min.", format="%d"),
            "calificacion": st.column_config.NumberColumn("Calif.", format="%.1f"),
            "goles": st.column_config.NumberColumn("Goles", format="%d"),
            "asistencias": st.column_config.NumberColumn("Asist.", format="%d"),
            "remates_totales": st.column_config.NumberColumn("Remates", format="%d"),
            "remates_al_arco": st.column_config.NumberColumn("Al arco", format="%d"),
            "pases_totales": st.column_config.NumberColumn("Pases", format="%d"),
            "pases_precision": st.column_config.TextColumn("% Precisión"),
            "entradas": st.column_config.NumberColumn("Entradas", format="%d"),
            "intercepciones": st.column_config.NumberColumn("Intercep.", format="%d"),
            "despejes": st.column_config.NumberColumn("Despejes", format="%d"),
            "duelos_totales": st.column_config.NumberColumn("Duelos", format="%d"),
            "duelos_ganados": st.column_config.NumberColumn("Duelos ganados", format="%d"),
            "faltas_cometidas": st.column_config.NumberColumn("Faltas cometidas", format="%d"),
            "faltas_recibidas": st.column_config.NumberColumn("Faltas recibidas", format="%d"),
            "amarillas": st.column_config.NumberColumn("🟨", format="%d"),
            "rojas": st.column_config.NumberColumn("🟥", format="%d"),
        },
    )


MEDALS = ["🥇", "🥈", "🥉"]

# Minimum partidos_jugados to appear in the "vs. promedio de posición" chart
# -- below this, a single big/bad game can dominate a per-90 rate and make
# the comparison meaningless.
MIN_MATCHES_FOR_VS_AVG_CHART = 3


def _format_metric_value(metric: str, value: float) -> str:
    if pd.isna(value):
        return "s/d"
    if metric in PERCENT_COLUMNS:
        return f"{value * 100:.0f}%"
    if metric == "minutos_totales":
        return f"{int(value)}"
    return f"{value:.2f}"


def _format_metric_delta(metric: str, value: float) -> str:
    """Like _format_metric_value, but with an explicit "+" sign for
    non-negative values -- used for "jugador vs. promedio" differences,
    where the sign is the whole point.
    """
    if pd.isna(value):
        return "s/d"
    sign = "+" if value >= 0 else ""
    return f"{sign}{_format_metric_value(metric, value)}"


def _render_podium(top: pd.DataFrame, metric: str) -> None:
    """Top-3 cards for the selected metric, medal-style -- a quick highlight
    before the full table, reusing the same card component as Equipo.

    Always shows partidos_jugados alongside the metric: a single standout
    match can otherwise look like a full-season leader (e.g. 4+ goles_por90
    from one great game), which is misleading without that context.
    """
    podio = [
        {
            "icon": medalla,
            "value": _format_metric_value(metric, row[metric]),
            "label": f"{row['jugador']} ({int(row['anio'])}) · {int(row['partidos_jugados'])} PJ",
        }
        for medalla, (_, row) in zip(MEDALS, top.head(3).iterrows())
    ]
    if podio:
        _stat_card_row(podio)


def _render_ranking_tab(con, filters: Filters) -> None:
    st.header("Ranking de jugadores")

    metric = st.selectbox("Ordenar / Graficar por", list(RANKING_METRICS), format_func=RANKING_METRICS.get)

    summary = dashboard_data.player_season_summary_filtered(
        con,
        anios=filters.anios,
        posiciones=filters.posiciones,
    )

    if summary.empty:
        st.info("No hay jugadores para los filtros seleccionados.")
        return

    # Benchmark against the position average for the chosen metric, not the
    # whole squad -- a center-back and a forward shouldn't share a
    # goles_por90 scale. Averages use the same (global) anio filter as the
    # table.
    pos_avg = dashboard_data.position_averages(con, anios=filters.anios)
    if metric in pos_avg.columns:
        avg_by_posicion = pos_avg.set_index("posicion")[metric]
        summary = summary.assign(
            promedio_posicion=summary["posicion"].map(avg_by_posicion),
        )
        summary["vs_promedio_posicion"] = summary[metric] - summary["promedio_posicion"]

    summary_sorted = summary.sort_values(metric, ascending=False, na_position="last")
    top = summary_sorted.dropna(subset=[metric]).head(15)
    if not top.empty:
        top = top.assign(jugador_anio=top["jugador"] + " (" + top["anio"].astype(str) + ")")

    _render_podium(top, metric)

    summary_display = summary_sorted.assign(
        posicion=summary_sorted["posicion"].map(fmt.position_label),
        puesto=range(1, len(summary_sorted) + 1),
    )
    summary_display = _scale_percent_columns(summary_display)
    summary_display = summary_display[["puesto"] + [c for c in summary_display.columns if c != "puesto"]]
    st.dataframe(
        summary_display,
        width="stretch",
        hide_index=True,
        column_config=RANKING_COLUMN_CONFIG,
    )
    st.download_button(
        "⬇️ Descargar tabla (CSV)",
        data=summary_display.to_csv(index=False).encode("utf-8-sig"),
        file_name="ranking_jugadores.csv",
        mime="text/csv",
    )

    with st.expander("Promedio por posición (Todas las métricas)"):
        pos_avg_display = pos_avg.assign(posicion=pos_avg["posicion"].map(fmt.position_label))
        pos_avg_display = _scale_percent_columns(pos_avg_display)
        st.dataframe(
            pos_avg_display,
            width="stretch",
            hide_index=True,
            column_config={**RANKING_COLUMN_CONFIG, "posicion": st.column_config.TextColumn("Posición")},
        )

    if not top.empty:
        scale = _metric_scale(metric)
        top_chart = top.assign(**{metric: top[metric] * scale}) if scale != 1 else top
        _render_chart(
            px.bar(
                top_chart,
                x="jugador_anio",
                y=metric,
                title=f"Top 15: {RANKING_METRICS[metric]}",
                color_discrete_sequence=[fmt.PRIMARY_COLOR],
                labels={"jugador_anio": "", metric: RANKING_METRICS[metric]},
            )
        )

        top_vs_avg = top.dropna(subset=["vs_promedio_posicion"]) if "vs_promedio_posicion" in top.columns else top.iloc[0:0]
        # A player with 1-2 matches can look like a standout (or a disaster)
        # purely from a small sample; require a minimum before comparing
        # them against their position's average.
        top_vs_avg = top_vs_avg[top_vs_avg["partidos_jugados"] >= MIN_MATCHES_FOR_VS_AVG_CHART]
        if not top_vs_avg.empty:
            vs_avg_values = top_vs_avg["vs_promedio_posicion"] * scale
            colors = vs_avg_values.apply(lambda v: fmt.WIN_COLOR if v >= 0 else fmt.LOSS_COLOR)
            vs_avg_fig = go.Figure()
            vs_avg_fig.add_bar(
                x=top_vs_avg["jugador_anio"],
                y=vs_avg_values,
                marker_color=colors,
            )
            vs_avg_fig.update_layout(
                title=f"{RANKING_METRICS[metric]}: Por encima o por debajo del promedio de su posición",
                yaxis_title="Diferencia vs. promedio",
                xaxis_title="",
                showlegend=False,
            )
            _render_chart(vs_avg_fig)
            st.caption(
                f"Solo incluye jugadores con {MIN_MATCHES_FOR_VS_AVG_CHART} o más partidos jugados "
                "en el año seleccionado, para no comparar contra el promedio a alguien con una "
                "muestra muy chica."
            )


PLAYER_FORM_ROLLING_WINDOW = 5

# Rate metrics compared against the position average on the player's own
# profile -- minutos_totales is deliberately left out here (it already has
# its own stat card, and "minutes vs. position average" isn't a performance
# comparison the way the others are).
PLAYER_COMPARISON_METRICS = [
    "goles_por90",
    "asistencias_por90",
    "calificacion_promedio",
    "duelos_ganados_pct",
    "pases_precision_promedio",
]


def _player_form_chart(jugados: pd.DataFrame) -> go.Figure:
    """Calificación per match (marker size = minutos, color = resultado del
    equipo) with a rolling-average line -- one chart instead of two
    unrelated ones, same visual language as Equipo's forma reciente chart.
    """
    jugados = jugados.sort_values("fecha").reset_index(drop=True)
    rolling = jugados["calificacion"].rolling(window=PLAYER_FORM_ROLLING_WINDOW, min_periods=1).mean()
    colors = jugados["resultado_partido"].map(fmt.RESULT_COLORS).fillna("#9AA5B1")
    sizes = 7 + (jugados["minutos"].clip(lower=0, upper=120) / 120) * 18

    def _hover(row: pd.Series) -> str:
        calificacion = f"{row['calificacion']:.1f}" if pd.notna(row["calificacion"]) else "s/d"
        return (
            f"<b>{row['fecha']}</b> vs {row['rival']} ({fmt.condition_label(row['condicion'])})<br>"
            f"Marcador: {row['resultado']}<br>Minutos: {int(row['minutos'])}<br>"
            f"Calificación: {calificacion}"
        )

    fig = go.Figure()
    fig.add_scatter(
        x=jugados["fecha"],
        y=rolling,
        mode="lines",
        name="Forma reciente",
        line=dict(color=fmt.PRIMARY_COLOR, width=2),
        hoverinfo="skip",
    )
    fig.add_scatter(
        x=jugados["fecha"],
        y=jugados["calificacion"],
        mode="markers",
        name="Calificación por partido",
        marker=dict(size=sizes, color=colors, line=dict(width=1, color="white")),
        hovertext=jugados.apply(_hover, axis=1),
        hoverinfo="text",
    )
    fig.update_layout(
        title=f"Forma (Promedio móvil de {PLAYER_FORM_ROLLING_WINDOW} partidos)",
        yaxis_title="Calificación",
        xaxis_title="",
        showlegend=False,
    )
    return fig


def _render_player_comparison_table(con, jugados: pd.DataFrame, anios: list[int] | None) -> None:
    """Jugador vs. promedio de su posición, one row per headline metric --
    a table instead of a chart since the metrics have very different scales
    (goles/90 ~0-1, calificación ~0-10, % ~0-100) and wouldn't share a
    readable axis.
    """
    posicion_moda = jugados["posicion"].mode()
    if posicion_moda.empty:
        return
    posicion = posicion_moda.iat[0]

    pos_avg = dashboard_data.position_averages(con, anios=anios)
    avg_row = pos_avg[pos_avg["posicion"] == posicion]

    minutos_totales = jugados["minutos"].sum()
    duelos_totales = jugados["duelos_totales"].sum()
    player_values = {
        "goles_por90": jugados["goles"].sum() / minutos_totales * 90 if minutos_totales else float("nan"),
        "asistencias_por90": jugados["asistencias"].sum() / minutos_totales * 90 if minutos_totales else float("nan"),
        "calificacion_promedio": jugados["calificacion"].mean(),
        "duelos_ganados_pct": jugados["duelos_ganados"].sum() / duelos_totales if duelos_totales else float("nan"),
        "pases_precision_promedio": jugados["pases_precision_num"].mean(),
    }

    rows = []
    for metric in PLAYER_COMPARISON_METRICS:
        jugador_valor = player_values[metric]
        promedio_valor = avg_row.iloc[0][metric] if not avg_row.empty and metric in avg_row.columns else float("nan")
        diferencia = (
            jugador_valor - promedio_valor if pd.notna(jugador_valor) and pd.notna(promedio_valor) else float("nan")
        )
        rows.append(
            {
                "Métrica": RANKING_METRICS[metric],
                "Jugador": _format_metric_value(metric, jugador_valor),
                f"Promedio {fmt.position_label(posicion)}": _format_metric_value(metric, promedio_valor),
                "Diferencia": _format_metric_delta(metric, diferencia),
            }
        )

    st.subheader("Comparación con el promedio de su posición")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _render_player_season_table(con, jugador: str, anios: list[int] | None) -> None:
    resumen = dashboard_data.player_season_summary_filtered(con, jugadores=[jugador], anios=anios)
    if resumen.empty:
        return
    resumen_display = resumen.assign(posicion=resumen["posicion"].map(fmt.position_label))
    resumen_display = _scale_percent_columns(resumen_display)

    st.subheader("Resumen por temporada")
    st.dataframe(
        resumen_display.sort_values("anio"),
        width="stretch",
        hide_index=True,
        column_config=RANKING_COLUMN_CONFIG,
    )


def _render_player_profile_tab(con, filters: Filters) -> None:
    st.header("Ficha de jugador")

    if filters.jugador_ficha is None:
        st.info("No hay jugadores disponibles.")
        return

    historial = dashboard_data.player_match_history(con, filters.jugador_ficha, anios=filters.anios)
    jugados = historial[historial["jugo"].fillna(False)]

    if jugados.empty:
        st.info(f"{filters.jugador_ficha} no registra minutos jugados en los datos disponibles.")
        return

    posicion_moda = jugados["posicion"].mode()
    posicion_label = fmt.position_label(posicion_moda.iat[0]) if not posicion_moda.empty else "s/d"
    st.subheader(f"{filters.jugador_ficha} · {posicion_label}")

    calificacion_promedio = jugados["calificacion"].mean()
    _stat_card_row(
        [
            {"label": "Partidos jugados", "value": len(jugados)},
            {"label": "Minutos totales", "value": int(jugados["minutos"].sum())},
            {
                "label": "Calificación promedio",
                "value": f"{calificacion_promedio:.2f}" if pd.notna(calificacion_promedio) else "s/d",
            },
            {"label": "Goles", "value": int(jugados["goles"].sum())},
            {"label": "Asistencias", "value": int(jugados["asistencias"].sum())},
            {
                "label": "Tarjetas",
                "value": f"🟨 {int(jugados['amarillas'].sum())} · 🟥 {int(jugados['rojas'].sum())}",
            },
        ]
    )

    _render_chart(_player_form_chart(jugados))
    st.caption(
        "El tamaño de cada punto es proporcional a los minutos jugados en ese partido; el color "
        "es el resultado del equipo en ese partido (🟢 ganó, 🟡 empató, 🔴 perdió)."
    )

    _render_player_comparison_table(con, jugados, filters.anios)
    _render_player_season_table(con, filters.jugador_ficha, filters.anios)


def _render_comparator_tab(con, filters: Filters) -> None:
    st.header("Comparador de jugadores / Temporadas")
    st.caption(
        "Elige 2 o más jugadores en el sidebar para comparar. Para comparar un jugador contra sí "
        "mismo en otra temporada, selecciónalo y después filtra por año con el rango del sidebar."
    )

    if len(filters.jugadores_comparador) < 1:
        st.info("Selecciona al menos un jugador en el sidebar.")
        return

    comparacion = dashboard_data.player_season_summary_filtered(
        con, jugadores=filters.jugadores_comparador, anios=filters.anios
    )
    if comparacion.empty:
        st.info("No hay datos de temporada para la selección.")
        return

    comparacion = comparacion.assign(
        jugador_anio=comparacion["jugador"] + " (" + comparacion["anio"].astype(str) + ")"
    )
    comparacion_display = comparacion.assign(posicion=comparacion["posicion"].map(fmt.position_label))
    comparacion_display = _scale_percent_columns(comparacion_display)
    st.dataframe(
        comparacion_display.drop(columns=["jugador_anio"]),
        width="stretch",
        hide_index=True,
        column_config=RANKING_COLUMN_CONFIG,
    )
    st.download_button(
        "⬇️ Descargar comparación (CSV)",
        data=comparacion_display.drop(columns=["jugador_anio"]).to_csv(index=False).encode("utf-8-sig"),
        file_name="comparacion_jugadores.csv",
        mime="text/csv",
    )

    metric = st.selectbox(
        "Métrica a comparar",
        list(RANKING_METRICS),
        format_func=RANKING_METRICS.get,
        key="comparador_metric",
    )
    comparacion_scale = _metric_scale(metric)
    comparacion_chart = (
        comparacion.assign(**{metric: comparacion[metric] * comparacion_scale})
        if comparacion_scale != 1
        else comparacion
    )
    _render_chart(
        px.bar(
            comparacion_chart,
            x="jugador_anio",
            y=metric,
            title=f"Comparación: {RANKING_METRICS[metric]}",
            color_discrete_sequence=[fmt.PRIMARY_COLOR],
            labels={"jugador_anio": "", metric: RANKING_METRICS[metric]},
        )
    )


if __name__ == "__main__":
    main()
