"""Fase 5 — end-to-end orchestration.

One function/command that chains everything downstream of new JSON match
files: consolidate the JSON into the player-match CSV, rebuild the
analytics tables from it, and run the sanity checks -- so after
`download-season` (or after manually adding JSON files), a single command
leaves the dashboard's data current.

Duplicate-match detection is included as a *read-only* check (never moves
files here) -- `dedupe-matches --apply` stays a deliberate, explicit step,
since moving files is something a human should trigger on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .analytics import build_match_results, build_player_match_features, build_player_season_summary
from .consolidate import ConsolidationResult, consolidate_dataset
from .dedupe import find_duplicate_matches
from .validate import ValidationReport, run_validations


@dataclass
class RefreshResult:
    consolidation: ConsolidationResult
    match_results_rows: int
    player_match_features_rows: int
    player_season_summary_rows: int
    validation: ValidationReport
    duplicate_match_groups: int
    ambiguous_match_groups: int


def run_refresh(
    base_path: Path,
    dataset_path: Path,
    analytics_output_dir: Path,
    rebuild: bool = False,
    write_analytics: bool = True,
) -> RefreshResult:
    consolidation = consolidate_dataset(
        base_path=base_path,
        output_path=dataset_path,
        write_output=True,
        rebuild=rebuild,
    )

    _, duplicate_groups, ambiguous_groups = find_duplicate_matches(base_path)

    match_results = build_match_results(base_path)
    player_features = build_player_match_features(consolidation.dataframe)
    season_summary = build_player_season_summary(player_features)

    if write_analytics:
        analytics_output_dir.mkdir(parents=True, exist_ok=True)
        match_results.to_csv(analytics_output_dir / "match_results.csv", index=False, encoding="utf-8-sig")
        player_features.to_csv(
            analytics_output_dir / "player_match_features.csv", index=False, encoding="utf-8-sig"
        )
        season_summary.to_csv(
            analytics_output_dir / "player_season_summary.csv", index=False, encoding="utf-8-sig"
        )

    validation = run_validations(base_path=base_path, dataset_path=dataset_path)

    return RefreshResult(
        consolidation=consolidation,
        match_results_rows=len(match_results),
        player_match_features_rows=len(player_features),
        player_season_summary_rows=len(season_summary),
        validation=validation,
        duplicate_match_groups=len(duplicate_groups),
        ambiguous_match_groups=len(ambiguous_groups),
    )
