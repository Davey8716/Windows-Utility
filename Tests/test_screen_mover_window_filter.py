from unittest.mock import patch

import pytest
from resurface.features.screen_mover import service, window_filter


@pytest.mark.parametrize(
    "executable_path",
    [
        r"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2.exe",
        r"D:\STEAMLIBRARY\SteamApps\Common\Game\bin\game.exe",
        "E:/SteamLibrary/steamapps/common/Game/game.exe",
    ],
)
def test_recognizes_steam_game_executable_paths(executable_path):
    assert window_filter.is_steam_game_executable(executable_path)


@pytest.mark.parametrize(
    "executable_path",
    [
        None,
        "",
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Games\steamapps\common\game.exe",
        r"C:\Games\notsteamapps\common\Game\game.exe",
        r"C:\Games\steamapps\commonplace\Game\game.exe",
        r"C:\Games\Game\game.exe",
    ],
)
def test_rejects_non_steam_game_executable_paths(executable_path):
    assert not window_filter.is_steam_game_executable(executable_path)


def test_process_lookup_failure_does_not_classify_window_as_steam_game():
    mover = service.ScreenMover.__new__(service.ScreenMover)

    with patch.object(
        window_filter.win32process,
        "GetWindowThreadProcessId",
        side_effect=OSError,
    ):
        assert not mover._is_steam_game_window(123)
