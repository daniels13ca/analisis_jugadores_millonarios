"""Streamlit dashboard: rendimiento de equipo y jugadores de Millonarios FC.

Run with:

    streamlit run src/millos_data/dashboard/app.py

or `python -m millos_data dashboard` (see cli.py), which also lets you point
at a different `analytics/` folder via --analytics-dir.

Data source: the tables written by `python -m millos_data build-analytics`
(see docs/analytics_kpis.md for what each column means). This file only
handles layout/widgets; every query goes through dashboard/data.py.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from millos_data.dashboard import data as dashboard_data

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

st.set_page_config(page_title="Millonarios FC — Rendimiento", layout="wide")


@st.cache_resource
def _connection(analytics_dir: str):
    return dashboard_data.get_connection(Path(analytics_dir))


def _render_sidebar() -> None:
    with st.sidebar:
        st.header("⚽ Millonarios FC")
        st.caption(f"Datos: `{ANALYTICS_DIR}`")
        last_updated = dashboard_data.dataset_last_updated(ANALYTICS_DIR)
        if last_updated is not None:
            st.caption(f"Ultima actualizacion: {datetime.fromtimestamp(last_updated):%Y-%m-%d %H:%M}")
        st.caption(
            "Para refrescar con datos nuevos: `python -m millos_data refresh` "
            "(corre consolidate + build-analytics + validate-analytics de una)."
        )


def main() -> None:
    st.title("⚽ Millonarios FC — Rendimiento")
    _render_sidebar()

    if not (ANALYTICS_DIR / "match_results.csv").exists():
        st.error(
            f"No se encontraron las tablas de analitica en `{ANALYTICS_DIR}`. "
            "Corre `python -m millos_data build-analytics` primero."
        )
        st.stop()

    con = _connection(str(ANALYTICS_DIR))

    tab_equipo, tab_ranking, tab_jugador, tab_comparador = st.tabs(
        ["📊 Equipo", "🏆 Ranking de jugadores", "🔎 Ficha de jugador", "⚖️ Comparador"]
    )

    with tab_equipo:
        _render_team_tab(con)
    with tab_ranking:
        _render_ranking_tab(con)
    with tab_jugador:
        _render_player_profile_tab(con)
    with tab_comparador:
        _render_comparator_tab(con)


def _render_team_tab(con) -> None:
    st.header("Resumen de equipo")

    campeonatos = dashboard_data.list_campeonatos(con)
    condiciones = dashboard_data.list_condiciones(con)

    col1, col2 = st.columns(2)
    selected_campeonatos = col1.multiselect("Campeonato", campeonatos, default=campeonatos)
    selected_condiciones = col2.multiselect("Condicion", condiciones, default=condiciones)

    resultados = dashboard_data.match_results_with_form(
        con,
        campeonatos=selected_campeonatos or None,
        condiciones=selected_condiciones or None,
    )

    if resultados.empty:
        st.info("No hay partidos para los filtros seleccionados.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Partidos", len(resultados))
    c2.metric("Puntos", int(resultados["puntos"].fillna(0).sum()))
    c3.metric("Goles a favor", int(resultados["goles_favor"].fillna(0).sum()))
    c4.metric("Goles en contra", int(resultados["goles_contra"].fillna(0).sum()))

    st.plotly_chart(
        px.line(
            resultados,
            x="fecha",
            y="puntos_acumulados",
            title="Puntos acumulados en el tiempo",
            markers=True,
        ),
        width="stretch",
    )

    st.plotly_chart(
        px.line(
            resultados,
            x="fecha",
            y="forma_reciente",
            title="Forma reciente (promedio movil de puntos, ultimos 5 partidos)",
            markers=True,
        ),
        width="stretch",
    )

    st.plotly_chart(
        px.bar(
            resultados,
            x="fecha",
            y=["goles_favor", "goles_contra"],
            barmode="group",
            title="Goles a favor / en contra por partido",
        ),
        width="stretch",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Por condicion")
        st.dataframe(
            dashboard_data.team_summary(
                con, group_by="condicion", campeonatos=selected_campeonatos or None
            ),
            width="stretch",
        )
    with col2:
        st.subheader("Por campeonato")
        st.dataframe(
            dashboard_data.team_summary(con, group_by="campeonato"),
            width="stretch",
        )


def _render_ranking_tab(con) -> None:
    st.header("Ranking de jugadores")

    anios = dashboard_data.list_anios(con)
    posiciones = dashboard_data.list_posiciones(con)

    col1, col2, col3 = st.columns(3)
    selected_anios = col1.multiselect("Anio", anios, default=anios)
    selected_posiciones = col2.multiselect("Posicion", posiciones, default=posiciones)
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
    st.dataframe(summary_sorted, width="stretch")
    st.download_button(
        "⬇️ Descargar tabla (CSV)",
        data=summary_sorted.to_csv(index=False).encode("utf-8-sig"),
        file_name="ranking_jugadores.csv",
        mime="text/csv",
    )

    with st.expander("Promedio por posicion (todas las metricas)"):
        st.dataframe(pos_avg, width="stretch")

    top = summary_sorted.dropna(subset=[metric]).head(15)
    if not top.empty:
        top = top.assign(jugador_anio=top["jugador"] + " (" + top["anio"].astype(str) + ")")
        st.plotly_chart(
            px.bar(
                top,
                x="jugador_anio",
                y=metric,
                title=f"Top 15 — {RANKING_METRICS[metric]}",
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
        "Calificacion promedio",
        f"{calificacion_promedio:.2f}" if pd.notna(calificacion_promedio) else "n/d",
    )

    st.plotly_chart(
        px.line(jugados, x="fecha", y="calificacion", markers=True, title="Calificacion por partido"),
        width="stretch",
    )
    st.plotly_chart(
        px.bar(jugados, x="fecha", y="minutos", title="Minutos jugados por partido"),
        width="stretch",
    )


def _render_comparator_tab(con) -> None:
    st.header("Comparador de jugadores / temporadas")
    st.caption(
        "Elegi 2 o mas filas (jugador x anio) para comparar. Para comparar un jugador contra si "
        "mismo en otra temporada, seleccionalo y despues filtra por anio en la tabla de abajo."
    )

    jugadores = dashboard_data.list_jugadores(con)
    seleccionados = st.multiselect("Jugadores", jugadores)

    if len(seleccionados) < 1:
        st.info("Selecciona al menos un jugador.")
        return

    comparacion = dashboard_data.player_season_summary_filtered(con, jugadores=seleccionados)
    if comparacion.empty:
        st.info("No hay datos de temporada para la seleccion.")
        return

    comparacion = comparacion.assign(
        jugador_anio=comparacion["jugador"] + " (" + comparacion["anio"].astype(str) + ")"
    )
    st.dataframe(comparacion.drop(columns=["jugador_anio"]), width="stretch")
    st.download_button(
        "⬇️ Descargar comparacion (CSV)",
        data=comparacion.drop(columns=["jugador_anio"]).to_csv(index=False).encode("utf-8-sig"),
        file_name="comparacion_jugadores.csv",
        mime="text/csv",
    )

    metric = st.selectbox(
        "Metrica a comparar",
        list(RANKING_METRICS),
        format_func=RANKING_METRICS.get,
        key="comparador_metric",
    )
    st.plotly_chart(
        px.bar(comparacion, x="jugador_anio", y=metric, title=f"Comparacion — {RANKING_METRICS[metric]}"),
        width="stretch",
    )


if __name__ == "__main__":
    main()
