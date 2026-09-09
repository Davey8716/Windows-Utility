"""Clipboard capture, provenance, and export support."""

from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
from typing import Callable
from uuid import uuid4

import psutil
import win32gui
import win32process
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

HISTORY_LIMIT = 100
BACKUP_FORMAT = "windows-resurface-clipboard-provenance"
BACKUP_VERSION = 1
_WEB_URL_PATTERN = re.compile(r'''https?://[^\s<>"']+''', re.IGNORECASE)
_URL_TRAILING_PUNCTUATION = ".,;:!?)]}"


def extract_web_urls(text: str) -> list[str]:
    """Return unique HTTP(S) URLs in their first-seen order."""
    if not isinstance(text, str):
        return []
    urls = []
    for match in _WEB_URL_PATTERN.finditer(text):
        url = match.group(0).rstrip(_URL_TRAILING_PUNCTUATION)
        if url and url not in urls:
            urls.append(url)
    return urls


def _program_name(source: dict) -> str:
    executable = str(source.get("executable") or "").strip()
    if executable:
        return PureWindowsPath(executable).stem or executable
    return str(source.get("process_name") or source.get("title") or "Unknown program").strip()


def normalize_history(value) -> list[dict]:
    """Keep only JSON-safe records created by the provenance service."""
    if not isinstance(value, list):
        return []
    records = []
    for raw in value[-HISTORY_LIMIT:]:
        if not isinstance(raw, dict) or raw.get("content_type") not in {"text", "files"}:
            continue
        source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
        record = {
            "id": str(raw.get("id") or uuid4().hex),
            "timestamp": str(raw.get("timestamp") or ""),
            "content_type": raw["content_type"],
            "source": {"program_name": _program_name(source)},
        }
        if record["content_type"] == "text" and isinstance(raw.get("text"), str):
            record["text"] = raw["text"]
            record["urls"] = extract_web_urls(record["text"])
        elif record["content_type"] == "files" and isinstance(raw.get("files"), list):
            record["files"] = [str(path) for path in raw["files"] if str(path)]
        else:
            continue
        records.append(record)
    return records[-HISTORY_LIMIT:]


def capture_foreground_source() -> dict:
    """Return best-effort metadata for the foreground window."""
    try:
        hwnd = int(win32gui.GetForegroundWindow())
        if not hwnd:
            return {}
        _thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
        executable = ""
        process_name = ""
        try:
            process = psutil.Process(process_id)
            executable = process.exe()
            process_name = process.name()
        except (psutil.Error, OSError):
            pass
        return {"program_name": _program_name({
            "executable": executable,
            "process_name": process_name,
            "title": win32gui.GetWindowText(hwnd),
        })}
    except Exception:
        return {}


class ClipboardProvenanceService(QObject):
    """Observe clipboard changes while enabled and persist a bounded history."""

    history_changed = Signal(list)
    recording_changed = Signal(bool)

    def __init__(
        self,
        state: dict,
        save_state: Callable[[dict], None],
        *,
        clipboard=None,
        source_provider: Callable[[], dict] = capture_foreground_source,
        now: Callable[[], datetime] = datetime.now,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._save_state = save_state
        self._clipboard = clipboard
        self._source_provider = source_provider
        self._now = now
        self._connected = False
        self._state["clipboard_provenance_history"] = normalize_history(
            state.get("clipboard_provenance_history")
        )
        self._state["clipboard_provenance_enabled"] = bool(
            state.get("clipboard_provenance_enabled", False)
        )

    @property
    def enabled(self) -> bool:
        return bool(self._state["clipboard_provenance_enabled"])

    @property
    def history(self) -> list[dict]:
        return copy.deepcopy(self._state["clipboard_provenance_history"])

    def start(self) -> None:
        if self._connected:
            return
        self._clipboard = self._clipboard or QGuiApplication.clipboard()
        self._clipboard.dataChanged.connect(self._on_clipboard_changed)
        self._connected = True

    def stop(self) -> None:
        if not self._connected:
            return
        try:
            self._clipboard.dataChanged.disconnect(self._on_clipboard_changed)
        except (RuntimeError, TypeError):
            pass
        self._connected = False

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.enabled:
            return
        self._state["clipboard_provenance_enabled"] = enabled
        self._save_state(self._state)
        self.recording_changed.emit(enabled)

    def _on_clipboard_changed(self) -> None:
        if not self.enabled or self._clipboard is None:
            return
        mime = self._clipboard.mimeData()
        if mime.hasUrls():
            return
        if mime.hasText():
            text = mime.text()
            if text:
                self._append({
                    "content_type": "text",
                    "text": text,
                    "urls": extract_web_urls(text),
                })

    def _append(self, content: dict) -> None:
        if content.get("content_type") == "text":
            content = {**content, "urls": extract_web_urls(content.get("text", ""))}
        record = {
            "id": uuid4().hex,
            "timestamp": self._now().astimezone().isoformat(timespec="seconds"),
            "source": self._source_provider() or {},
            **content,
        }
        history = self._state["clipboard_provenance_history"]
        history.append(record)
        self._state["clipboard_provenance_history"] = history[-HISTORY_LIMIT:]
        self._save_state(self._state)
        self.history_changed.emit(self.history)

    def delete(self, record_id: str) -> None:
        history = self._state["clipboard_provenance_history"]
        updated = [item for item in history if item.get("id") != record_id]
        if len(updated) == len(history):
            return
        self._state["clipboard_provenance_history"] = updated
        self._save_state(self._state)
        self.history_changed.emit(self.history)

    def clear(self) -> None:
        if not self._state["clipboard_provenance_history"]:
            return
        self._state["clipboard_provenance_history"] = []
        self._save_state(self._state)
        self.history_changed.emit([])

class ClipboardProvenanceRepository:
    def __init__(self, get_master_backup_dir: Callable[[], str] | None, *, now=datetime.now):
        self._get_master_backup_dir = get_master_backup_dir
        self._now = now

    def backup_directory(self) -> Path | None:
        raw = str(self._get_master_backup_dir() or "").strip() if callable(self._get_master_backup_dir) else ""
        return Path(raw) if raw else None

    @staticmethod
    def _fingerprint(history: list[dict]) -> str:
        normalized = normalize_history(copy.deepcopy(history))
        encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def has_export_changes(self, history: list[dict]) -> bool:
        """Compare history with the latest compatible backup in the master path."""
        backup_dir = self.backup_directory()
        if backup_dir is None:
            return True
        candidates = sorted(
            (
                path for path in (backup_dir / "Clipboard Provenance").glob(
                    "clipboard_provenance_*.json"
                )
                if re.fullmatch(
                    r"clipboard_provenance_\d{8}_\d{6}_\d{6}\.json", path.name
                )
            ),
            reverse=True,
        )
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                raw_records = payload.get("records") if isinstance(payload, dict) else None
                if (
                    not isinstance(payload, dict)
                    or payload.get("format") != BACKUP_FORMAT
                    or payload.get("version") != BACKUP_VERSION
                    or not isinstance(raw_records, list)
                ):
                    continue
                previous = normalize_history(raw_records)
                if len(previous) != len(raw_records):
                    continue
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            return self._fingerprint(history) != self._fingerprint(previous)
        return True

    def export_history(self, history: list[dict]) -> Path:
        backup_dir = self.backup_directory()
        if backup_dir is None:
            raise ValueError("Set a Master Backup Path before exporting clipboard provenance.")
        timestamp = self._now().strftime("%Y%m%d_%H%M%S_%f")
        path = backup_dir / "Clipboard Provenance" / f"clipboard_provenance_{timestamp}.json"
        payload = {"format": BACKUP_FORMAT, "version": BACKUP_VERSION, "records": normalize_history(history)}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
