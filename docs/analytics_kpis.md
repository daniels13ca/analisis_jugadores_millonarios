# Fase 0 — Preguntas y KPIs del dashboard de rendimiento

Catálogo de las preguntas que el dashboard debe responder, con su métrica y la
tabla/columna exacta de donde sale (generadas por `python -m millos_data
build-analytics`, ver [analytics.py](../src/millos_data/analytics.py)). Sirve
como contrato entre la capa de datos y las vistas del dashboard: si una
pregunta nueva aparece, primero se agrega acá la métrica y de dónde sale,
después se construye el gráfico.

## Tablas disponibles

| Tabla | Grano | Contenido |
|---|---|---|
| `analytics/match_results.csv` | 1 fila por partido (200) | resultado, condición, rival, `resultado_partido` (W/D/L), `puntos`, incluye los 32 partidos sin plantilla registrada |
| `analytics/player_match_features.csv` | 1 fila por jugador × partido (3.110) | el dataset consolidado + `pases_precision_num`, `jugo`, columnas `*_por90`, `anio` |
| `analytics/player_season_summary.csv` | 1 fila por jugador × año (120) | totales y promedios agregados por año calendario |

## Preguntas de equipo

| Pregunta | Métrica | Fuente |
|---|---|---|
| ¿Cómo viene la forma reciente? | `resultado_partido` / `puntos` de los últimos N partidos, ordenado por `fecha` | `match_results` |
| ¿Rinde distinto de local que de visitante? | `puntos` promedio, `goles_favor`/`goles_contra` promedio, agrupado por `condicion` | `match_results` |
| ¿Cómo le va por torneo (liga vs. copas internacionales)? | mismas métricas agrupadas por `campeonato` | `match_results` |
| ¿Cuál es la eficiencia ofensiva? | goles / remates: `sum(goles) / sum(remates_totales)` y `sum(goles) / sum(remates_al_arco)` | `player_match_features` agregado por `match_id`, cruzado con `match_results` |
| ¿Qué tan disciplinado es el equipo? | `amarillas` + `rojas` promedio por partido | `player_match_features` agregado por `match_id` |
| ¿Cuánto domina el balón? (proxy, no hay posesión real) | `pases_totales` y `pases_precision_num` promedio del equipo por partido | `player_match_features` agregado por `match_id` |

**Limitación conocida**: no tenemos la tabla de posiciones de la liga ni los
resultados de los rivales entre sí — "forma" acá es *solo* la racha propia de
Millonarios, no una posición relativa en el campeonato.

**Nota de validación**: en 11 partidos, `sum(goles)` de `player_match_features`
queda 1 gol por debajo de `goles_favor` en `match_results`. Es autogol del
rival (no atribuible a ningún jugador de Millonarios en los datos), no un
error de consolidación — confirmado partido por partido antes de cerrar esta
fase.

## Preguntas de jugadores

| Pregunta | Métrica | Fuente |
|---|---|---|
| ¿Quién más contribuye ofensivamente? | `goles_por90`, `asistencias_por90` (temporada, no por partido individual) | `player_season_summary` |
| ¿Quién es más regular/mejor calificado? | `calificacion_promedio`, y su serie en el tiempo (`calificacion` por `fecha`) | `player_season_summary` / `player_match_features` |
| ¿Cómo se reparten los minutos? (uso de plantel) | `minutos_totales`, `partidos_jugados`, `titularidades` | `player_season_summary` |
| ¿Quién gana más duelos? | `duelos_ganados_pct` | `player_season_summary` |
| ¿Quién pasa mejor? | `pases_precision_promedio` | `player_season_summary` |
| ¿Quién es más indisciplinado? | `amarillas`, `rojas` (temporada) | `player_season_summary` |
| Comparar jugadores de la misma posición | cualquier métrica de arriba, filtrado por `posicion` | `player_season_summary` |

**Limitación conocida**: `anio` es el año calendario de la `fecha`, no la
temporada deportiva oficial (Apertura/Finalización). Suficiente para una v1;
si hace falta el split exacto por semestre, se puede agregar después sin
tocar el resto del pipeline.

**Nota de calidad de nombres (resuelta en Fase 2)**: no hay un ID de jugador
estable, se agrupa por el string `jugador` tal cual viene de la API. La
auditoría (`validate.check_player_name_variants`) sí encontró 4 casos reales
de fragmentación por tilde/mayúscula (mismo patrón que el de nombres de
rivales en `dedupe.py`): "Daniel Ruiz"/"Daniel Ruíz", "Nicolas
Arevalo"/"Nicolás Arévalo", "Jhoan Hernandez"/"Jhoan Hernández" y "Jonathan
Gonzalez"/"Jonathan Gónzalez". `build_player_match_features` ahora los
fusiona automáticamente (`canonicalize_player_names`), eligiendo la grafía
más frecuente en el dataset como canónica — en los 4 casos fue la variante
sin tilde. `validate-analytics` sigue reportando estos casos como warning
(no error) para que quede visible cuál se fusionó y con qué criterio.

## Prioridad para la v1 del dashboard (Fase 3-4) — implementada

Las 4 vistas están construidas en `dashboard/app.py` (Streamlit + DuckDB +
Plotly, ver [README](../README.md#dashboard)):

1. Resumen de equipo: puntos acumulados, forma reciente (media móvil de 5
   partidos), goles a favor/en contra por partido, resumen por condición y
   por campeonato.
2. Ranking de jugadores por `goles_por90` / `asistencias_por90` /
   `calificacion_promedio` / minutos / % duelos ganados, filtrable por
   posición y año.
3. Ficha de jugador: serie de `calificacion` en el tiempo, minutos por
   partido.
4. Comparador de 2+ jugadores (o el mismo jugador en distintos años).

Todo lo demás (clustering, índices compuestos, posición en la tabla de la
liga, etc.) queda para la Fase 6 — ver el listado de ideas en el
[README](../README.md#ideas-para-fase-6-analitica-avanzada--no-implementado),
después de validar que estas vistas ya aportan valor.

## Fase 2 — Validación, implementada

`validate.py` corre los checks de consistencia interna descritos arriba
(reconciliación de goles, `puntos` vs. `resultado_partido`, `condicion`
valida — todo partido debe ser `Local` o `Visitante`, sin nulos ni otro
valor —, duplicados, variantes de nombre) sobre datos reales. Estado a la
fecha: **0 errores**, 1 warning esperado (las 4 variantes de nombre ya
fusionadas, ver arriba). Ver
`python -m millos_data validate-analytics`.
