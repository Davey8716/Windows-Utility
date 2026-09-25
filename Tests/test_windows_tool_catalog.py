from PySide6.QtWidgets import QApplication

from resurface.features.system.windows_tool_catalog import WindowsToolCatalog
from resurface.ui.pages.windows_utilities_page import WindowsUtilitiesPage


def _application():
    return QApplication.instance() or QApplication([])


def test_catalog_exposes_expected_groups_and_unique_tools():
    groups = WindowsToolCatalog.groups()
    assert [group.label for group in groups] == [
        "System",
        "Devices & Storage",
        "Display And Sound",
        "Services & Logs",
        "Monitoring & Security",
        "Network",
        "Startup & Power",
    ]
    tools = [tool for group in groups for tool in group.tools]
    assert len({tool.key for tool in tools}) == len(tools)
    assert all(group.tooltip_key for group in groups)


def test_catalog_preserves_special_launch_and_minimize_metadata():
    tools = {
        tool.key: tool
        for group in WindowsToolCatalog.groups()
        for tool in group.tools
    }
    assert tools["hosts_editor"].launch_kind == "shell_execute_elevated"
    assert tools["hosts_editor"].title_candidates == ("hosts - Notepad", "Notepad")
    assert tools["ip_config"].launch_kind == "maintenance"
    assert tools["ip_config"].minimize is False
    assert tools["advanced_display_settings"].launch_kind == "advanced_display_settings"
    assert tools["display_settings"].launch_kind == "display_settings"
    assert tools["sound_devices"].launch_kind == "sound_settings"
    assert tools["router_login"].launch_kind == "router"


def test_display_and_sound_dropdown_is_in_the_left_column_and_dispatches_existing_actions():
    _application()
    calls = []
    actions = type(
        "Actions",
        (),
        {
            "open_advanced_display_settings": lambda self: calls.append("advanced"),
            "open_display_settings": lambda self: calls.append("display"),
            "open_sound_settings": lambda self: calls.append("sound"),
        },
    )()
    output_contexts = []
    page = WindowsUtilitiesPage(
        WindowsToolCatalog(),
        object(),
        object(),
        object(),
        actions,
        lambda *_args: None,
        lambda action: action(),
        output_contexts.append,
    )

    assert [group.label for _combo, group, _tools in page.quick_action_dropdowns] == [
        "System",
        "Devices & Storage",
        "Display And Sound",
        "Services & Logs",
        "Monitoring & Security",
        "Network",
        "Startup & Power",
    ]
    display_group = next(
        tools for _combo, group, tools in page.quick_action_dropdowns if group.label == "Display And Sound"
    )
    for label in ("Advanced Display Settings", "Display Settings", "Sound Devices"):
        page.invoke_tool(display_group[label])

    assert calls == ["advanced", "display", "sound"]
    assert output_contexts == [
        "Advanced Display Settings",
        "Display Settings",
        "Sound Devices",
    ]
    page.deleteLater()
