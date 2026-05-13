from pathlib import Path

from millos_data.consolidate import consolidate_dataset


def test_consolidate_dataset_skips_empty_matches(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2024_Stats_Detalladas"
    stats_dir.mkdir()

    populated = stats_dir / "2024-01-19_Visitante_Junior.json"
    populated.write_text(
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

    empty_match = stats_dir / "2024-01-25_Local_Junior.json"
    empty_match.write_text(
        """
        {
          "metadata": {
            "fecha": "2024-01-25",
            "rival": "Junior",
            "condicion": "Local",
            "campeonato": "Superliga",
            "resultado": "0 - 0"
          },
          "jugadores": []
        }
        """.strip(),
        encoding="utf-8",
    )

    output = tmp_path / "dataset.csv"
    result = consolidate_dataset(tmp_path, output)

    assert result.scanned_files == 2
    assert result.empty_matches == 1
    assert result.new_rows == 1
    assert output.exists()
    assert len(result.dataframe) == 1
