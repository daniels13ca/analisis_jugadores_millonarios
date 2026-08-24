"""Fase 2 — sanity checks over the analytics tables.

These are internal-consistency checks (no external "ground truth" file is
available), designed to catch the kind of problem this project has already
hit once for real: duplicated matches, a metric that doesn't reconcile with
another metric derived from the same underlying data, or a player split
across two spellings of their name.

Each check returns zero or more `ValidationIssue`s instead of raising, so a
single bad row doesn't stop the rest of the report from running.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .analytics import build_match_results, build_player_match_features, normalize_name_key
from .consolidate import read_existing_dataset

# Columns that should never be negative in the player-match dataset.
NON_NEGATIVE_COLUMNS = [
    "minutos",
    "goles",
    "asistencias",
    "remates_totales",
    "remates_al_arco",
    "pases_totales",
    "entradas",
    "intercepciones",
    "despejes",
    "duelos_totales",
    "duelos_ganados",
    "faltas_cometidas",
    "faltas_recibidas",
    "amarillas",
    "rojas",
]

# A regular match is 90 minutes; cup fixtures with extra time can run to
# ~120. Anything past that is almost certainly a data error.
MAX_PLAUSIBLE_MINUTES = 130

# "goles" scored by Millonarios players will fall short of the team's
# goles_favor by exactly the number of rival own-goals in that match. One
# own goal per match is common; more than that is worth a manual look.
MAX_EXPECTED_GOAL_GAP = 1

# Millonarios plays every match either at home or away -- there's no third
# option. See config.ApiConfig / extract.build_fixture_payload, which only
# ever writes one of these two values.
VALID_CONDICIONES = {"Local", "Visitante"}


@dataclass
class ValidationIssue:
    check: str
    severity: str  # "error" (data is wrong/impossible) or "warning" (worth a look)
    message: str
    details: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class ValidationReport:
    issues: list[ValidationIssue]

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        """True if there are no *errors*. Warnings don't fail the build."""
        return not self.errors


def check_no_duplicate_match_ids(match_results: pd.DataFrame) -> list[ValidationIssue]:
    counts = match_results["match_id"].value_counts()
    duplicated = counts[counts > 1]
    if duplicated.empty:
        return []
    return [
        ValidationIssue(
            check="no_duplicate_match_ids",
            severity="error",
            message=f"{len(duplicated)} match_id aparecen mas de una vez en match_results",
            details=duplicated.rename("apariciones").reset_index(),
        )
    ]


def check_points_consistency(match_results: pd.DataFrame) -> list[ValidationIssue]:
    with_outcome = match_results[match_results["resultado_partido"].notna()]
    expected_points = with_outcome["resultado_partido"].map({"W": 3, "D": 1, "L": 0})
    mismatched = with_outcome[with_outcome["puntos"] != expected_points]
    if mismatched.empty:
        return []
    return [
        ValidationIssue(
            check="points_consistency",
            severity="error",
            message=f"{len(mismatched)} partidos con `puntos` inconsistente con `resultado_partido`",
            details=mismatched,
        )
    ]


def check_minutes_within_bounds(player_features: pd.DataFrame) -> list[ValidationIssue]:
    minutes = pd.to_numeric(player_features["minutos"], errors="coerce")
    out_of_bounds = player_features[(minutes < 0) | (minutes > MAX_PLAUSIBLE_MINUTES)]
    if out_of_bounds.empty:
        return []
    return [
        ValidationIssue(
            check="minutes_within_bounds",
            severity="warning",
            message=(
                f"{len(out_of_bounds)} filas con minutos fuera de "
                f"[0, {MAX_PLAUSIBLE_MINUTES}]"
            ),
            details=out_of_bounds,
        )
    ]


def check_condicion_valid(match_results: pd.DataFrame) -> list[ValidationIssue]:
    """Every match must be Local or Visitante for Millonarios -- no third option.

    A missing/blank/misspelled condicion silently breaks every home/away
    split (team_summary by condicion, the Partidos tab filter, the win/draw/
    loss cards) for that match instead of raising anywhere, so it's worth
    catching explicitly rather than relying on those views looking "a little
    off".
    """
    invalid = match_results[~match_results["condicion"].isin(VALID_CONDICIONES)]
    if invalid.empty:
        return []
    return [
        ValidationIssue(
            check="condicion_valid",
            severity="error",
            message=(
                f"{len(invalid)} partido(s) sin `condicion` valida "
                f"(debe ser 'Local' o 'Visitante')"
            ),
            details=invalid,
        )
    ]


def check_no_negative_stats(player_features: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for column in NON_NEGATIVE_COLUMNS:
        if column not in player_features.columns:
            continue
        values = pd.to_numeric(player_features[column], errors="coerce")
        negative = player_features[values < 0]
        if not negative.empty:
            issues.append(
                ValidationIssue(
                    check=f"non_negative:{column}",
                    severity="error",
                    message=f"{len(negative)} filas con `{column}` negativo",
                    details=negative,
                )
            )
    return issues


def check_team_goals_reconciliation(
    match_results: pd.DataFrame, player_features: pd.DataFrame
) -> list[ValidationIssue]:
    """goles_favor (team result) vs sum(goles) (individual scorers).

    A gap of exactly N means N goals in that match aren't attributed to any
    Millonarios player -- expected for rival own-goals. A *negative* gap
    (players credited with more goals than the team actually scored) can
    never happen with real data and points at a consolidation bug.
    """
    goals_by_scorers = player_features.groupby("match_id")["goles"].sum()
    merged = match_results.set_index("match_id")[["fecha", "rival", "goles_favor"]].join(
        goals_by_scorers, how="inner"
    )
    merged["gap"] = merged["goles_favor"] - merged["goles"]

    issues: list[ValidationIssue] = []

    impossible = merged[merged["gap"] < 0]
    if not impossible.empty:
        issues.append(
            ValidationIssue(
                check="team_goals_reconciliation",
                severity="error",
                message=(
                    f"{len(impossible)} partidos con mas goles de jugadores que "
                    "goles_favor del equipo (imposible)"
                ),
                details=impossible.reset_index(),
            )
        )

    unexpected_gap = merged[merged["gap"] > MAX_EXPECTED_GOAL_GAP]
    if not unexpected_gap.empty:
        issues.append(
            ValidationIssue(
                check="team_goals_reconciliation",
                severity="warning",
                message=(
                    f"{len(unexpected_gap)} partidos con diferencia > {MAX_EXPECTED_GOAL_GAP} "
                    "entre goles_favor y goles de jugadores (autogol multiple o dato faltante?)"
                ),
                details=unexpected_gap.reset_index(),
            )
        )

    return issues


def check_player_name_variants(player_match_df: pd.DataFrame) -> list[ValidationIssue]:
    """Flag names that only differ by accents/case/spacing.

    Run this against the *raw* consolidated dataset, not the output of
    build_player_match_features -- that function already calls
    canonicalize_player_names to merge these variants, so checking its
    output would never find anything. Surfacing them here tells you what got
    auto-merged, in case the "most frequent spelling wins" heuristic picked
    the wrong one for a given name.
    """
    names = player_match_df["jugador"].dropna().unique()
    groups: dict[str, set[str]] = {}
    for name in names:
        groups.setdefault(normalize_name_key(name), set()).add(name)

    conflicting = {key: variants for key, variants in groups.items() if len(variants) > 1}
    if not conflicting:
        return []

    details = pd.DataFrame(
        {
            "variantes": [", ".join(sorted(variants)) for variants in conflicting.values()],
        }
    )
    return [
        ValidationIssue(
            check="player_name_variants",
            severity="warning",
            message=(
                f"{len(conflicting)} nombre(s) con mas de una variante de escritura "
                "(build_player_match_features ya los fusiona automaticamente; revisar que "
                "la variante elegida como canonica sea la correcta)"
            ),
            details=details,
        )
    ]


def run_validations(base_path: Path, dataset_path: Path) -> ValidationReport:
    match_results = build_match_results(base_path)
    player_match_df = read_existing_dataset(dataset_path)
    player_features = build_player_match_features(player_match_df)

    issues: list[ValidationIssue] = [
        *check_no_duplicate_match_ids(match_results),
        *check_points_consistency(match_results),
        *check_condicion_valid(match_results),
        *check_minutes_within_bounds(player_features),
        *check_no_negative_stats(player_features),
        *check_team_goals_reconciliation(match_results, player_features),
        *check_player_name_variants(player_match_df),
    ]

    return ValidationReport(issues=issues)
