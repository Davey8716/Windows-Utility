from resurface.features.desktop.desktop_icon_layout import (
    desktop_icon_groups_are_alphabetised,
    desktop_icon_groups,
    grouped_alphabetical_positions,
)


def test_grouped_alphabetical_positions_preserves_separate_group_shapes():
    layout = [
        {"name": "Gamma", "x": 0, "y": 0},
        {"name": "Alpha", "x": 0, "y": 100},
        {"name": "Delta", "x": 100, "y": 0},
        {"name": "Beta", "x": 100, "y": 100},
        {"name": "Zoo", "x": 400, "y": 0},
        {"name": "Apple", "x": 400, "y": 100},
    ]

    groups = desktop_icon_groups(layout)

    assert [len(group) for group in groups] == [4, 2]
    assert grouped_alphabetical_positions(layout) == [
        (100, 100),  # Gamma
        (0, 0),      # Alpha
        (100, 0),    # Delta
        (0, 100),    # Beta
        (400, 100),  # Zoo
        (400, 0),    # Apple
    ]


def test_desktop_icon_groups_are_alphabetised_for_each_detected_group():
    layout = [
        {"name": "Alpha", "x": 0, "y": 0},
        {"name": "Beta", "x": 0, "y": 100},
        {"name": "Delta", "x": 100, "y": 0},
        {"name": "Gamma", "x": 100, "y": 100},
        {"name": "Apple", "x": 400, "y": 0},
        {"name": "Zoo", "x": 400, "y": 100},
    ]

    assert desktop_icon_groups_are_alphabetised(layout)


def test_desktop_icon_groups_are_not_alphabetised_when_a_group_is_rearranged():
    layout = [
        {"name": "Beta", "x": 0, "y": 0},
        {"name": "Alpha", "x": 0, "y": 100},
        {"name": "Apple", "x": 400, "y": 0},
        {"name": "Zoo", "x": 400, "y": 100},
    ]

    assert not desktop_icon_groups_are_alphabetised(layout)


def test_desktop_icon_groups_are_alphabetised_with_duplicate_names():
    layout = [
        {"name": "Alpha", "x": 0, "y": 0},
        {"name": "Alpha", "x": 0, "y": 100},
        {"name": "Beta", "x": 100, "y": 0},
    ]

    assert desktop_icon_groups_are_alphabetised(layout)
