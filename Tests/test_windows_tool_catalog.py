from resurface.features.system.windows_tool_catalog import WindowsToolCatalog


def test_catalog_exposes_expected_groups_and_unique_tools():
    groups = WindowsToolCatalog.groups()
    assert [group.label for group in groups] == [
        "System",
        "Devices & Storage",
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
    assert tools["router_login"].launch_kind == "router"
