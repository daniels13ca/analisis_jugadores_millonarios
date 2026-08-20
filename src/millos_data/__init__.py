"""Utilities for downloading and consolidating Millonarios player stats."""

from .analytics import (
    build_match_results,
    build_player_match_features,
    build_player_season_summary,
)
from .config import ApiConfig, season_directory_name
from .consolidate import consolidate_dataset
from .dedupe import archive_duplicate_matches, find_duplicate_matches
from .extract import download_season_matches, search_teams
from .pipeline import RefreshResult, run_refresh
from .validate import ValidationReport, run_validations

__all__ = [
    "ApiConfig",
    "RefreshResult",
    "ValidationReport",
    "archive_duplicate_matches",
    "build_match_results",
    "build_player_match_features",
    "build_player_season_summary",
    "consolidate_dataset",
    "download_season_matches",
    "find_duplicate_matches",
    "run_refresh",
    "run_validations",
    "search_teams",
    "season_directory_name",
]
