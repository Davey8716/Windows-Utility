from pathlib import Path

from resurface.features.screen_mover import dock_icons


def test_dock_icon_theme_uses_contrast_with_hysteresis():
    assert dock_icons._dock_icon_theme_for_luminance(20) == "White"
    assert dock_icons._dock_icon_theme_for_luminance(240) == "Black"
    assert dock_icons._dock_icon_theme_for_luminance(150, "White") == "White"
    assert dock_icons._dock_icon_theme_for_luminance(150, "Black") == "Black"
    assert dock_icons._dock_icon_theme_for_luminance(None) == "Black"


def test_dock_icon_paths_include_windows_resurface_asset_tree():
    project_root = Path(dock_icons.__file__).resolve().parents[4]
    directories = dock_icons._dock_icon_directories("Black")

    assert project_root / "Icon Pngs" / "Black" in directories
    assert (project_root / "Icon Pngs" / "Black" / "Left.png").is_file()
