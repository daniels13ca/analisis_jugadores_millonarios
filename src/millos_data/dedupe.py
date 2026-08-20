from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .consolidate import discover_json_files
from .transform import read_json_file


@dataclass
class DuplicateGroup:
    """A set of JSON files that describe the exact same real-world match.

    This happens when a fixture gets downloaded twice under different
    filenames, most commonly because the API renamed the rival club between
    two download runs (e.g. "Rionegro Aguilas" -> "Aguilas Doradas"). `kept`
    is the file considered canonical (it carries a `fixture_id`, or is the
    earliest match otherwise); everything else in `archived` is redundant.
    """

    key: tuple[str, str, str]
    kept: Path
    archived: list[Path]


@dataclass
class AmbiguousGroup:
    """Files that share (fecha, condicion, resultado) but whose player
    rosters don't match closely enough to be safely treated as the same
    match (e.g. two genuinely different competitions coinciding on the same
    date/scoreline). Left untouched, reported for manual review.
    """

    key: tuple[str, str, str]
    files: list[Path]


@dataclass
class DedupeResult:
    scanned_files: int
    duplicate_groups: list[DuplicateGroup] = field(default_factory=list)
    ambiguous_groups: list[AmbiguousGroup] = field(default_factory=list)
    dry_run: bool = True

    @property
    def archived_files(self) -> list[Path]:
        return [path for group in self.duplicate_groups for path in group.archived]


def _fixture_id(metadata: dict[str, Any]) -> Any:
    return metadata.get("fixture_id")


def _has_fixture_id(path: Path, metadata_by_file: dict[Path, dict[str, Any]]) -> bool:
    return _fixture_id(metadata_by_file[path]) not in (None, "")


def _pick_canonical(files: list[Path], metadata_by_file: dict[Path, dict[str, Any]]) -> Path:
    with_fixture_id = sorted(f for f in files if _has_fixture_id(f, metadata_by_file))
    if with_fixture_id:
        return with_fixture_id[0]
    return sorted(files)[0]


def _player_names(data: dict[str, Any]) -> frozenset[str]:
    players = data.get("jugadores") or data.get("plantilla") or []
    return frozenset(str(p.get("nombre", "")).strip() for p in players if p.get("nombre"))


def _same_match_content(files: list[Path], data_by_file: dict[Path, dict[str, Any]]) -> bool:
    """Guard against grouping two genuinely different matches that happen to
    share date/condicion/resultado by coincidence (it does happen when a
    league match and an international-cup match land on the same date).

    Requires the player rosters to be identical across all files in the
    group; a real duplicate (same fixture saved twice) always has an
    identical roster, while two unrelated matches essentially never do.
    """
    non_empty = [f for f in files if _player_names(data_by_file[f])]
    if len(non_empty) < 2:
        # Can't compare rosters (e.g. both files have 0 jugadores). Fall
        # back to trusting the (fecha, condicion, resultado) match.
        return True
    reference = _player_names(data_by_file[non_empty[0]])
    return all(_player_names(data_by_file[f]) == reference for f in non_empty[1:])


def find_duplicate_matches(
    base_path: Path,
) -> tuple[int, list[DuplicateGroup], list[AmbiguousGroup]]:
    """Group JSON match files by (fecha, condicion, resultado), then confirm
    each group with an exact-roster check before calling it a duplicate.

    A single team cannot legitimately play two different matches with the
    same date, home/away condition and final score, so any group with more
    than one file is initially suspicious. But that alone is not proof: two
    different competitions can coincide on the same date/scoreline, so we
    only call it a true duplicate when the player rosters also match
    exactly. Groups that fail that check are reported as ambiguous instead
    of being archived.
    """
    files = discover_json_files(base_path)
    metadata_by_file: dict[Path, dict[str, Any]] = {}
    data_by_file: dict[Path, dict[str, Any]] = {}
    by_key: dict[tuple[str, str, str], list[Path]] = {}

    for path in files:
        data = read_json_file(path)
        metadata = data.get("metadata", {})
        metadata_by_file[path] = metadata
        data_by_file[path] = data

        fecha = str(metadata.get("fecha", "")).strip()
        condicion = str(metadata.get("condicion", "")).strip()
        resultado = str(metadata.get("resultado", "")).strip()
        if not fecha or not condicion or not resultado:
            continue

        by_key.setdefault((fecha, condicion, resultado), []).append(path)

    groups: list[DuplicateGroup] = []
    ambiguous: list[AmbiguousGroup] = []
    for key, group_files in sorted(by_key.items()):
        if len(group_files) <= 1:
            continue

        if not _same_match_content(group_files, data_by_file):
            ambiguous.append(AmbiguousGroup(key=key, files=sorted(group_files)))
            continue

        canonical = _pick_canonical(group_files, metadata_by_file)
        duplicates = sorted(f for f in group_files if f != canonical)
        groups.append(DuplicateGroup(key=key, kept=canonical, archived=duplicates))

    return len(files), groups, ambiguous


def archive_duplicate_matches(
    base_path: Path,
    archive_dir: Path,
    dry_run: bool = True,
) -> DedupeResult:
    scanned_files, groups, ambiguous = find_duplicate_matches(base_path)

    if not dry_run:
        for group in groups:
            for duplicate in group.archived:
                relative = duplicate.relative_to(base_path)
                destination = archive_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(duplicate), str(destination))

    return DedupeResult(
        scanned_files=scanned_files,
        duplicate_groups=groups,
        ambiguous_groups=ambiguous,
        dry_run=dry_run,
    )
