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
    "temporadas": st.column_config.TextColumn("Temporadas"),
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
    jugadores: list[str]
    goles_anio: int | None
    min_partidos: int


DEFAULT_MIN_PARTIDOS = 3


def _query_param_years(anio_min: int, anio_max: int) -> tuple[int, int]:
    """Read anio_inicio/anio_fin from the URL's query params, clamped to the
    dataset's actual range -- lets a filtered "Rango de años" be shared via
    link. Falls back to the full range if absent, malformed, or inverted.
    """
    raw_inicio = st.query_params.get("anio_inicio")
    raw_fin = st.query_params.get("anio_fin")
    if not (raw_inicio and raw_inicio.isdigit() and raw_fin and raw_fin.isdigit()):
        return anio_min, anio_max
    inicio = min(max(int(raw_inicio), anio_min), anio_max)
    fin = min(max(int(raw_fin), anio_min), anio_max)
    return (inicio, fin) if inicio <= fin else (anio_min, anio_max)


def _render_sidebar(con) -> Filters:
    """Sidebar: a title, the two dataset-freshness dates, and every filter
    control -- grouped as team/match filters (which apply to Equipo and
    Partidos) then, past a divider, player filters (Ranking, Ficha,
    Comparativa). No other text.

    One multiselect ("Jugadores") drives both Ficha and Comparativa instead
    of a separate control per tab -- Ficha shows the ficha of whichever one
    is selected (or lets you pick, in-tab, when there's more than one), and
    Comparativa compares everyone selected. Defaults to the first player so
    Ficha has something to show without any action.

    "Rango de años" and "Jugadores" are mirrored into the URL's query
    params, so a specific filtered view (a player, a year range) can be
    shared via link and comes back on reload.
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
            default_anios = _query_param_years(anio_min, anio_max)
            anio_inicio, anio_fin = st.slider(
                "Rango de años",
                min_value=anio_min,
                max_value=anio_max,
                value=default_anios,
            )
            anios = list(range(anio_inicio, anio_fin + 1))
            st.query_params["anio_inicio"] = str(anio_inicio)
            st.query_params["anio_fin"] = str(anio_fin)

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

        # --- Ranking / Ficha de jugador / Comparativa ---
        posiciones = dashboard_data.list_posiciones(con)
        selected_posiciones = st.multiselect(
            "Posición (Ranking)", posiciones, default=posiciones, format_func=fmt.position_label
        )

        jugadores = dashboard_data.list_jugadores(con)
        if "jugadores_selector" not in st.session_state:
            # Seed session_state before instantiating the widget, instead of
            # passing `default=` -- a "Ver ficha" button elsewhere (see
            # _select_jugador_for_ficha) also writes this same key via the
            # Session State API, and Streamlit warns if a keyed widget gets
            # both a `default=` and a session_state write.
            query_jugadores = [j for j in st.query_params.get_all("jugador") if j in jugadores]
            st.session_state["jugadores_selector"] = query_jugadores or (jugadores[:1] if jugadores else [])
        selected_jugadores = st.multiselect(
            "Jugadores (Ficha / Comparativa)",
            jugadores,
            key="jugadores_selector",
        )
        if selected_jugadores:
            st.query_params["jugador"] = selected_jugadores
        elif "jugador" in st.query_params:
            del st.query_params["jugador"]

        min_partidos = st.slider(
            "Mínimo de partidos (Ranking / Ficha / Comparativa)",
            min_value=1,
            max_value=10,
            value=DEFAULT_MIN_PARTIDOS,
            help=(
                "Por debajo de este número de partidos jugados, una tasa por 90' o un porcentaje "
                "puede estar dominado por uno o dos partidos puntuales -- las vistas de jugadores "
                "avisan cuando esto aplica en vez de ocultarlo en silencio."
            ),
        )

        return Filters(
            anios=anios,
            campeonatos=selected_campeonatos or None,
            condiciones=selected_condiciones or None,
            resultados=selected_resultados or None,
            posiciones=selected_posiciones or None,
            jugadores=selected_jugadores,
            goles_anio=goles_anio,
            min_partidos=min_partidos,
        )


def _render_glossary() -> None:
    """Definitions built lazily (not a module-level constant) since it
    references FORM_ROLLING_WINDOW, which is defined further down this
    file -- that's fine at call time (this only runs once main() is
    already executing, well after the whole module has loaded).
    """
    glosario = [
        ("Calificación", "Puntaje de rendimiento de API-Football para ese partido, en escala 0-10."),
        (
            "Forma reciente (Equipo)",
            f"Promedio móvil de puntos obtenidos (0/1/3) en los últimos {FORM_ROLLING_WINDOW} partidos.",
        ),
        (
            "Goles / Asistencias por 90'",
            "Goles o asistencias normalizados a 90 minutos jugados, para poder comparar jugadores "
            "con distintos minutos en cancha (un suplente y un titular, por ejemplo).",
        ),
        ("% Duelos ganados", "Duelos individuales ganados / duelos individuales disputados."),
        ("% Precisión de pase", "Pases completados / pases intentados."),
        (
            "Promedio de posición / vs. promedio",
            "El promedio de esa métrica entre todos los jugadores que juegan esa misma posición "
            "(defensa, mediocampista, etc.), y la diferencia del jugador puntual contra ese "
            "promedio.",
        ),
        (
            "Radar (Comparativa)",
            "Cada eje normaliza el valor del jugador contra el mejor registrado en una temporada "
            "en la liga -- en su posición para goles/asistencias por 90' (métricas donde la "
            "posición influye mucho), y en general para calificación/% duelos/% pases. 100% = el "
            "mejor registrado.",
        ),
        (
            "Mínimo de partidos",
            "Filtro del sidebar: por debajo de ese número de partidos jugados, una tasa por 90' o "
            "un porcentaje puede estar dominado por uno o dos partidos puntuales y dejar de ser "
            "representativa -- las vistas de jugadores avisan cuando esto aplica.",
        ),
    ]
    with st.expander("❓ Glosario de métricas"):
        for termino, definicion in glosario:
            st.markdown(f"**{termino}**: {definicion}")


def main() -> None:
    _inject_style()
    st.title("⚽ Millonarios FC: Rendimiento")
    _render_glossary()

    if not (ANALYTICS_DIR / "match_results.csv").exists():
        st.error(
            f"No se encontraron las tablas de analítica en `{ANALYTICS_DIR}`. "
            "Corre `python -m millos_data build-analytics` primero."
        )
        st.stop()

    con = _connection(str(ANALYTICS_DIR))
    filters = _render_sidebar(con)

    tab_equipo, tab_partidos, tab_ranking, tab_jugador, tab_comparador = st.tabs(
        ["📊 Equipo", "📋 Partidos", "🏆 Ranking de jugadores", "🔎 Ficha de jugador", "⚖️ Comparativa de jugadores"]
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
        _render_comparison_tab(con, filters)


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
    st.download_button(
        "⬇️ Descargar partidos con forma (CSV)",
        data=resultados.to_csv(index=False).encode("utf-8-sig"),
        file_name="equipo_partidos.csv",
        mime="text/csv",
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
    st.download_button(
        "⬇️ Descargar histórico (CSV)",
        data=display.to_csv(index=False).encode("utf-8-sig"),
        file_name="historico_partidos.csv",
        mime="text/csv",
    )

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

    lineup_display = lineup.assign(posicion=lineup["posicion"].map(fmt.position_label))
    st.dataframe(
        lineup_display,
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
    st.download_button(
        "⬇️ Descargar planilla (CSV)",
        data=lineup_display.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"planilla_{str(match_id).replace(':', '_')}.csv",
        mime="text/csv",
    )


MEDALS = ["🥇", "🥈", "🥉"]


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


def _select_jugador_for_ficha(jugador: str) -> None:
    """on_click callback for the podium's "Ver ficha" buttons -- runs before
    the script reruns from the top, so it's safe to write straight into the
    sidebar multiselect's session_state key here (unlike doing it inline in
    the tab body, which would run *after* that widget was already
    instantiated this same run and raise). Streamlit can't switch the
    active tab programmatically, so the user still clicks over to Ficha/
    Comparativa themselves; this just saves re-typing the name there.
    """
    st.session_state["jugadores_selector"] = [jugador]


def _render_podium(top: pd.DataFrame, metric: str, periodo_col: str) -> None:
    """Top-3 cards for the selected metric, medal-style -- a quick highlight
    before the full table, reusing the same card component as Equipo. Below
    the cards, one button per player pre-selects them in the sidebar's
    "Jugadores" control, to jump into Ficha/Comparativa without re-typing
    the name.

    Always shows partidos_jugados alongside the metric: a single standout
    match can otherwise look like a full-season leader (e.g. 4+ goles_por90
    from one great game), which is misleading without that context.
    """
    top3 = top.head(3)
    podio = [
        {
            "icon": medalla,
            "value": _format_metric_value(metric, row[metric]),
            "label": f"{row['jugador']} ({row[periodo_col]}) · {int(row['partidos_jugados'])} PJ",
        }
        for medalla, (_, row) in zip(MEDALS, top3.iterrows())
    ]
    if not podio:
        return
    _stat_card_row(podio)

    columns = st.columns(len(top3))
    for col, (_, row) in zip(columns, top3.iterrows()):
        with col:
            st.button(
                f"🔎 Ver ficha: {row['jugador']}",
                key=f"ver_ficha_{row['jugador']}_{row[periodo_col]}",
                on_click=_select_jugador_for_ficha,
                args=(row["jugador"],),
                width="stretch",
            )
    st.caption(
        "Al hacer clic, el jugador queda seleccionado en el sidebar -- ve a la pestaña 'Ficha de "
        "jugador' o 'Comparativa de jugadores' para verlo."
    )


def _render_ranking_tab(con, filters: Filters) -> None:
    st.header("Ranking de jugadores")
    st.caption(
        "No se ve afectado por los filtros de Campeonato/Condición del sidebar -- sí por "
        "Posición, Rango de años y Mínimo de partidos."
    )

    metric = st.selectbox("Ordenar / Graficar por", list(RANKING_METRICS), format_func=RANKING_METRICS.get)
    vista = st.radio(
        "Vista",
        ["Por temporada", "Agregado por jugador"],
        horizontal=True,
        help=(
            "Por temporada: una fila por jugador y año (un jugador puede aparecer varias veces "
            "en el top). Agregado: una sola fila por jugador, sumando todo el rango de años del "
            "sidebar -- útil para comparar carreras en vez de temporadas puntuales."
        ),
    )

    if vista == "Por temporada":
        summary = dashboard_data.player_season_summary_filtered(
            con, anios=filters.anios, posiciones=filters.posiciones,
        )
        periodo_col = "anio"
    else:
        summary = dashboard_data.player_summary_aggregate(
            con, jugadores=dashboard_data.list_jugadores(con), anios=filters.anios,
        )
        if not summary.empty:
            if filters.posiciones:
                summary = summary[summary["posicion"].isin(filters.posiciones)]
            summary = summary.assign(
                temporadas=[
                    _format_season_span(anio_min, anio_max)
                    for anio_min, anio_max in zip(summary["anio_min"], summary["anio_max"])
                ]
            ).drop(columns=["anio_min", "anio_max", "amarillas", "rojas"])
        periodo_col = "temporadas"

    if summary.empty:
        st.info("No hay jugadores para los filtros seleccionados.")
        return

    # Benchmark against the position average for the chosen metric, not the
    # whole squad -- a center-back and a forward shouldn't share a
    # goles_por90 scale. Averages use the same (global) anio filter as the
    # table, and the per-season table regardless of which vista is active
    # (a per-season average is still a meaningful yardstick for an
    # aggregated-by-jugador rate).
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
        top = top.assign(jugador_anio=top["jugador"] + " (" + top[periodo_col].astype(str) + ")")

    _render_podium(top, metric, periodo_col)

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
        # purely from a small sample; require the sidebar's minimum before
        # comparing them against their position's average.
        top_vs_avg = top_vs_avg[top_vs_avg["partidos_jugados"] >= filters.min_partidos]
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
                f"Solo incluye jugadores con {filters.min_partidos} o más partidos jugados (ajustable "
                "en el sidebar), para no comparar contra el promedio a alguien con una muestra muy "
                "chica."
            )


PLAYER_FORM_ROLLING_WINDOW = 5

# Rate metrics compared against the position average on the player's own
# profile, and reused as the radar-chart axes in the Comparativa tab --
# minutos_totales is deliberately left out here (it already has its own
# stat card, and "minutes vs. position average"/"minutes vs. league max"
# isn't a performance comparison the way the others are).
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


def _render_player_comparison_table(
    con, jugados: pd.DataFrame, anios: list[int] | None, min_partidos: int
) -> None:
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
    if len(jugados) < min_partidos:
        st.caption(
            f"⚠️ {len(jugados)} partido(s) jugado(s) -- por debajo del mínimo configurado en el "
            f"sidebar ({min_partidos}). Las tasas de abajo pueden no ser representativas."
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _render_player_season_table(con, jugador: str, anios: list[int] | None) -> None:
    resumen = dashboard_data.player_season_summary_filtered(con, jugadores=[jugador], anios=anios)
    if resumen.empty:
        return
    resumen_display = resumen.assign(posicion=resumen["posicion"].map(fmt.position_label))
    resumen_display = _scale_percent_columns(resumen_display).sort_values("anio")

    st.subheader("Resumen por temporada")
    st.dataframe(
        resumen_display,
        width="stretch",
        hide_index=True,
        column_config=RANKING_COLUMN_CONFIG,
    )
    st.download_button(
        "⬇️ Descargar resumen por temporada (CSV)",
        data=resumen_display.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{jugador.replace(' ', '_').lower()}_temporadas.csv",
        mime="text/csv",
        key="ficha_download_temporadas",
    )


def _season_trend_card(con, jugador: str) -> dict:
    """"Tendencia vs. 2023" style card, comparing the player's two most
    recent seasons on record -- independent of the sidebar's year range
    (that range decides what the cards/chart above aggregate over; this is
    always "the last full season vs. the one before it", a fixed fact about
    the player's trajectory).
    """
    historial = dashboard_data.player_season_summary_filtered(con, jugadores=[jugador]).sort_values("anio")
    if len(historial) < 2:
        return {"label": "Tendencia", "value": "s/d"}

    ultimo, anterior = historial.iloc[-1], historial.iloc[-2]
    delta = ultimo["calificacion_promedio"] - anterior["calificacion_promedio"]
    flecha = "▲" if delta > 0 else "▼" if delta < 0 else "→"
    return {
        "label": f"Tendencia (Calif. vs. {int(anterior['anio'])})",
        "value": f"{flecha} {_format_metric_delta('calificacion_promedio', delta)}",
    }


def _render_player_profile_tab(con, filters: Filters) -> None:
    st.header("Ficha de jugador")
    st.caption(
        "No se ve afectada por los filtros de Campeonato/Condición del sidebar -- sí por el "
        "Rango de años."
    )

    if not filters.jugadores:
        st.info("Selecciona al menos un jugador en el sidebar.")
        return

    if len(filters.jugadores) == 1:
        jugador = filters.jugadores[0]
    else:
        jugador = st.selectbox("Ver ficha de", filters.jugadores)

    historial = dashboard_data.player_match_history(con, jugador, anios=filters.anios)
    jugados = historial[historial["jugo"].fillna(False)]

    if jugados.empty:
        st.info(f"{jugador} no registra minutos jugados en los datos disponibles.")
        return

    posicion_moda = jugados["posicion"].mode()
    posicion_label = fmt.position_label(posicion_moda.iat[0]) if not posicion_moda.empty else "s/d"
    st.subheader(f"{jugador} · {posicion_label}")

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
            _season_trend_card(con, jugador),
        ]
    )

    _render_chart(_player_form_chart(jugados))
    st.caption(
        "El tamaño de cada punto es proporcional a los minutos jugados en ese partido; el color "
        "es el resultado del equipo en ese partido (🟢 ganó, 🟡 empató, 🔴 perdió)."
    )

    _render_player_comparison_table(con, jugados, filters.anios, filters.min_partidos)
    _render_player_season_table(con, jugador, filters.anios)

    st.download_button(
        "⬇️ Descargar historial partido a partido (CSV)",
        data=jugados.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{jugador.replace(' ', '_').lower()}_partidos.csv",
        mime="text/csv",
        key="ficha_download_partidos",
    )


# Numeric season-summary columns eligible for the "quién tiene el mejor
# valor" table highlight -- identifying columns (jugador/anio/posicion) are
# deliberately excluded.
COMPARISON_HIGHLIGHT_COLUMNS = [
    "partidos_jugados",
    "titularidades",
    "minutos_totales",
    "goles",
    "asistencias",
    "goles_por90",
    "asistencias_por90",
    "calificacion_promedio",
    "duelos_ganados_pct",
    "pases_precision_promedio",
]

# Qualitative palette for the radar chart's per-jugador polygons -- a
# neutral, muted set (not WIN/DRAW/LOSS green/amber/red, which already
# carry a specific meaning everywhere else in the dashboard) since a
# jugador has no inherent color.
RADAR_COLOR_SEQUENCE = px.colors.qualitative.Set2


def _format_season_span(anio_min: float, anio_max: float) -> str:
    """"2022-2024", or just "2023" when a player's rows all fall in one
    year -- shows what part of the sidebar's year range a given jugador's
    aggregated row actually covers (a player who joined partway through
    won't cover all of it).
    """
    if pd.isna(anio_min) or pd.isna(anio_max):
        return "s/d"
    anio_min, anio_max = int(anio_min), int(anio_max)
    return f"{anio_min}" if anio_min == anio_max else f"{anio_min}-{anio_max}"


def _comparison_stat_cards(row: pd.Series) -> list[dict]:
    return [
        {"label": "Temporadas", "value": _format_season_span(row["anio_min"], row["anio_max"])},
        {"label": "Partidos", "value": int(row["partidos_jugados"])},
        {"label": "Minutos", "value": int(row["minutos_totales"])},
        {"label": "Goles", "value": int(row["goles"])},
        {"label": "Asistencias", "value": int(row["asistencias"])},
        {"label": "Calificación", "value": _format_metric_value("calificacion_promedio", row["calificacion_promedio"])},
        {"label": "% Duelos ganados", "value": _format_metric_value("duelos_ganados_pct", row["duelos_ganados_pct"])},
    ]


def _highlight_best_per_metric(df: pd.DataFrame):
    """Wrap df in a pandas Styler that highlights the max value in each
    comparison metric column -- makes it obvious at a glance who has the
    best number in each stat, without touching the underlying values
    (column_config still controls how each one is displayed).
    """
    columns = [c for c in COMPARISON_HIGHLIGHT_COLUMNS if c in df.columns]
    return df.style.highlight_max(subset=columns, color=f"{fmt.ACCENT_COLOR}40")


# goles_por90/asistencias_por90 depend heavily on position (a forward's
# ceiling is nowhere near a defensive midfielder's) -- normalizing those
# against the *position's* max, not the whole league's, so a non-forward
# doesn't read as uniformly "flat" on the radar regardless of how good they
# are at their own job. Calificación/% duelos/% pases are more
# position-agnostic and stay normalized against the league-wide max.
POSITION_RELATIVE_RADAR_METRICS = {"goles_por90", "asistencias_por90"}


def _comparison_radar_chart(con, comparacion: pd.DataFrame, anios: list[int] | None) -> go.Figure:
    """One filled polygon per jugador across PLAYER_COMPARISON_METRICS, each
    metric normalized against the best *single-season* value in the same
    (year-filtered) season table -- so a polygon's shape reflects that
    player's own standing against the best anyone has done, and doesn't
    reshape just because a stronger or weaker player is added to the
    comparison. See POSITION_RELATIVE_RADAR_METRICS for which axes use a
    position-specific ceiling instead of the whole league's.
    """
    domain = dashboard_data.player_season_summary_filtered(con, anios=anios)
    global_maxes = {
        metric: domain[metric].max() if metric in domain.columns and domain[metric].notna().any() else float("nan")
        for metric in PLAYER_COMPARISON_METRICS
    }
    position_maxes = (
        domain.groupby("posicion")[list(POSITION_RELATIVE_RADAR_METRICS)].max()
        if not domain.empty
        else pd.DataFrame()
    )

    def _max_for(metric: str, posicion) -> float:
        if metric in POSITION_RELATIVE_RADAR_METRICS and posicion in position_maxes.index:
            return position_maxes.loc[posicion, metric]
        return global_maxes[metric]

    labels = [RANKING_METRICS[metric] for metric in PLAYER_COMPARISON_METRICS]

    fig = go.Figure()
    for idx, (_, row) in enumerate(comparacion.iterrows()):
        values = []
        hover_text = []
        for metric in PLAYER_COMPARISON_METRICS:
            max_value = _max_for(metric, row["posicion"])
            raw_value = row[metric]
            if pd.isna(raw_value) or pd.isna(max_value) or max_value == 0:
                values.append(0)
            else:
                values.append(raw_value / max_value * 100)
            # The radial position is a relative "% of the best", which reads
            # as ambiguous on its own for a metric that's already itself a
            # percentage (% duelos, % pases) -- the tooltip spells out both
            # numbers, and which ceiling (position or league) was used, so
            # there's no confusing "the metric's own %" with "% of the max".
            basis = (
                f"de {fmt.position_label(row['posicion'])} en la liga"
                if metric in POSITION_RELATIVE_RADAR_METRICS
                else "en la liga"
            )
            hover_text.append(
                f"{RANKING_METRICS[metric]}: {_format_metric_value(metric, raw_value)}"
                f"<br>Nivel: {values[-1]:.0f}% del máximo de una temporada {basis}"
                if pd.notna(raw_value)
                else f"{RANKING_METRICS[metric]}: s/d"
            )
        color = RADAR_COLOR_SEQUENCE[idx % len(RADAR_COLOR_SEQUENCE)]
        fig.add_trace(
            go.Scatterpolar(
                r=values + values[:1],
                theta=labels + labels[:1],
                fill="toself",
                name=row["jugador"],
                line=dict(color=color),
                opacity=0.75,
                text=hover_text + hover_text[:1],
                hovertemplate="<b>%{fullData.name}</b><br>%{text}<extra></extra>",
            )
        )
    fig.update_layout(
        title=(
            "Comparación por métrica<br>"
            "<sup>Goles/asistencias por 90': % del máximo de su posición · el resto: % del máximo "
            "de la liga</sup>"
        ),
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], ticksuffix="% del máx.")),
    )
    return fig


def _render_comparison_evolution_chart(con, filters: Filters) -> None:
    """A metric's year-over-year line, shown only for the "un solo jugador,
    distintas temporadas" case -- with 2+ different players selected, the
    radar above already covers the snapshot comparison and a per-metric
    evolution line wouldn't have a single subject to follow.
    """
    if len(filters.jugadores) != 1:
        return

    jugador = filters.jugadores[0]
    per_year = dashboard_data.player_season_summary_filtered(con, jugadores=[jugador], anios=filters.anios)
    if per_year["anio"].nunique() < 2:
        return

    metric = st.selectbox(
        "Métrica a comparar en el tiempo",
        list(RANKING_METRICS),
        format_func=RANKING_METRICS.get,
        key="comparador_metric",
    )
    scale = _metric_scale(metric)
    data = per_year.sort_values("anio").copy()
    if scale != 1:
        data[metric] = data[metric] * scale

    _render_chart(
        px.line(
            data,
            x="anio",
            y=metric,
            markers=True,
            title=f"Evolución de {jugador}: {RANKING_METRICS[metric]}",
            color_discrete_sequence=[fmt.PRIMARY_COLOR],
            labels={"anio": "Año", metric: RANKING_METRICS[metric]},
        )
    )


def _render_comparison_tab(con, filters: Filters) -> None:
    st.header("Comparativa de jugadores")
    st.caption(
        "Elige 2 o más jugadores en el sidebar para comparar. Para ver la evolución de un solo "
        "jugador entre temporadas, selecciónalo solo a él y ajusta el rango de años del sidebar. "
        "No se ve afectada por los filtros de Campeonato/Condición del sidebar."
    )

    if not filters.jugadores:
        st.info("Selecciona al menos un jugador en el sidebar.")
        return

    comparacion = dashboard_data.player_summary_aggregate(con, jugadores=filters.jugadores, anios=filters.anios)
    if comparacion.empty:
        st.info("No hay datos para la selección.")
        return

    bajo_muestra = comparacion[comparacion["partidos_jugados"] < filters.min_partidos]["jugador"].tolist()
    if bajo_muestra:
        st.caption(
            f"⚠️ {', '.join(bajo_muestra)} — menos de {filters.min_partidos} partido(s) jugado(s) "
            "en el rango filtrado; sus tasas por 90'/porcentajes pueden no ser representativas."
        )

    for _, row in comparacion.sort_values("jugador").iterrows():
        st.markdown(f"**{row['jugador']} · {fmt.position_label(row['posicion'])}**")
        _stat_card_row(_comparison_stat_cards(row))

    comparacion_display = comparacion.assign(
        posicion=comparacion["posicion"].map(fmt.position_label),
        temporadas=[
            _format_season_span(anio_min, anio_max)
            for anio_min, anio_max in zip(comparacion["anio_min"], comparacion["anio_max"])
        ],
    ).drop(columns=["anio_min", "anio_max", "amarillas", "rojas"])
    comparacion_display = _scale_percent_columns(comparacion_display)
    st.dataframe(
        _highlight_best_per_metric(comparacion_display),
        width="stretch",
        hide_index=True,
        column_config=RANKING_COLUMN_CONFIG,
    )
    st.download_button(
        "⬇️ Descargar comparación (CSV)",
        data=comparacion_display.to_csv(index=False).encode("utf-8-sig"),
        file_name="comparacion_jugadores.csv",
        mime="text/csv",
    )

    _render_chart(_comparison_radar_chart(con, comparacion, filters.anios))
    st.caption(
        "Cada métrica está normalizada contra el máximo de una temporada dentro del rango de años "
        "filtrado (por posición para goles/asistencias por 90', por liga completa para el resto) "
        "-- así la forma del polígono refleja el nivel general del jugador y no solo la "
        "comparación entre los seleccionados."
    )

    _render_comparison_evolution_chart(con, filters)


if __name__ == "__main__":
    main()
