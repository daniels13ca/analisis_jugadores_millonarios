from millos_data.dashboard import formatting as fmt


def test_goals_for_against_rename_and_colors_are_consistent() -> None:
    """The color map must be keyed by the *renamed* (display) column names,
    not the raw ones -- otherwise color_discrete_map silently fails to match
    and Plotly falls back to its default palette.
    """
    assert set(fmt.GOALS_FOR_AGAINST_RENAME.values()) == set(fmt.GOALS_FOR_AGAINST_COLORS.keys())


def test_result_label_known_and_unknown_values() -> None:
    assert fmt.result_label("W") == "🟢 Ganó"
    assert fmt.result_label("D") == "🟡 Empató"
    assert fmt.result_label("L") == "🔴 Perdió"
    assert fmt.result_label("?") == "?"


def test_condition_label_known_and_unknown_values() -> None:
    assert fmt.condition_label("Local") == "🏠 Local"
    assert fmt.condition_label("Visitante") == "✈️ Visitante"
    assert fmt.condition_label("Neutral") == "Neutral"


def test_mes_abbr_has_twelve_entries() -> None:
    assert len(fmt.MES_ABBR) == 12
    assert fmt.MES_ABBR[0] == "Ene"
    assert fmt.MES_ABBR[11] == "Dic"


def test_position_label_known_and_unknown_values() -> None:
    assert fmt.position_label("D") == "Defensa"
    assert fmt.position_label("F") == "Delantero"
    assert fmt.position_label("G") == "Arquero"
    assert fmt.position_label("M") == "Mediocampista"
    assert fmt.position_label("?") == "?"
