from pathlib import Path

from conftest import make_match_payload, make_player, write_match_json

from millos_data.dedupe import archive_duplicate_matches, find_duplicate_matches


def test_find_duplicate_matches_detects_rename_with_identical_roster(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2024_Stats_Detalladas"
    roster = [make_player("Player A"), make_player("Player B"), make_player("Player C")]

    write_match_json(
        stats_dir / "2024-02-16_Local_Rionegro_Aguilas.json",
        make_match_payload("2024-02-16", "Local", "0 - 1", rival="Rionegro Aguilas", jugadores=roster),
    )
    write_match_json(
        stats_dir / "2024-02-16_Local_Aguilas_Doradas.json",
        make_match_payload(
            "2024-02-16", "Local", "0 - 1", rival="Aguilas Doradas", jugadores=roster, fixture_id=1153126
        ),
    )

    scanned, groups, ambiguous = find_duplicate_matches(tmp_path)

    assert scanned == 2
    assert ambiguous == []
    assert len(groups) == 1
    group = groups[0]
    assert group.kept.name == "2024-02-16_Local_Aguilas_Doradas.json"
    assert [f.name for f in group.archived] == ["2024-02-16_Local_Rionegro_Aguilas.json"]


def test_find_duplicate_matches_leaves_coincidental_same_date_matches_alone(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2023_Stats_Detalladas"

    write_match_json(
        stats_dir / "2023-05-04_Local_America_Mineiro.json",
        make_match_payload(
            "2023-05-04",
            "Local",
            "1 - 1",
            rival="America Mineiro",
            jugadores=[make_player("Player A"), make_player("Player B"), make_player("Player X")],
        ),
    )
    write_match_json(
        stats_dir / "2023-05-04_Local_Envigado.json",
        make_match_payload(
            "2023-05-04",
            "Local",
            "1 - 1",
            rival="Envigado",
            jugadores=[make_player("Player A"), make_player("Player B")],
        ),
    )

    scanned, groups, ambiguous = find_duplicate_matches(tmp_path)

    assert scanned == 2
    assert groups == []
    assert len(ambiguous) == 1
    assert {f.name for f in ambiguous[0].files} == {
        "2023-05-04_Local_America_Mineiro.json",
        "2023-05-04_Local_Envigado.json",
    }


def test_archive_duplicate_matches_moves_only_confirmed_duplicates(tmp_path: Path) -> None:
    stats_dir = tmp_path / "Millonarios_2024_Stats_Detalladas"
    roster = [make_player("Player A"), make_player("Player B")]

    legacy = write_match_json(
        stats_dir / "2024-02-16_Local_Rionegro_Aguilas.json",
        make_match_payload("2024-02-16", "Local", "0 - 1", rival="Rionegro Aguilas", jugadores=roster),
    )
    canonical = write_match_json(
        stats_dir / "2024-02-16_Local_Aguilas_Doradas.json",
        make_match_payload(
            "2024-02-16", "Local", "0 - 1", rival="Aguilas Doradas", jugadores=roster, fixture_id=1153126
        ),
    )

    archive_dir = tmp_path / "_archived_duplicates"

    dry_run_result = archive_duplicate_matches(tmp_path, archive_dir, dry_run=True)
    assert dry_run_result.dry_run is True
    assert len(dry_run_result.archived_files) == 1
    assert legacy.exists()  # nothing moved yet
    assert not archive_dir.exists()

    applied_result = archive_duplicate_matches(tmp_path, archive_dir, dry_run=False)
    assert applied_result.dry_run is False
    assert not legacy.exists()
    assert canonical.exists()
    assert (archive_dir / "Millonarios_2024_Stats_Detalladas" / legacy.name).exists()
