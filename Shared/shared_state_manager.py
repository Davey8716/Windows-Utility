import copy
import json
import os
from pathlib import Path


class JsonStateManager:
    def __init__(
        self,
        *,
        app_dir_name: str,
        config_filename: str,
        defaults: dict,
        legacy_config_path: Path | None = None,
        legacy_key_map: dict | None = None,
        legacy_value_transforms: dict | None = None,
        persist_defaults_on_missing: bool = False,
        preserve_unknown_keys: bool = False,
        config_path_resolver=None,
        legacy_config_path_resolver=None,
    ):
        self.app_dir_name = app_dir_name
        self.config_filename = config_filename
        self.default_state = copy.deepcopy(defaults)
        self.legacy_config_path = legacy_config_path
        self.legacy_key_map = dict(legacy_key_map or {})
        self.legacy_value_transforms = dict(legacy_value_transforms or {})
        self.persist_defaults_on_missing = persist_defaults_on_missing
        self.preserve_unknown_keys = preserve_unknown_keys
        self._config_path_resolver = config_path_resolver
        self._legacy_config_path_resolver = legacy_config_path_resolver

    @property
    def app_dir(self) -> Path:
        return self.get_config_path().parent

    @property
    def state_file(self) -> Path:
        return self.get_config_path()

    def _copy_defaults(self) -> dict:
        return copy.deepcopy(self.default_state)

    def get_config_path(self) -> Path:
        if callable(self._config_path_resolver):
            return Path(self._config_path_resolver())

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / self.app_dir_name / self.config_filename
        return Path.home() / "AppData" / "Local" / self.app_dir_name / self.config_filename

    def get_legacy_config_path(self) -> Path | None:
        if callable(self._legacy_config_path_resolver):
            legacy_path = self._legacy_config_path_resolver()
            return Path(legacy_path) if legacy_path is not None else None
        if self.legacy_config_path is None:
            return None
        return Path(self.legacy_config_path)

    def _merge_value(self, value, default):
        if isinstance(default, dict):
            merged = copy.deepcopy(default)
            if isinstance(value, dict):
                for nested_key, nested_default in default.items():
                    if nested_key in value:
                        merged[nested_key] = self._merge_value(
                            value[nested_key],
                            nested_default,
                        )
            return merged

        if isinstance(default, bool):
            return bool(value)

        if value is None:
            return None if default is None else copy.deepcopy(default)

        return value

    def _build_persisted_state(self, state: dict) -> dict:
        payload = dict(state)
        persisted = {}

        for key, default in self.default_state.items():
            legacy_key = self.legacy_key_map.get(key)

            if key in payload:
                persisted[key] = self._merge_value(payload[key], default)
                continue

            if legacy_key and legacy_key in payload:
                transform = self.legacy_value_transforms.get(key, lambda value: value)
                persisted[key] = self._merge_value(transform(payload[legacy_key]), default)
                continue

            persisted[key] = copy.deepcopy(default)

        return persisted

    def _read_json_file(self, path: Path) -> dict | None:
        try:
            with open(path, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _merge_unknown_keys(self, persisted: dict, *source_dicts: dict | None) -> dict:
        if not self.preserve_unknown_keys:
            return persisted

        merged = dict(persisted)
        for source in source_dicts:
            if not isinstance(source, dict):
                continue
            for key, value in source.items():
                if key not in merged and key not in self.default_state:
                    merged[key] = value
        return merged

    def save_state(self, state_dict: dict):
        config_path = self.get_config_path()
        existing_data = self._read_json_file(config_path) or {}
        payload = self._build_persisted_state({**existing_data, **state_dict})
        payload = self._merge_unknown_keys(payload, existing_data, state_dict)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(config_path, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, indent=4)
        except Exception:
            pass

    def load_state(self) -> dict:
        config_path = self.get_config_path()
        legacy_config_path = self.get_legacy_config_path()
        config_data = self._read_json_file(config_path) if config_path.exists() else None
        legacy_data = None

        if legacy_config_path is not None and legacy_config_path.exists():
            legacy_data = self._read_json_file(legacy_config_path)

        if config_data is None and legacy_data is None:
            defaults = self._copy_defaults()
            if self.persist_defaults_on_missing:
                self.save_state(defaults)
            return defaults

        try:
            data = dict(config_data or {})
            if isinstance(legacy_data, dict):
                for key, value in legacy_data.items():
                    data.setdefault(key, value)
            data = self._build_persisted_state(data)
            data = self._merge_unknown_keys(data, config_data, legacy_data)

            if legacy_data is not None and legacy_config_path != config_path:
                self.save_state(data)

            return data
        except Exception:
            return self._copy_defaults()

    def update(self, key, value):
        state = self.load_state()
        state[key] = value
        self.save_state(state)
