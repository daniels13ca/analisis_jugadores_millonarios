from pathlib import Path

from millos_data.transform import build_match_id, flatten_match_file


def test_build_match_id_from_metadata_without_fixture_id() -> None:
    match_id = build_match_id(
        {"fecha": "2024-01-19", "rival": "Junior", "condicion": "Visitante"}
    )
    assert match_id == "match:2024-01-19:visitante:junior"


def test_flatten_match_file_returns_expected_columns(tmp_path: Path) -> None:
    sample = tmp_path / "2024-01-19_Visitante_Junior.json"
    sample.write_text(
        """
        {
          "metadata": {
            "fecha": "2024-01-19",
            "rival": "Junior",
            "condicion": "Visitante",
            "campeonato": "Superliga",
            "resultado": "1 - 0"
          },
          "jugadores": [
            {
              "nombre": "Jugador Uno",
              "posicion": "M",
              "minutos": 90,
              "calificacion": "7.1",
              "titular": true,
              "rendimiento": {
                "goles": 1,
                "asistencias": 0,
                "remates_totales": 2,
                "remates_al_arco": 1,
                "pases": {"totales": 30, "precision": "80%"},
                "defensa": {"entradas": 1, "intercepciones": 2, "despejes": 0},
                "duelos": {"totales": 4, "ganados": 3},
                "faltas": {"cometidas": 1, "recibidas": 2},
                "tarjetas": {"amarilla": 0, "roja": 0}
              }
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    rows = flatten_match_file(sample)

    assert len(rows) == 1
    assert rows[0]["match_id"] == "match:2024-01-19:visitante:junior"
    assert rows[0]["jugador"] == "Jugador Uno"
    assert rows[0]["pases_precision"] == "80%"
