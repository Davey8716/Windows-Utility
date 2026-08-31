"""Application-to-monitor placement rules."""

from .rule_schema import (
    normalize_monitor_rule,
    normalize_monitor_rules,
    rule_matches_window,
)
from .repository import BackupDirectoryNotConfiguredError, MonitorRulesRepository
from .watcher import MonitorRuleWatcher
from .win32_windows import (
    apply_monitor_rule,
    capture_window_geometry,
    enumerate_eligible_windows,
    enumerate_monitors,
)

__all__ = [
    "MonitorRuleWatcher",
    "MonitorRulesRepository",
    "BackupDirectoryNotConfiguredError",
    "apply_monitor_rule",
    "capture_window_geometry",
    "enumerate_eligible_windows",
    "enumerate_monitors",
    "normalize_monitor_rule",
    "normalize_monitor_rules",
    "rule_matches_window",
]
