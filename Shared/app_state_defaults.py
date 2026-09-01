from pathlib import Path

FOLDER_CREATOR_DEFAULTS = {
    "last_base_dir": "",
    "nested_date_stamp_enabled": False,
    "nested_date_stamp_mode": "ISO",
    "nested_auto_number_enabled": False,
    "open_folder_after_build": False,
    "minimize_after_build": False,
    "close_after_build": False,
}

FOLDER_CREATOR_STATE_KEYS = frozenset(FOLDER_CREATOR_DEFAULTS)

WINDOWS_RESURFACE_DEFAULTS = {
    "last_opened_page": "overview",
    "theme_dark": True,
    "main_always_on_top_enabled": True,
    "tooltips_enabled": True,
    "maximize_all_enabled": True,
    "minimize_after_use_enabled": True,
    "power_options_enabled": False,
    "mmb_activation_enabled": True,
    "screen_mover_activation_button": "middle",
    "title_bar_dock_enabled": True,
    "retired_features_cleanup_version": 0,
    "screen_mover_keyboard_hotkeys": {
        "FAR_LEFT": "",
        "LEFT": "",
        "RIGHT": "",
        "FAR_RIGHT": "",
        "MINIMIZE": "",
        "MAXIMIZE": "",
    },
    "monitor_rules": [],
    "usb_idle_enabled": True,
    "usb_plug_enabled": True,
    "usb_plug_notify_mode": "on",
    "recycle_bin_auto_clean_enabled": False,
    "recycle_bin_age_rule_days": 30,
    "recycle_bin_last_auto_clean_popup_days": None,
    "master_backup_output_path": str(Path.home()),
    "desktop_screenshot_last_dir": str(Path.home()),
}

# These keys are persisted by Windows Resurface but are intentionally not all
# defaults. Some are optional output paths and some are compatibility aliases
# retained while older state files are migrated.
WINDOWS_RESURFACE_STATE_KEYS = frozenset(
    {
        *WINDOWS_RESURFACE_DEFAULTS,
        "backup_folder_path",
        "backup_output_path",
        "desktop_layout_last_path",
        "desktop_screenshot_last_path",
        "desktop_zen_mode_enabled",
        "minimize_all_enabled",
    }
)

WINDOWS_RESURFACE_DEPRECATED_STATE_KEYS = frozenset(
    {
        "hover_window_controls_enabled",
        "hover_window_controls_dwell_ms",
        "hover_window_controls_migration_completed",
    }
)

SHARED_APP_STATE_DEFAULTS = {
    **WINDOWS_RESURFACE_DEFAULTS,
    **FOLDER_CREATOR_DEFAULTS,
}
