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
    "calificacion_promedio": "Calificacion promedio",
    "minutos_totales": "Minutos totales",
    "duelos_ganados_pct": "% Duelos ganados",
    "pases_precision_promedio": "% Precision de pase",
}

# column_config blocks reused across tables so the same raw column always
# gets the same header/format wherever it shows up.
RANKING_COLUMN_CONFIG = {
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

st.set_page_config(page_title="Millonarios FC — Rendimiento", layout="wide", page_icon="⚽")


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
        h3 { font-weight: 600 !important; }

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
        .wdl-row { display: flex; gap: 0.5rem; }
        .wdl-item { flex: 1; text-align: center; border-radius: 0.55rem; padding: 0.4rem 0.25rem; }
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
    """Like _stat_card_row, but appends a compound card with 3 nested W/D/L mini-cards.

    A single "12 / 8 / 5" metric label is hard to scan; nesting a nicely
    colored mini-card per outcome inside one wider card reads at a glance
    and matches the win/draw/loss color coding used everywhere else in the
    dashboard (see formatting.RESULT_COLORS).
    """
    parts = ['<div class="stat-card-row">']
    for card in cards:
        icon = f"{card['icon']} " if card.get("icon") else ""
        parts.append(
            f'<div class="stat-card"><span class="stat-value">{icon}{card["value"]}</span>'
            f'<span class="stat-label">{card["label"]}</span></div>'
        )
    parts.append(
        '<div class="stat-card wdl-card"><span class="stat-label">Resultados</span>'
        '<div class="wdl-row">'
        f'<div class="wdl-item wdl-win"><span class="wdl-value">{victorias}</span>'
        '<span class="wdl-sub">Ganados</span></div>'
        f'<div class="wdl-item wdl-draw"><span class="wdl-value">{empates}</span>'
        '<span class="wdl-sub">Empatados</span></div>'
        f'<div class="wdl-item wdl-loss"><span class="wdl-value">{derrotas}</span>'
        '<span class="wdl-sub">Perdidos</span></div>'
        "</div></div>"
    )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


@st.cache_resource
def _connection(analytics_dir: str):
    return dashboard_data.get_connection(Path(analytics_dir))


def _render_sidebar() -> None:
    with st.sidebar:
        st.header("⚽ Millonarios FC")
        st.caption(f"Datos: `{ANALYTICS_DIR}`")
        last_updated = dashboard_data.dataset_last_updated(ANALYTICS_DIR)
        if last_updated is not None:
            st.caption(f"Última actualización: {datetime.fromtimestamp(last_updated):%Y-%m-%d %H:%M}")
        st.caption(
            "Para refrescar con datos nuevos: `python -m millos_data refresh` "
            "(corre consolidate + build-analytics + validate-analytics de una)."
        )


def main() -> None:
    _inject_style()
    st.title("⚽ Millonarios FC — Rendimiento")
    _render_sidebar()

    if not (ANALYTICS_DIR / "match_results.csv").exists():
        st.error(
            f"No se encontraron las tablas de analitica en `{ANALYTICS_DIR}`. "
            "Corre `python -m millos_data build-analytics` primero."
        )
        st.stop()

    con = _connection(str(ANALYTICS_DIR))

    tab_equipo, tab_partidos, tab_ranking, tab_jugador, tab_comparador = st.tabs(
        ["📊 Equipo", "📋 Partidos", "🏆 Ranking de jugadores", "🔎 Ficha de jugador", "⚖️ Comparador"]
    )

    with tab_equipo:
        _render_team_tab(con)
    with tab_partidos:
        _render_matches_tab(con)
    with tab_ranking:
        _render_ranking_tab(con)
    with tab_jugador:
        _render_player_profile_tab(con)
    with tab_comparador:
        _render_comparator_tab(con)


def _form_chart(resultados: pd.DataFrame) -> go.Figure:
    """Match-by-match points (bar, colored win/draw/loss) with the rolling
    "forma reciente" average overlaid as a line.

    Replaces a plain all-time cumulative-points line, which only ever climbs
    and doesn't say much on its own -- this shows the actual sequence of
    results (won/drawn/lost, at a glance by color) *and* the smoothed trend
    in one chart.
    """
    colors = resultados["resultado_partido"].map(fmt.RESULT_COLORS).fillna("#9AA5B1")
    hover_customdata = resultados[["rival", "resultado"]].to_numpy()

    fig = go.Figure()
    fig.add_bar(
        x=resultados["fecha"],
        y=resultados["puntos"],
        marker_color=colors,
        name="Puntos por partido",
        customdata=hover_customdata,
        hovertemplate="%{x}<br>vs %{customdata[0]} (%{customdata[1]})<br>Puntos: %{y}<extra></extra>",
    )
    fig.add_scatter(
        x=resultados["fecha"],
        y=resultados["forma_reciente"],
        mode="lines",
        name="Forma (promedio móvil, 5 partidos)",
        line=dict(color=fmt.PRIMARY_COLOR, width=3),
        hovertemplate="%{x}<br>Forma reciente: %{y:.2f}<extra></extra>",
    )
    fig.update_layout(
        title="Racha de resultados y forma reciente",
        yaxis_title="Puntos",
        xaxis_title="",
        yaxis=dict(range=[0, 3.4], dtick=1),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        margin=dict(t=80),
    )
    return fig


def _points_race_chart(race: pd.DataFrame) -> go.Figure:
    race = race.astype({"anio": str})
    fig = px.line(
        race,
        x="jornada",
        y="puntos_acumulados",
        color="anio",
        markers=True,
        title="Puntos acumulados por año (comparación de ritmo)",
        labels={"jornada": "Jornada", "puntos_acumulados": "Puntos acumulados", "anio": "Año"},
        color_discrete_sequence=fmt.YEAR_COLOR_SEQUENCE,
    )
    fig.update_layout(legend_title_text="Año")
    return fig


def _render_team_tab(con) -> None:
    st.header("Resumen de equipo")

    campeonatos = dashboard_data.list_campeonatos(con)
    condiciones = dashboard_data.list_condiciones(con)

    col1, col2 = st.columns(2)
    selected_campeonatos = col1.multiselect("Campeonato", campeonatos, default=campeonatos, key="equipo_campeonato")
    selected_condiciones = col2.multiselect("Condición", condiciones, default=condiciones, key="equipo_condicion")

    resultados = dashboard_data.match_results_with_form(
        con,
        campeonatos=selected_campeonatos or None,
        condiciones=selected_condiciones or None,
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

    st.plotly_chart(_form_chart(resultados), width="stretch")

    race = dashboard_data.points_race_by_year(con, campeonatos=selected_campeonatos or None)
    if race["anio"].nunique() > 1:
        st.plotly_chart(_points_race_chart(race), width="stretch")
    else:
        st.caption(
            "La comparación de ritmo por año aparece cuando hay partidos de más de un año "
            "en los filtros seleccionados."
        )

    st.plotly_chart(
        px.bar(
            resultados,
            x="fecha",
            y=["goles_favor", "goles_contra"],
            barmode="group",
            title="Goles a favor / en contra por partido",
            color_discrete_map=fmt.GOALS_FOR_AGAINST_COLORS,
            labels={"value": "Goles", "variable": "", "fecha": "Fecha"},
        ),
        width="stretch",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Por condición")
        por_condicion = dashboard_data.team_summary(
            con, group_by="condicion", campeonatos=selected_campeonatos or None
        )
        st.dataframe(
            por_condicion.assign(condicion=por_condicion["condicion"].map(fmt.condition_label)),
            width="stretch",
            hide_index=True,
            column_config=_team_summary_column_config("condicion", "Condición"),
        )
    with col2:
        st.subheader("Por campeonato")
        por_campeonato = dashboard_data.team_summary(con, group_by="campeonato")
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
        "puntos_promedio": st.column_config.NumberColumn("Puntos/partido", format="%.2f"),
        "goles_favor_promedio": st.column_config.NumberColumn("GF/partido", format="%.2f"),
        "goles_contra_promedio": st.column_config.NumberColumn("GC/partido", format="%.2f"),
    }


def _render_matches_tab(con) -> None:
    st.header("Detalle de partidos")
    st.caption("Fecha, rival, condición y resultado de cada partido, con la planilla del que elijas.")

    campeonatos = dashboard_data.list_campeonatos(con)
    condiciones = dashboard_data.list_condiciones(con)

    col1, col2, col3 = st.columns(3)
    selected_campeonatos = col1.multiselect(
        "Campeonato", campeonatos, default=campeonatos, key="partidos_campeonato"
    )
    selected_condiciones = col2.multiselect(
        "Condición", condiciones, default=condiciones, key="partidos_condicion"
    )
    selected_resultados = col3.multiselect(
        "Resultado",
        ["W", "D", "L"],
        default=["W", "D", "L"],
        format_func=fmt.result_label,
        key="partidos_resultado",
    )

    partidos = dashboard_data.matches_filtered(
        con,
        campeonatos=selected_campeonatos or None,
        condiciones=selected_condiciones or None,
        resultados=selected_resultados or None,
    )

    if partidos.empty:
        st.info("No hay partidos para los filtros seleccionados.")
        return

    display = partidos.assign(
        condicion=partidos["condicion"].map(fmt.condition_label),
        resultado_partido=partidos["resultado_partido"].map(fmt.result_label),
    )[["fecha", "rival", "condicion", "resultado", "resultado_partido", "campeonato", "puntos"]]

    st.dataframe(
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
    )
    st.caption(f"{len(partidos)} partido(s)")

    sin_datos = int((~partidos["tiene_datos_jugadores"]).sum())
    if sin_datos:
        st.caption(f"ℹ️ {sin_datos} de estos partidos no tienen planilla de jugadores registrada.")

    st.divider()
    st.subheader("Planilla de un partido")

    con_datos = partidos[partidos["tiene_datos_jugadores"]].copy()
    if con_datos.empty:
        st.info("Ninguno de los partidos filtrados tiene planilla de jugadores.")
        return

    con_datos["etiqueta"] = (
        con_datos["fecha"] + " — " + con_datos["rival"]
        + " (" + con_datos["condicion"].map(fmt.condition_label) + ") "
        + con_datos["resultado"]
    )
    etiqueta_to_id = dict(zip(con_datos["etiqueta"], con_datos["match_id"]))
    seleccion = st.selectbox("Partido", list(etiqueta_to_id))

    lineup = dashboard_data.match_lineup(con, etiqueta_to_id[seleccion])
    if lineup.empty:
        st.info("No hay datos de jugadores para este partido.")
        return

    st.dataframe(
        lineup,
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


def _render_ranking_tab(con) -> None:
    st.header("Ranking de jugadores")

    anios = dashboard_data.list_anios(con)
    posiciones = dashboard_data.list_posiciones(con)

    col1, col2, col3 = st.columns(3)
    selected_anios = col1.multiselect("Año", anios, default=anios, key="ranking_anio")
    selected_posiciones = col2.multiselect("Posición", posiciones, default=posiciones, key="ranking_posicion")
    metric = col3.selectbox("Ordenar / graficar por", list(RANKING_METRICS), format_func=RANKING_METRICS.get)

    summary = dashboard_data.player_season_summary_filtered(
        con,
        anios=selected_anios or None,
        posiciones=selected_posiciones or None,
    )

    if summary.empty:
        st.info("No hay jugadores para los filtros seleccionados.")
        return

    # Benchmark against the position average for the chosen metric, not the
    # whole squad -- a center-back and a forward shouldn't share a
    # goles_por90 scale. Averages use the same anio filter as the table.
    pos_avg = dashboard_data.position_averages(con, anios=selected_anios or None)
    if metric in pos_avg.columns:
        avg_by_posicion = pos_avg.set_index("posicion")[metric]
        summary = summary.assign(
            promedio_posicion=summary["posicion"].map(avg_by_posicion),
        )
        summary["vs_promedio_posicion"] = summary[metric] - summary["promedio_posicion"]

    summary_sorted = summary.sort_values(metric, ascending=False, na_position="last")
    st.dataframe(
        summary_sorted,
        width="stretch",
        hide_index=True,
        column_config=RANKING_COLUMN_CONFIG,
    )
    st.download_button(
        "⬇️ Descargar tabla (CSV)",
        data=summary_sorted.to_csv(index=False).encode("utf-8-sig"),
        file_name="ranking_jugadores.csv",
        mime="text/csv",
    )

    with st.expander("Promedio por posición (todas las métricas)"):
        st.dataframe(
            pos_avg,
            width="stretch",
            hide_index=True,
            column_config={**RANKING_COLUMN_CONFIG, "posicion": st.column_config.TextColumn("Posición")},
        )

    top = summary_sorted.dropna(subset=[metric]).head(15)
    if not top.empty:
        top = top.assign(jugador_anio=top["jugador"] + " (" + top["anio"].astype(str) + ")")
        st.plotly_chart(
            px.bar(
                top,
                x="jugador_anio",
                y=metric,
                title=f"Top 15 — {RANKING_METRICS[metric]}",
                color_discrete_sequence=[fmt.PRIMARY_COLOR],
                labels={"jugador_anio": "", metric: RANKING_METRICS[metric]},
            ),
            width="stretch",
        )


def _render_player_profile_tab(con) -> None:
    st.header("Ficha de jugador")

    jugadores = dashboard_data.list_jugadores(con)
    if not jugadores:
        st.info("No hay jugadores disponibles.")
        return

    jugador = st.selectbox("Jugador", jugadores)
    historial = dashboard_data.player_match_history(con, jugador)
    jugados = historial[historial["jugo"].fillna(False)]

    if jugados.empty:
        st.info(f"{jugador} no registra minutos jugados en los datos disponibles.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Partidos jugados", len(jugados))
    c2.metric("Minutos totales", int(jugados["minutos"].sum()))
    calificacion_promedio = jugados["calificacion"].mean()
    c3.metric(
        "Calificación promedio",
        f"{calificacion_promedio:.2f}" if pd.notna(calificacion_promedio) else "n/d",
    )

    st.plotly_chart(
        px.line(
            jugados,
            x="fecha",
            y="calificacion",
            markers=True,
            title="Calificación por partido",
            color_discrete_sequence=[fmt.PRIMARY_COLOR],
        ),
        width="stretch",
    )
    st.plotly_chart(
        px.bar(
            jugados,
            x="fecha",
            y="minutos",
            title="Minutos jugados por partido",
            color_discrete_sequence=[fmt.ACCENT_COLOR],
        ),
        width="stretch",
    )


def _render_comparator_tab(con) -> None:
    st.header("Comparador de jugadores / temporadas")
    st.caption(
        "Elegí 2 o más filas (jugador x año) para comparar. Para comparar un jugador contra sí "
        "mismo en otra temporada, seleccionalo y después filtrá por año en la tabla de abajo."
    )

    jugadores = dashboard_data.list_jugadores(con)
    seleccionados = st.multiselect("Jugadores", jugadores)

    if len(seleccionados) < 1:
        st.info("Selecciona al menos un jugador.")
        return

    comparacion = dashboard_data.player_season_summary_filtered(con, jugadores=seleccionados)
    if comparacion.empty:
        st.info("No hay datos de temporada para la selección.")
        return

    comparacion = comparacion.assign(
        jugador_anio=comparacion["jugador"] + " (" + comparacion["anio"].astype(str) + ")"
    )
    st.dataframe(
        comparacion.drop(columns=["jugador_anio"]),
        width="stretch",
        hide_index=True,
        column_config=RANKING_COLUMN_CONFIG,
    )
    st.download_button(
        "⬇️ Descargar comparación (CSV)",
        data=comparacion.drop(columns=["jugador_anio"]).to_csv(index=False).encode("utf-8-sig"),
        file_name="comparacion_jugadores.csv",
        mime="text/csv",
    )

    metric = st.selectbox(
        "Métrica a comparar",
        list(RANKING_METRICS),
        format_func=RANKING_METRICS.get,
        key="comparador_metric",
    )
    st.plotly_chart(
        px.bar(
            comparacion,
            x="jugador_anio",
            y=metric,
            title=f"Comparación — {RANKING_METRICS[metric]}",
            color_discrete_sequence=[fmt.PRIMARY_COLOR],
            labels={"jugador_anio": "", metric: RANKING_METRICS[metric]},
        ),
        width="stretch",
    )


if __name__ == "__main__":
    main()
