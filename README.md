# Analisis Jugadores Millonarios

Paquete Python para descargar, transformar y consolidar estadisticas de jugadores de
Millonarios FC a partir de la API de API-Football, y un dashboard (Streamlit + DuckDB + Plotly)
para analizar el rendimiento del equipo y de los jugadores.

## Guia rapida

Los dos flujos mas comunes: bajar datos nuevos de una temporada, y abrir el dashboard.

```powershell
# 1. Instalar (incluye lo necesario para ETL, tests y dashboard)
python -m pip install -e ".[dev]"

# 2. Configurar la API key (una vez) -- ver "Variables de entorno" mas abajo
#    Opcion A: archivo .env en la raiz del repo con FOOTBALL_API_KEY=tu_api_key
#    Opcion B: variable de entorno
$env:FOOTBALL_API_KEY="tu_api_key"

# 3. Descargar una temporada
python -m millos_data download-season --season 2025

# 4. Refrescar el CSV consolidado + las tablas de analitica + validarlas, todo de una
python -m millos_data refresh --base-path .

# 5. Abrir el dashboard
python -m millos_data dashboard
```

El paso 5 abre `http://localhost:8501` en el navegador. Si ya tenias el repo clonado con datos
existentes, podes saltar directo al paso 5 (las tablas de `analytics/` ya estan generadas); corre
el paso 4 despues de cada descarga nueva. Detalle de cada comando en las secciones de abajo.

## Estructura

- `src/millos_data/`: logica de configuracion, descarga, transformacion, deduplicacion y
  consolidacion.
  - `config.py`: `ApiConfig` (carga `.env` via `python-dotenv`, valida el equipo soportado) y
    `season_directory_name()`.
  - `extract.py`: llamadas a la API (con reintentos/backoff), armado del JSON por partido y
    deteccion de fixtures ya descargados.
  - `schema.py`: fuente unica de verdad del esquema de una fila jugador-partido (columnas del CSV
    y como se extraen del JSON anidado).
  - `transform.py`: aplanado de un JSON de partido a filas, usando `schema.py`.
  - `consolidate.py`: descubre los JSON de todas las temporadas y arma el CSV consolidado.
  - `dedupe.py`: detecta partidos duplicados (p. ej. por un cambio de nombre de rival en la API)
    y los archiva sin borrarlos.
  - `analytics.py`: capa de analitica — tablas listas para dashboard (resultados de equipo,
    features por jugador-partido, resumen por temporada), incluye la canonicalizacion de nombres
    de jugador con variantes de escritura (tildes). Ver
    [docs/analytics_kpis.md](docs/analytics_kpis.md) para el catalogo de preguntas/metricas.
  - `validate.py`: sanity checks sobre las tablas de analitica (partidos duplicados, stats
    negativos, reconciliacion de goles equipo vs. jugadores, variantes de nombre) — ver
    [Validacion de datos](#validacion-de-datos).
  - `dashboard/`: dashboard Streamlit + DuckDB + Plotly. `data.py` es la capa de queries (DuckDB,
    testeable sin Streamlit); `app.py` es la UI. Ver [Dashboard](#dashboard).
  - `pipeline.py`: orquesta consolidate + build-analytics + validate-analytics en un solo paso
    (`refresh`) — ver [Refrescar todo de una](#refrescar-todo-de-una).
  - `cli.py`: comandos `consolidate`, `download-season`, `dedupe-matches`, `build-analytics`,
    `validate-analytics`, `refresh` y `dashboard`.
- `tests/`: pruebas unitarias, con un factory compartido en `conftest.py` para construir JSON de
  partidos de prueba.
- `docs/analytics_kpis.md`: catalogo de preguntas de negocio y de que tabla/columna sale cada
  metrica (el contrato entre la capa de datos y el futuro dashboard).
- `Millonarios_*_Stats_Detalladas/`: datos JSON historicos por temporada.
- `_archived_duplicates/`: partidos duplicados que `dedupe-matches --apply` movio aqui (nunca se
  borran, solo se sacan del set activo).
- `analytics/`: tablas derivadas que genera `build-analytics` (`match_results.csv`,
  `player_match_features.csv`, `player_season_summary.csv`), listas para leer desde un dashboard.
- `Descargar_temporada.ipynb`: notebook de apoyo para buscar equipos y descargar datos.
- `Consolidar_data.ipynb`: notebook de apoyo para consolidar el dataset final.

## Requisitos

- Python 3.10 o superior
- `pip`
- API key de API-Football para descargar datos nuevos

## Instalacion

El proyecto es un paquete instalable (`pyproject.toml` es la unica fuente de dependencias, no hay
`requirements.txt`). Instalalo en modo editable, con los extras de test:

```powershell
python -m pip install -e ".[dev]"
```

Con esto `python -m millos_data ...` y `import millos_data` funcionan desde cualquier carpeta, sin
necesidad de tocar `PYTHONPATH`. Si preferis no instalar el paquete, seguis pudiendo usar
`PYTHONPATH=src` como antes; los notebooks lo hacen asi.

`[dev]` ya incluye lo necesario para el dashboard (Streamlit, Plotly, DuckDB). Si solo queres esas
tres dependencias, sin `pytest`, instala el extra `dashboard`:

```powershell
python -m pip install -e ".[dashboard]"
```

## Git

El archivo `.env` esta ignorado en Git para evitar subir credenciales por accidente.

## Variables de entorno

Puedes usar un archivo `.env` en la raiz del repo (se busca subiendo desde el directorio actual, y
tambien en la raiz del repo como respaldo). Las variables ya definidas en el entorno siempre tienen
prioridad sobre el `.env`.

- `FOOTBALL_API_KEY`: obligatoria para descargas.
- `MILLONARIOS_TEAM_ID`: opcional, por defecto `1125`.
- `FOOTBALL_API_DELAY_SECONDS`: opcional, por defecto `1.0`.
- `FOOTBALL_API_BASE_URL`: opcional.
- `FOOTBALL_API_HOST`: opcional.

Ejemplo de `.env`:

```dotenv
FOOTBALL_API_KEY=tu_api_key
MILLONARIOS_TEAM_ID=1125
FOOTBALL_API_DELAY_SECONDS=1.0
```

Ejemplo en PowerShell:

```powershell
$env:FOOTBALL_API_KEY="tu_api_key"
$env:MILLONARIOS_TEAM_ID="1125"
$env:FOOTBALL_API_DELAY_SECONDS="1.0"
```

## Uso por CLI

### Ejecutar el modulo

```powershell
python -m millos_data --help
```

Tambien puedes usar el CLI explicito:

```powershell
python -m millos_data.cli --help
```

(Si no instalaste el paquete con `pip install -e .`, antepone `$env:PYTHONPATH="src"` a cada
comando.)

### Consolidar los JSON existentes

```powershell
python -m millos_data consolidate --base-path . --output dataset_millonarios_consolidado.csv
```

### Probar la consolidacion sin escribir archivo

```powershell
python -m millos_data consolidate --base-path . --dry-run
```

### Reconstruir el CSV desde cero

Ignora el CSV existente y lo regenera solo a partir de los JSON que hay en disco. Util despues de
archivar duplicados con `dedupe-matches`, porque el CSV anterior puede tener filas ya incorporadas
de archivos que ya no existen:

```powershell
python -m millos_data consolidate --base-path . --output dataset_millonarios_consolidado.csv --rebuild
```

### Consolidar a otra ruta de salida

```powershell
python -m millos_data consolidate --base-path . --output salida/millonarios.csv
```

### Descargar una temporada completa

```powershell
$env:FOOTBALL_API_KEY="tu_api_key"
python -m millos_data download-season --season 2025
```

La descarga informa cuantas fechas encontro, cuantas ya estaban descargadas y cuantas se bajaron
en la ejecucion actual (con logging por cada fixture, en vivo). Reintenta automaticamente ante
errores 429/5xx con backoff exponencial (respetando `Retry-After` si la API lo envia).

### Descargar una temporada a una carpeta personalizada

```powershell
$env:FOOTBALL_API_KEY="tu_api_key"
python -m millos_data download-season --season 2025 --output-dir data/2025
```

### Revisar y archivar partidos duplicados

Ver la seccion [Mantenimiento](#mantenimiento-partidos-duplicados-por-cambio-de-nombre-de-rival).

### Construir las tablas de analitica (para el dashboard)

Lee el CSV consolidado + los JSON en disco y escribe tres tablas en `analytics/`:

```powershell
python -m millos_data build-analytics --base-path .
```

- `match_results.csv`: un resultado por partido (incluye los partidos sin plantilla registrada,
  que `consolidate` descarta).
- `player_match_features.csv`: el dataset consolidado + columnas derivadas (`pases_precision_num`,
  `jugo`, tasas `*_por90`, `anio`).
- `player_season_summary.csv`: agregado por jugador x anio.

Correlo de nuevo cada vez que cambie `dataset_millonarios_consolidado.csv`. Ver
[docs/analytics_kpis.md](docs/analytics_kpis.md) para el detalle de cada metrica.

`build_player_match_features` fusiona automaticamente variantes de escritura del mismo jugador
(tildes/mayusculas, p. ej. "Daniel Ruiz" / "Daniel Ruíz"), eligiendo la grafia mas frecuente como
canonica. Ver [Validacion de datos](#validacion-de-datos) para revisar que casos detecto.

### Validar las tablas de analitica

```powershell
python -m millos_data validate-analytics --base-path .
```

Corre sanity checks sobre `match_results` y `player_match_features`: partidos duplicados, `puntos`
inconsistente con `resultado_partido`, minutos fuera de rango, stats negativos, reconciliacion de
goles del equipo vs. goles individuales de jugadores (un autogol del rival genera una diferencia de
1, es normal; mas de eso o una diferencia negativa se marca), y variantes de nombre de jugador ya
fusionadas automaticamente en `build_player_match_features` (te avisa cual eligio como canonica).

Sale con codigo de salida distinto de cero si hay algun `ERROR` (los `WARNING` no fallan el
comando). Utiles para correr despues de cada `build-analytics`, especialmente tras bajar una
temporada nueva.

### Refrescar todo de una

Encadena `consolidate` + `build-analytics` + `validate-analytics` (mas una revision de solo
lectura de partidos duplicados) en un solo comando. Es lo que corres despues de cada
`download-season`:

```powershell
python -m millos_data refresh --base-path .
```

```
consolidate: scanned_files=200 new_rows=0 total_rows=3110
analytics: match_results=200 player_match_features=3110 player_season_summary=120
validate: errors=0 warnings=1
  [WARNING] player_name_variants: ...
```

- Acepta `--rebuild` (se pasa a `consolidate`), `--dataset` y `--analytics-dir` (mismos defaults
  que los comandos individuales).
- Si `find_duplicate_matches` encuentra partidos duplicados nuevos, `refresh` los reporta pero
  **nunca mueve archivos** — eso sigue siendo `dedupe-matches --apply`, una accion explicita.
- `--strict` hace que el comando termine con codigo de salida distinto de cero si `validate`
  encuentra algun `ERROR` (util para un cron/CI que no deba seguir si los datos quedaron mal).

### Dashboard

Streamlit + DuckDB + Plotly, leyendo las tablas de `analytics/`:

```powershell
python -m millos_data refresh --base-path .   # o build-analytics, si no queres validar de nuevo
python -m millos_data dashboard
```

Abre el dashboard en el navegador (puerto 8501 por defecto, `--port` para cambiarlo). El sidebar
muestra la carpeta de datos y cuando se actualizaron por ultima vez (mtime de `match_results.csv`).
Tiene 4 vistas (ver [docs/analytics_kpis.md](docs/analytics_kpis.md) para la prioridad detras de
cada una):

1. **Equipo**: puntos acumulados, forma reciente (promedio movil de 5 partidos), goles a favor/en
   contra por partido, resumen por condicion (local/visitante) y por campeonato.
2. **Ranking de jugadores**: tabla y grafico de barras ordenable por goles/asistencias por 90',
   calificacion promedio, minutos, % de duelos ganados, filtrable por anio y posicion — con el
   promedio de la posicion como referencia (`promedio_posicion` / `vs_promedio_posicion`) y boton
   de descarga a CSV.
3. **Ficha de jugador**: calificacion y minutos partido a partido para un jugador elegido.
4. **Comparador**: 2+ jugadores (o el mismo jugador en distintos anios) lado a lado, con descarga
   a CSV.

Si preferis apuntar a otra carpeta de analitica (por ejemplo para probar con datos de otra
temporada sin pisar la carpeta `analytics/` principal):

```powershell
python -m millos_data dashboard --analytics-dir otra_carpeta/analytics --port 8502
```

`dashboard/data.py` es la unica capa que sabe consultar las tablas (via DuckDB); `dashboard/app.py`
solo arma la UI con esas funciones — si agregas una vista nueva, la query va primero en `data.py`
para que quede testeada sin depender de Streamlit.

## Uso desde Python

### Consolidar dataset

```python
from pathlib import Path

from millos_data import consolidate_dataset

result = consolidate_dataset(
    base_path=Path("."),
    output_path=Path("dataset_millonarios_consolidado.csv"),
    write_output=True,
)

print(result.scanned_files)
print(result.new_rows)
print(result.dataframe.head())
```

### Correr consolidacion en modo analisis

```python
from pathlib import Path

from millos_data import consolidate_dataset

result = consolidate_dataset(
    base_path=Path("."),
    output_path=Path("dataset_millonarios_consolidado.csv"),
    write_output=False,
)

df = result.dataframe
```

### Descargar una temporada

```python
from pathlib import Path

from millos_data import ApiConfig, download_season_matches, season_directory_name

config = ApiConfig.from_env()
stats = download_season_matches(
    config=config,
    season=2025,
    output_dir=Path(season_directory_name(2025)),
)

print(stats)
```

### Buscar equipos en la API

```python
from millos_data import ApiConfig, search_teams

config = ApiConfig.from_env()
teams = search_teams(config, "Millonarios")
print(teams)
```

### Detectar y archivar partidos duplicados

```python
from pathlib import Path

from millos_data import archive_duplicate_matches, find_duplicate_matches

# Solo reporte, no mueve nada:
scanned, groups, ambiguous = find_duplicate_matches(Path("."))

# Reporte + mover los duplicados confirmados a _archived_duplicates/:
result = archive_duplicate_matches(
    base_path=Path("."),
    archive_dir=Path("_archived_duplicates"),
    dry_run=False,
)
```

### Construir las tablas de analitica

```python
from pathlib import Path

from millos_data import (
    build_match_results,
    build_player_match_features,
    build_player_season_summary,
)
from millos_data.consolidate import read_existing_dataset

match_results = build_match_results(Path("."))
player_features = build_player_match_features(
    read_existing_dataset(Path("dataset_millonarios_consolidado.csv"))
)
season_summary = build_player_season_summary(player_features)
```

### Validar las tablas de analitica

```python
from pathlib import Path

from millos_data import run_validations

report = run_validations(
    base_path=Path("."),
    dataset_path=Path("dataset_millonarios_consolidado.csv"),
)

print(f"errors={len(report.errors)} warnings={len(report.warnings)}")
for issue in report.issues:
    print(issue.severity, issue.check, issue.message)
    print(issue.details)  # DataFrame con las filas involucradas
```

### Refrescar todo de una

```python
from pathlib import Path

from millos_data import run_refresh

result = run_refresh(
    base_path=Path("."),
    dataset_path=Path("dataset_millonarios_consolidado.csv"),
    analytics_output_dir=Path("analytics"),
)

print(result.consolidation.new_rows)
print(result.match_results_rows, result.player_match_features_rows, result.player_season_summary_rows)
print(result.validation.ok, len(result.validation.errors), len(result.validation.warnings))
```

## Uso desde notebooks

Los notebooks estan restaurados y usan los modulos nuevos.

### `Descargar_temporada.ipynb`

Incluye:

- carga de `src/` en `sys.path`
- lectura de `ApiConfig.from_env()`
- busqueda de equipos con `search_teams`
- descarga por temporada con `download_season_matches`

### `Consolidar_data.ipynb`

Incluye:

- carga de `src/` en `sys.path`
- consolidacion con `consolidate_dataset`
- impresion de metricas del proceso
- vista previa del dataframe consolidado

## Ejecutar tests

```powershell
python -m pip install -e ".[dev]"
pytest -q
```

En algunos entornos Anaconda, `pytest` intenta cargar plugins globales incompatibles. Si te pasa
eso:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
pytest -q
```

## Compatibilidad con datos existentes

- Los JSON historicos sin `fixture_id` siguen funcionando.
- El consolidado legacy en `utf-16` se puede leer sin migracion manual.
- Los nuevos CSV se escriben en `utf-8-sig`.
- Se agrega `match_id` para tener una clave estable por partido (prioriza `fixture_id`; si no
  existe, cae a `fecha:condicion:rival`).

## Restriccion del proyecto

- La descarga solo soporta Millonarios FC de Colombia masculino mayor.
- El `team_id` soportado es `1125`.
- El codigo esperado del equipo es `MIL`.
- Si en `.env` se configura otro `MILLONARIOS_TEAM_ID`, el proyecto falla de forma explicita.

## Archivos principales

- [src/millos_data/config.py](src/millos_data/config.py)
- [src/millos_data/extract.py](src/millos_data/extract.py)
- [src/millos_data/schema.py](src/millos_data/schema.py)
- [src/millos_data/transform.py](src/millos_data/transform.py)
- [src/millos_data/consolidate.py](src/millos_data/consolidate.py)
- [src/millos_data/dedupe.py](src/millos_data/dedupe.py)
- [src/millos_data/analytics.py](src/millos_data/analytics.py)
- [src/millos_data/validate.py](src/millos_data/validate.py)
- [src/millos_data/pipeline.py](src/millos_data/pipeline.py)
- [src/millos_data/dashboard/data.py](src/millos_data/dashboard/data.py)
- [src/millos_data/dashboard/app.py](src/millos_data/dashboard/app.py)
- [src/millos_data/cli.py](src/millos_data/cli.py)
- [docs/analytics_kpis.md](docs/analytics_kpis.md)

## Ideas para Fase 6 (analitica avanzada — no implementado)

Las Fases 0-5 cubren analitica descriptiva: que paso, y como se compara un jugador contra su
posicion. Estas ideas quedan para despues, una vez que las vistas actuales muestren que valen la
pena iterar mas alla de lo descriptivo:

- **Clustering de jugadores por estilo de juego**: K-means (u otro) sobre las stats normalizadas
  de `player_season_summary` (por 90', no absolutas) para encontrar perfiles de juego que no
  coinciden exactamente con la posicion formal (p. ej. un mediocampista mas "recuperador" vs. uno
  mas "de construccion").
- **Deteccion de tendencias/declive de rendimiento**: regresion o test de cambio de nivel sobre la
  serie de `calificacion` (o `goles_por90`) de cada jugador en el tiempo, para señalar caidas
  sostenidas — insumo para decisiones de rotacion, no solo para mirar el numero mas reciente.
- **Indice compuesto de "impacto"**: combinar goles + asistencias + duelos ganados + pases en un
  score ponderado por posicion (los pesos de un defensor y un delantero no deberian ser los
  mismos), para poder rankear jugadores de perfiles distintos con un solo numero.
- **Posicion real en la tabla de la liga**: hoy `match_results` solo tiene los partidos de
  Millonarios. Bajar la tabla de posiciones completa (endpoint de standings de API-Football)
  permitiria comparar la "forma" del equipo contra el resto de la liga, no solo contra si mismo —
  ver la limitacion documentada en [docs/analytics_kpis.md](docs/analytics_kpis.md).
- **Historial cabeza a cabeza vs. un rival especifico**: filtrar `match_results` por `rival` para
  ver el patron historico contra un equipo puntual antes de un partido.
- **Fatiga / congestion de calendario**: cruzar fechas de partidos consecutivos (dias de descanso
  entre partidos) contra `calificacion`/`minutos` para ver si el rendimiento cae con calendarios
  apretados.
- **Expected goals/assists (proxy)**: si la API expone eventos de tiro mas detallados (no
  explorado todavia — requeriria el endpoint de `events`, no solo `fixtures/players`), se podria
  aproximar un xG simple y comparar goles reales vs. esperados.
- **Alertas automaticas**: un check tipo `validate.py` pero de negocio, no de calidad de datos
  (p. ej. "jugador con calificacion promedio por debajo de X en los ultimos 5 partidos"),
  mostrado como aviso en el sidebar del dashboard.

## Mantenimiento: partidos duplicados por cambio de nombre de rival

La API a veces renombra un club a mitad de temporada (por ejemplo "Rionegro Aguilas" paso a
llamarse "Aguilas Doradas"). Antes, esto hacia que el mismo partido se descargara dos veces bajo
nombres de archivo distintos, y `consolidate` no detectaba el duplicado porque los JSON antiguos no
tienen `fixture_id`. Esto ya esta corregido para descargas nuevas: el nombre de archivo ahora
incluye el `fixture_id`, y antes de descargar se revisa si ese `fixture_id` ya existe en algun JSON
de la carpeta destino (ver `_collect_existing_fixture_ids` en `extract.py`), sin importar bajo que
nombre de rival haya quedado guardado.

Para revisar y limpiar datos historicos:

```powershell
python -m millos_data dedupe-matches --base-path .
```

Por defecto solo imprime un reporte (dry-run): agrupa los JSON por `(fecha, condicion, resultado)`
y, dentro de cada grupo con mas de un archivo, solo los confirma como duplicados si ademas tienen
el **mismo roster de jugadores** (esto evita falsos positivos, como dos partidos de torneos
distintos que coinciden en fecha y marcador por pura casualidad; esos casos quedan marcados como
"AMBIGUOUS" y no se tocan).

Para mover los archivos redundantes a `_archived_duplicates/` (nunca se borran) agrega `--apply`:

```powershell
python -m millos_data dedupe-matches --base-path . --apply
```

Despues de archivar duplicados, regenera el CSV desde cero con `--rebuild` (ver arriba), ya que el
CSV anterior puede tener filas duplicadas ya incorporadas de ejecuciones previas.
