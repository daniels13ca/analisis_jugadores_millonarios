from pathlib import Path

from conftest import make_match_payload, make_player, write_match_json

from millos_data.consolidate import consolidate_dataset


def test_consolidate_dataset_skips_empty_matches(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2024_Stats_Detalladas"

    write_match_json(
        stats_dir / "2024-01-19_Visitante_Junior.json",
        make_match_payload(
            fecha="2024-01-19",
            condicion="Visitante",
            resultado="1 - 0",
            rival="Junior",
            campeonato="Superliga",
            jugadores=[make_player("Jugador Uno", goles=1)],
        ),
    )
    write_match_json(
        stats_dir / "2024-01-25_Local_Junior.json",
        make_match_payload(
            fecha="2024-01-25",
            condicion="Local",
            resultado="0 - 0",
            rival="Junior",
            campeonato="Superliga",
            jugadores=[],
        ),
    )

    output = tmp_path / "dataset.csv"
    result = consolidate_dataset(tmp_path, output)

    assert result.scanned_files == 2
    assert result.empty_matches == 1
    assert result.new_rows == 1
    assert output.exists()
    assert len(result.dataframe) == 1


def test_consolidate_dataset_rebuild_ignores_existing_csv(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2024_Stats_Detalladas"
    write_match_json(
        stats_dir / "2024-01-19_Visitante_Junior.json",
        make_match_payload(
            fecha="2024-01-19",
            condicion="Visitante",
            resultado="1 - 0",
            rival="Junior",
            jugadores=[make_player("Jugador Uno", goles=1)],
        ),
    )

    output = tmp_path / "dataset.csv"

    # A stale CSV with a row that no longer has a matching JSON file on disk
    # (e.g. it was left over from an archived duplicate).
    output.write_text(
        "match_id,source_file,fecha,campeonato,rival,condicion,resultado,jugador,posicion,minutos,"
        "calificacion,titular,goles,asistencias,remates_totales,remates_al_arco,pases_totales,"
        "pases_precision,entradas,intercepciones,despejes,duelos_totales,duelos_ganados,"
        "faltas_cometidas,faltas_recibidas,amarillas,rojas\n"
        "match:stale,old.json,2020-01-01,Superliga,Ghost,Local,0 - 0,Fantasma,M,90,7.0,True,"
        "0,0,0,0,0,0%,0,0,0,0,0,0,0,0,0\n",
        encoding="utf-8",
    )

    result = consolidate_dataset(tmp_path, output, rebuild=True)

    assert "match:stale" not in set(result.dataframe["match_id"])
    assert len(result.dataframe) == 1
    assert result.dataframe.iloc[0]["jugador"] == "Jugador Uno"
