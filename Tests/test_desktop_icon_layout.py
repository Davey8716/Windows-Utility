from resurface.features.desktop.desktop_icon_layout import (
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
