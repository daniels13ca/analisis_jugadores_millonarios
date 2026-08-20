import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def make_player(
    nombre: str,
    posicion: str = "M",
    minutos: int = 90,
    calificacion: str | float | None = "7.0",
    titular: bool = True,
    **rendimiento_overrides: Any,
) -> dict[str, Any]:
    """Build a player dict shaped like what extract.py writes to disk.

    Pass performance overrides as flat kwargs matching the top-level
    `rendimiento` keys, e.g. make_player("X", goles=1, pases={"totales": 30}).
    """
    rendimiento: dict[str, Any] = {
        "goles": 0,
        "asistencias": 0,
        "remates_totales": 0,
        "remates_al_arco": 0,
        "pases": {"totales": 0, "precision": "0%"},
        "defensa": {"entradas": 0, "intercepciones": 0, "despejes": 0},
        "duelos": {"totales": 0, "ganados": 0},
        "faltas": {"cometidas": 0, "recibidas": 0},
        "tarjetas": {"amarilla": 0, "roja": 0},
    }
    rendimiento.update(rendimiento_overrides)

    return {
        "nombre": nombre,
        "posicion": posicion,
        "minutos": minutos,
        "calificacion": calificacion,
        "titular": titular,
        "rendimiento": rendimiento,
    }


def make_match_payload(
    fecha: str,
    condicion: str,
    resultado: str,
    rival: str = "Rival FC",
    campeonato: str = "Primera A",
    fixture_id: int | None = None,
    jugadores: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a match JSON payload shaped like what extract.py writes to disk."""
    metadata: dict[str, Any] = {
        "fecha": fecha,
        "condicion": condicion,
        "resultado": resultado,
        "rival": rival,
        "campeonato": campeonato,
    }
    if fixture_id is not None:
        metadata["fixture_id"] = fixture_id

    return {"metadata": metadata, "jugadores": jugadores if jugadores is not None else []}


def write_match_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
