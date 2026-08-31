"""Normalization and matching for monitor placement rules."""

from __future__ import annotations

import os
import uuid


PLACEMENT_MODES = {"keep_size", "maximize", "saved_geometry"}


def _clean_text(value) -> str:
    return str(value or "").strip()


def _normalize_path(value) -> str:
    path = _clean_text(value)
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(path))


def normalize_monitor_rule(raw: dict, *, create_id: bool = False) -> dict | None:
    if not isinstance(raw, dict):
        return None

    executable_name = os.path.basename(_clean_text(raw.get("executable_name"))).casefold()
    executable_path = _normalize_path(raw.get("executable_path"))
    target_device = _clean_text(raw.get("target_device"))
    placement_mode = _clean_text(raw.get("placement_mode")).casefold() or "keep_size"
    if not executable_name or not target_device or placement_mode not in PLACEMENT_MODES:
        return None

    geometry = raw.get("saved_geometry")
    normalized_geometry = None
    if isinstance(geometry, dict):
        try:
            normalized_geometry = {
                "x_offset": int(geometry["x_offset"]),
                "y_offset": int(geometry["y_offset"]),
                "width": max(1, int(geometry["width"])),
                "height": max(1, int(geometry["height"])),
            }
        except (KeyError, TypeError, ValueError):
            normalized_geometry = None
    if placement_mode == "saved_geometry" and normalized_geometry is None:
        return None

    rule_id = _clean_text(raw.get("id"))
    if not rule_id and create_id:
        rule_id = str(uuid.uuid4())
    if not rule_id:
        return None

    match_exact_path = bool(raw.get("match_exact_path", bool(executable_path)))
    if match_exact_path and not executable_path:
        match_exact_path = False

    return {
        "id": rule_id,
        "name": _clean_text(raw.get("name")) or executable_name,
        "enabled": bool(raw.get("enabled", True)),
        "reapply_if_moved": bool(raw.get("reapply_if_moved", False)),
        "executable_name": executable_name,
        "executable_path": executable_path,
        "match_exact_path": match_exact_path,
        "title_contains": _clean_text(raw.get("title_contains")),
        "class_name": _clean_text(raw.get("class_name")),
        "target_device": target_device,
        "target_label": _clean_text(raw.get("target_label")) or target_device,
        "placement_mode": placement_mode,
        "saved_geometry": normalized_geometry,
    }


def normalize_monitor_rules(rules) -> list[dict]:
    if not isinstance(rules, list):
        return []
    normalized = []
    seen_ids = set()
    for raw in rules:
        rule = normalize_monitor_rule(raw)
        if rule is None or rule["id"] in seen_ids:
            continue
        seen_ids.add(rule["id"])
        normalized.append(rule)
    return normalized


def rule_matches_window(rule: dict, details: dict) -> bool:
    if not rule.get("enabled", True):
        return False
    if _clean_text(details.get("executable_name")).casefold() != rule["executable_name"]:
        return False
    if rule.get("match_exact_path"):
        actual_path = _normalize_path(details.get("executable_path"))
        if not actual_path or actual_path != rule.get("executable_path", ""):
            return False
    title_filter = _clean_text(rule.get("title_contains")).casefold()
    if title_filter and title_filter not in _clean_text(details.get("title")).casefold():
        return False
    class_filter = _clean_text(rule.get("class_name")).casefold()
    if class_filter and class_filter != _clean_text(details.get("class_name")).casefold():
        return False
    return True


def first_matching_rule(rules: list[dict], details: dict) -> dict | None:
    return next((rule for rule in rules if rule_matches_window(rule, details)), None)

