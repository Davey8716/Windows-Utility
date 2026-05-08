import json,os
from pathlib import Path

class StateManager:
    def __init__(self):
        self.app_dir = Path(os.getenv("LOCALAPPDATA")) / "FolderCreator"
        self.app_dir.mkdir(parents=True, exist_ok=True)

        self.state_file = self.app_dir / "folder_creator_user_state.json"

        self.default_state = {
            "theme_index": 0,
            "last_base_dir": "",

            # Nested creator
            "nested_date_stamp_enabled": False,
            "nested_date_stamp_mode": "ISO",
            "nested_auto_number_enabled": False,

            # Nested build behaviour
            "open_folder_after_build": False,
            "minimize_after_build": False,
            "close_after_build": False,
        }

    # ---------------------------------------------------------
    # Load State
    # ---------------------------------------------------------
    def load_state(self):
        if not self.state_file.exists():
            self.save_state(self.default_state)
            return self.default_state.copy()

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # ensure missing keys are filled
            for k, v in self.default_state.items():
                data.setdefault(k, v)

            return data

        except Exception:
            return self.default_state.copy()

    # ---------------------------------------------------------
    # Save State
    # ---------------------------------------------------------
    def save_state(self, state_dict):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state_dict, f, indent=4)
        except Exception:
            pass

    # ---------------------------------------------------------
    # Update Single Key
    # ---------------------------------------------------------
    def update(self, key, value):
        state = self.load_state()
        state[key] = value
        self.save_state(state)
