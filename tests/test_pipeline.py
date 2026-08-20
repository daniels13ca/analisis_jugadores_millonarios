from pathlib import Path

from conftest import make_match_payload, make_player, write_match_json

from millos_data.pipeline import run_refresh


def test_run_refresh_produces_dataset_and_analytics(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2024_Stats_Detalladas"

    write_match_json(
        stats_dir / "2024-01-19_Visitante_Junior.json",
        make_match_payload(
            "2024-01-19",
            "Visitante",
            "0 - 1",
            rival="Junior",
            jugadores=[make_player("Jugador Uno", goles=1)],
        ),
    )
    write_match_json(
        stats_dir / "2024-01-25_Local_Junior.json",
        make_match_payload("2024-01-25", "Local", "0 - 0", rival="Junior", jugadores=[]),
    )

    dataset_path = tmp_path / "dataset.csv"
    analytics_dir = tmp_path / "analytics"

    result = run_refresh(
        base_path=tmp_path,
        dataset_path=dataset_path,
        analytics_output_dir=analytics_dir,
    )

    assert dataset_path.exists()
    assert (analytics_dir / "match_results.csv").exists()
    assert (analytics_dir / "player_match_features.csv").exists()
    assert (analytics_dir / "player_season_summary.csv").exists()

    assert result.consolidation.new_rows == 1
    # Both matches (one with player stats, one without) show up in match_results.
    assert result.match_results_rows == 2
    assert result.player_match_features_rows == 1
    assert result.duplicate_match_groups == 0
    assert result.ambiguous_match_groups == 0
    assert result.validation.ok


def test_run_refresh_reports_duplicate_matches_without_moving_files(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2024_Stats_Detalladas"
    roster = [make_player("Jugador Uno")]

    legacy = write_match_json(
        stats_dir / "2024-02-16_Local_Rionegro_Aguilas.json",
        make_match_payload("2024-02-16", "Local", "0 - 1", rival="Rionegro Aguilas", jugadores=roster),
    )
    write_match_json(
        stats_dir / "2024-02-16_Local_Aguilas_Doradas.json",
        make_match_payload(
            "2024-02-16", "Local", "0 - 1", rival="Aguilas Doradas", jugadores=roster, fixture_id=1153126
        ),
    )

    result = run_refresh(
        base_path=tmp_path,
        dataset_path=tmp_path / "dataset.csv",
        analytics_output_dir=tmp_path / "analytics",
    )

    assert result.duplicate_match_groups == 1
    # run_refresh never moves files -- that stays an explicit `dedupe-matches --apply` step.
    assert legacy.exists()


def test_run_refresh_can_skip_writing_analytics_files(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2024_Stats_Detalladas"
    write_match_json(
        stats_dir / "2024-01-19_Visitante_Junior.json",
        make_match_payload("2024-01-19", "Visitante", "0 - 1", rival="Junior", jugadores=[make_player("X")]),
    )

    analytics_dir = tmp_path / "analytics"
    run_refresh(
        base_path=tmp_path,
        dataset_path=tmp_path / "dataset.csv",
        analytics_output_dir=analytics_dir,
        write_analytics=False,
    )

    assert not analytics_dir.exists()
