"""Application-to-monitor placement rules."""

from .monitor_rules import (
    MonitorRuleWatcher,
    apply_monitor_rule,
    capture_window_geometry,
    enumerate_eligible_windows,
    enumerate_monitors,
    normalize_monitor_rule,
    normalize_monitor_rules,
    rule_matches_window,
)
from .repository import BackupDirectoryNotConfiguredError, MonitorRulesRepository

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
