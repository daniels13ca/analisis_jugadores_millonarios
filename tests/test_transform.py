from pathlib import Path

from conftest import make_match_payload, make_player, write_match_json

from millos_data.transform import build_match_id, flatten_match_file


def test_build_match_id_from_metadata_without_fixture_id() -> None:
    match_id = build_match_id(
        {"fecha": "2024-01-19", "rival": "Junior", "condicion": "Visitante"}
    )
    assert match_id == "match:2024-01-19:visitante:junior"


def test_flatten_match_file_returns_expected_columns(tmp_path: Path) -> None:
    sample = write_match_json(
        tmp_path / "2024-01-19_Visitante_Junior.json",
        make_match_payload(
            fecha="2024-01-19",
            condicion="Visitante",
            resultado="1 - 0",
            rival="Junior",
            campeonato="Superliga",
            jugadores=[
                make_player(
                    "Jugador Uno",
                    calificacion="7.1",
                    goles=1,
                    remates_totales=2,
                    remates_al_arco=1,
                    pases={"totales": 30, "precision": "80%"},
                    defensa={"entradas": 1, "intercepciones": 2, "despejes": 0},
                    duelos={"totales": 4, "ganados": 3},
                    faltas={"cometidas": 1, "recibidas": 2},
                )
            ],
        ),
    )

    rows = flatten_match_file(sample)

    assert len(rows) == 1
    assert rows[0]["match_id"] == "match:2024-01-19:visitante:junior"
    assert rows[0]["jugador"] == "Jugador Uno"
    assert rows[0]["pases_precision"] == "80%"
    assert rows[0]["goles"] == 1
