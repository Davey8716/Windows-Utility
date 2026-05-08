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

WINDOWS_RESURFACE_DEFAULTS = {
    "theme_dark": True,
    "main_always_on_top_enabled": True,
    "tooltips_enabled": True,
    "maximize_all_enabled": True,
    "minimize_after_use_enabled": True,
    "power_options_enabled": False,
    "mmb_activation_enabled": True,
    "screen_mover_activation_button": "middle",
    "title_bar_dock_enabled": True,
    "usb_idle_enabled": True,
    "usb_plug_enabled": True,
    "usb_plug_notify_mode": "on",
    "recycle_bin_auto_clean_enabled": False,
    "recycle_bin_age_rule_days": 30,
    "recycle_bin_last_auto_clean_popup_days": None,
    "master_backup_output_path": str(Path.home()),
    "advanced_panel_open": False,
    "master_toggle_left": True,
    "master_toggle_right": False,
    "left_section_states": {
        "user_interface": True,
        "screen_mover": True,
        "drive_reminder_options": True,
        "organising_utilities": True,
        "recycle_bin_actions": True,
    },
    "right_section_states": {
        "windows_utilities": False,
        "sidebar_utils_section": False,
        "drive_space_display": False,
    },
}

SHARED_APP_STATE_DEFAULTS = {
    **WINDOWS_RESURFACE_DEFAULTS,
    **FOLDER_CREATOR_DEFAULTS,
}
