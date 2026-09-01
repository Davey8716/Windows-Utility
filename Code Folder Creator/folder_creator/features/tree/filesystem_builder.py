from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any


BuildNode = Mapping[str, Any]


class FolderStructureBuilder:
    """Create a folder structure from widget-independent tree data."""

    def __init__(self, now: Callable[[], datetime] | None = None):
        self._now = now or datetime.now

    def build(
        self,
        nodes: Sequence[BuildNode],
        base_path: str | Path,
        timestamp_mode: str | None = None,
    ) -> tuple[str, str]:
        if not nodes:
            return "empty", "Tree is empty."

        try:
            base_dir = Path(base_path)
            for node in nodes:
                name = str(node.get("name", "")).strip()
                if timestamp_mode:
                    name = f"{name}_{self._build_timestamp(timestamp_mode)}"

                root_path = base_dir / name
                if root_path.is_dir():
                    return "exists", "Folder structure already exists."

                root_path.mkdir(parents=True, exist_ok=True)
                for child in node.get("children", []):
                    self._create_node(root_path, child)

            return "success", "Folder structure created successfully."
        except Exception:
            return "error", "Error creating folder structure."

    def _build_timestamp(self, mode: str) -> str:
        now = self._now()
        if mode == "ISO":
            return now.strftime("%Y-%m-%d")
        if mode == "UK":
            return now.strftime("%d-%m-%Y")
        if mode == "US":
            return now.strftime("%m-%d-%Y")
        return ""

    def _create_node(self, parent_path: Path, node: BuildNode) -> None:
        name = str(node.get("name", "")).strip()
        if not name:
            return

        node_path = parent_path / name
        if node.get("kind") == "file":
            try:
                node_path.parent.mkdir(parents=True, exist_ok=True)
                node_path.touch(exist_ok=True)
            except Exception:
                pass
            return

        node_path.mkdir(parents=True, exist_ok=True)
        for child in node.get("children", []):
            self._create_node(node_path, child)
