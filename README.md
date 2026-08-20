# Analisis Jugadores Millonarios

Paquete Python para descargar, transformar y consolidar estadisticas de jugadores de
Millonarios FC a partir de la API de API-Football.

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
  - `cli.py`: comandos `consolidate`, `download-season` y `dedupe-matches`.
- `tests/`: pruebas unitarias, con un factory compartido en `conftest.py` para construir JSON de
  partidos de prueba.
- `Millonarios_*_Stats_Detalladas/`: datos JSON historicos por temporada.
- `_archived_duplicates/`: partidos duplicados que `dedupe-matches --apply` movio aqui (nunca se
  borran, solo se sacan del set activo).
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
- [src/millos_data/cli.py](src/millos_data/cli.py)

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
