# Analisis Jugadores Millonarios

Refactor del flujo original basado en notebooks hacia un paquete Python reutilizable.

## Estructura

- `src/millos_data/`: logica de configuracion, descarga, transformacion y consolidacion.
- `tests/`: pruebas unitarias para normalizacion y consolidacion.
- `Millonarios_*_Stats_Detalladas/`: datos JSON historicos por temporada.
- `Descargar_temporada.ipynb`: notebook de apoyo para buscar equipos y descargar datos.
- `Consolidar_data.ipynb`: notebook de apoyo para consolidar el dataset final.

## Requisitos

- Python 3.10 o superior
- `pip`
- API key de API-Football para descargar datos nuevos

## Instalacion

```powershell
python -m pip install -r requirements.txt
```

Si prefieres trabajar sin instalar el paquete, usa `PYTHONPATH=src` en los ejemplos de CLI.

## Git

El archivo `.env` esta ignorado en Git para evitar subir credenciales por accidente.

## Variables de entorno

Puedes usar un archivo `.env` en la raiz del repo.

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
$env:PYTHONPATH="src"
python -m millos_data --help
```

Tambien puedes usar el CLI explicito:

```powershell
$env:PYTHONPATH="src"
python -m millos_data.cli --help
```

### Consolidar los JSON existentes

```powershell
$env:PYTHONPATH="src"
python -m millos_data consolidate --base-path . --output dataset_millonarios_consolidado.csv
```

### Probar la consolidacion sin escribir archivo

```powershell
$env:PYTHONPATH="src"
python -m millos_data consolidate --base-path . --dry-run
```

### Consolidar a otra ruta de salida

```powershell
$env:PYTHONPATH="src"
python -m millos_data consolidate --base-path . --output salida/millonarios.csv
```

### Descargar una temporada completa

```powershell
$env:PYTHONPATH="src"
$env:FOOTBALL_API_KEY="tu_api_key"
python -m millos_data download-season --season 2025
```

### Descargar una temporada a una carpeta personalizada

```powershell
$env:PYTHONPATH="src"
$env:FOOTBALL_API_KEY="tu_api_key"
python -m millos_data download-season --season 2025 --output-dir data/2025
```

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

from millos_data import ApiConfig, download_season_matches

config = ApiConfig.from_env()
stats = download_season_matches(
    config=config,
    season=2025,
    output_dir=Path("Millonarios_2025_Stats_Detalladas"),
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

En algunos entornos Anaconda, `pytest` intenta cargar plugins globales incompatibles. Si te pasa eso:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
pytest -q
```

## Compatibilidad con datos existentes

- Los JSON historicos sin `fixture_id` siguen funcionando.
- El consolidado legacy en `utf-16` se puede leer sin migracion manual.
- Los nuevos CSV se escriben en `utf-8-sig`.
- Se agrega `match_id` para tener una clave estable por partido.

## Restriccion del proyecto

- La descarga solo soporta Millonarios FC de Colombia masculino mayor.
- El `team_id` soportado es `1125`.
- El codigo esperado del equipo es `MIL`.
- Si en `.env` se configura otro `MILLONARIOS_TEAM_ID`, el proyecto falla de forma explicita.
- La descarga informa cuantas fechas encontro, cuantas ya estaban descargadas y cuantas se bajaron en la ejecucion actual.

## Archivos principales

- [src/millos_data/config.py](/d:/Repositorios/analisis_jugadores_millonarios/src/millos_data/config.py)
- [src/millos_data/extract.py](/d:/Repositorios/analisis_jugadores_millonarios/src/millos_data/extract.py)
- [src/millos_data/transform.py](/d:/Repositorios/analisis_jugadores_millonarios/src/millos_data/transform.py)
- [src/millos_data/consolidate.py](/d:/Repositorios/analisis_jugadores_millonarios/src/millos_data/consolidate.py)
- [src/millos_data/cli.py](/d:/Repositorios/analisis_jugadores_millonarios/src/millos_data/cli.py)
