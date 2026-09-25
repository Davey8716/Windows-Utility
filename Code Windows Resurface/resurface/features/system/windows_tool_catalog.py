from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WindowsToolSpec:
    key: str
    label: str
    title_candidates: tuple[str, ...] = ()
    launch_kind: str = "shell_open"
    target: str = ""
    parameters: str | None = None
    minimize: bool = True


@dataclass(frozen=True, slots=True)
class WindowsToolGroup:
    label: str
    tooltip_key: str
    tools: tuple[WindowsToolSpec, ...]


def _tool(key, label, titles=(), kind="shell_open", target="", parameters=None, minimize=True):
    return WindowsToolSpec(key, label, tuple(titles), kind, target, parameters, minimize)


class WindowsToolCatalog:
    @staticmethod
    def groups() -> tuple[WindowsToolGroup, ...]:
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        common_startup = os.path.join(
            os.environ.get("ProgramData", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup",
        )
        hosts_path = os.path.join(system_root, "System32", "drivers", "etc", "hosts")
        memory_diagnostic = os.path.join(system_root, "System32", "mdsched.exe")
        return (
            WindowsToolGroup(
                "System",
                "windows_dropdown_system",
                (
                    _tool("control_panel", "Control Panel", ("Control Panel",), "explorer_title", "explorer.exe", "shell:ControlPanelFolder"),
                    _tool("credential_manager", "Credential Manager", ("Credential Manager",), "shell_execute", "control.exe", "/name Microsoft.CredentialManager"),
                    _tool("local_users", "Local Users and Groups", ("Local Users and Groups", "lusrmgr"), "shell_execute", "lusrmgr.msc"),
                    _tool("system_restore", "System Restore", ("System Restore", "System Restore Properties"), "shell_execute", "rstrui.exe"),
                    _tool("system_settings", "System Settings", ("Settings",), target="ms-settings:"),
                    _tool("system_information", "System Information", ("System Information",), "popen", "msinfo32"),
                ),
            ),
            WindowsToolGroup(
                "Devices & Storage",
                "windows_dropdown_devices_storage",
                (
                    _tool("device_manager", "Device Manager", ("Device Manager",), target="devmgmt.msc"),
                    _tool("disk_cleanup", "Disk Cleanup", ("Disk Cleanup",), "popen", "cleanmgr"),
                    _tool("disk_management", "Disk Management", ("Disk Management",), target="diskmgmt.msc"),
                ),
            ),
            WindowsToolGroup(
                "Display And Sound",
                "windows_dropdown_display_sound",
                (
                    _tool("advanced_display_settings", "Advanced Display Settings", kind="advanced_display_settings"),
                    _tool("display_settings", "Display Settings", kind="display_settings"),
                    _tool("sound_devices", "Sound Devices", kind="sound_settings"),
                ),
            ),
            WindowsToolGroup(
                "Services & Logs",
                "windows_dropdown_services_logs",
                (
                    _tool("services", "Services", ("Services",), target="services.msc"),
                    _tool("event_viewer", "Event Viewer", ("Event Viewer",), target="eventvwr.msc"),
                ),
            ),
            WindowsToolGroup(
                "Monitoring & Security",
                "windows_dropdown_monitoring_security",
                (
                    _tool("hosts_editor", "Hosts File Editor", ("hosts - Notepad", "Notepad"), "shell_execute_elevated", "notepad.exe", hosts_path),
                    _tool("reliability_monitor", "Reliability Monitor", ("Reliability Monitor", "View reliability history", "Performance Monitor"), "shell_execute", "perfmon.exe", "/rel"),
                    _tool("resource_monitor", "Resource Monitor", ("Resource Monitor",), "popen", "resmon"),
                    _tool("task_manager", "Task Manager", ("Task Manager", "Windows Task Manager"), "popen", "taskmgr"),
                    _tool("memory_diagnostic", "Windows Memory Diagnostic", ("Windows Memory Diagnostic", "Diagnosing your computer's memory problems"), "shell_execute", memory_diagnostic),
                    _tool("windows_security", "Windows Defender / Virus & Threat Protection", ("Virus & threat protection", "Windows Security", "Security at a glance"), target="windowsdefender://threat"),
                    _tool("update_troubleshooter", "Windows Update Troubleshooter", ("Troubleshoot", "Get Help", "Windows Update"), target="ms-settings:troubleshoot"),
                ),
            ),
            WindowsToolGroup(
                "Network",
                "windows_dropdown_network",
                (
                    _tool("firewall", "Firewall", ("Windows Defender Firewall", "Firewall"), target="wf.msc"),
                    _tool("ip_config", "IP Configuration", kind="maintenance", minimize=False),
                    _tool("network_connections", "Network Connections", ("Network Connections",), "shell_execute", "control.exe", "ncpa.cpl"),
                    _tool("network_diagnostics", "Network Diagnostics", ("Troubleshoot", "Get Help", "Network & internet"), target="ms-settings:network-status"),
                    _tool("network_reset", "Network Reset", ("Network reset", "Network & internet"), target="ms-settings:network-advancedsettings"),
                    _tool("router_login", "Router Login", kind="router"),
                ),
            ),
            WindowsToolGroup(
                "Startup & Power",
                "windows_dropdown_startup_power",
                (
                    _tool("autoplay", "AutoPlay Settings", ("AutoPlay",), "shell_execute", "control.exe", "/name Microsoft.AutoPlay"),
                    _tool("common_startup", "Common Startup Folder", kind="folder", target=common_startup),
                    _tool("installed_programs", "Installed Programs", ("Programs and Features", "Installed Programs"), "shell_execute", "control.exe", "appwiz.cpl"),
                    _tool("power_options", "Power Options", ("Power Options",), "shell_execute", "control.exe", "/name Microsoft.PowerOptions"),
                    _tool("startup_apps", "Startup Apps", ("Startup apps",), target="ms-settings:startupapps"),
                ),
            ),
        )
