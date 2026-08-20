import pandas as pd

from millos_data.validate import (
    check_minutes_within_bounds,
    check_no_duplicate_match_ids,
    check_no_negative_stats,
    check_player_name_variants,
    check_points_consistency,
    check_team_goals_reconciliation,
)


def make_match_results(**overrides) -> pd.DataFrame:
    base = {
        "match_id": ["m1", "m2"],
        "fecha": ["2024-01-19", "2024-01-25"],
        "rival": ["Junior", "Santa Fe"],
        "goles_favor": [1, 2],
        "goles_contra": [0, 2],
        "resultado_partido": ["W", "D"],
        "puntos": [3, 1],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_check_no_duplicate_match_ids_flags_repeated_ids() -> None:
    df = make_match_results(match_id=["m1", "m1"])
    issues = check_no_duplicate_match_ids(df)
    assert len(issues) == 1
    assert issues[0].severity == "error"


def test_check_no_duplicate_match_ids_clean() -> None:
    assert check_no_duplicate_match_ids(make_match_results()) == []


def test_check_points_consistency_flags_mismatch() -> None:
    df = make_match_results(puntos=[1, 1])  # first row says W but has 1 point
    issues = check_points_consistency(df)
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert len(issues[0].details) == 1


def test_check_minutes_within_bounds_flags_impossible_minutes() -> None:
    df = pd.DataFrame({"minutos": [90, 45, 250, -5]})
    issues = check_minutes_within_bounds(df)
    assert len(issues) == 1
    assert len(issues[0].details) == 2
    assert issues[0].severity == "warning"


def test_check_no_negative_stats_flags_negative_goals() -> None:
    df = pd.DataFrame({"goles": [1, -1, 0], "minutos": [90, 90, 90]})
    issues = check_no_negative_stats(df)
    assert len(issues) == 1
    assert issues[0].check == "non_negative:goles"
    assert issues[0].severity == "error"


def test_check_team_goals_reconciliation_allows_one_own_goal_gap() -> None:
    match_results = make_match_results(goles_favor=[2, 2])
    player_features = pd.DataFrame({"match_id": ["m1", "m2", "m2"], "goles": [1, 1, 1]})

    issues = check_team_goals_reconciliation(match_results, player_features)

    # m1: gap of 1 (own goal), within tolerance -> no issue.
    # m2: gap of 0 -> no issue.
    assert issues == []


def test_check_team_goals_reconciliation_flags_impossible_negative_gap() -> None:
    match_results = make_match_results(goles_favor=[1, 2])
    player_features = pd.DataFrame({"match_id": ["m1", "m2"], "goles": [3, 2]})

    issues = check_team_goals_reconciliation(match_results, player_features)

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].check == "team_goals_reconciliation"


def test_check_team_goals_reconciliation_flags_large_unexpected_gap() -> None:
    match_results = make_match_results(goles_favor=[5, 2])
    player_features = pd.DataFrame({"match_id": ["m1", "m2"], "goles": [1, 2]})

    issues = check_team_goals_reconciliation(match_results, player_features)

    assert len(issues) == 1
    assert issues[0].severity == "warning"


def test_check_player_name_variants_flags_accent_only_differences() -> None:
    df = pd.DataFrame({"jugador": ["Daniel Ruiz", "Daniel Ruíz", "Andrés Llinás", "Andrés Llinás"]})
    issues = check_player_name_variants(df)
    assert len(issues) == 1
    assert "Daniel Ruiz" in issues[0].details["variantes"].iloc[0]
    assert "Daniel Ruíz" in issues[0].details["variantes"].iloc[0]


def test_check_player_name_variants_clean_when_consistent() -> None:
    df = pd.DataFrame({"jugador": ["Daniel Ruíz", "Daniel Ruíz", "Andrés Llinás"]})
    assert check_player_name_variants(df) == []
