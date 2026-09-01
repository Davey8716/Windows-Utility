"""Privacy-safe computer-vision fallback for custom caption buttons."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication, QImage

from resurface.features.hover_window_controls.app.identity import (
    DISPLAY_NAME,
    LEGACY_DATA_DIRECTORY,
    local_app_data_directory,
)
from resurface.features.hover_window_controls.app.data_export import (
    DataExportError,
    DataExportResult,
    export_application_data,
)
from resurface.features.hover_window_controls.core.hover_controller import CaptionAction

SCHEMA_VERSION = 3
CONSOLIDATED_SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
AUTOMATIC_SCORE = 0.88
FINAL_SCORE = 0.90
WINNER_MARGIN = 0.12
AUTOMATIC_PERSISTENCE_COUNT = 3
AUTOMATIC_LAYOUT_VERSION = 3
CAPTION_STRIP_WIDTH_DIP = 192
CAPTION_STRIP_HEIGHT_DIP = 64


@dataclass(frozen=True)
class ApplicationIdentity:
    executable_path: str
    executable_version: str
    friendly_name: str
    window_class: str
    dpi: int
    theme: str
    caption_side: str
    window_state: str

    @property
    def executable_hash(self) -> str:
        return hashlib.sha256(
            self.executable_path.casefold().encode("utf-8")
        ).hexdigest()[:16]

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class VisionContext:
    hwnd: int
    bounds: tuple[int, int, int, int]
    dpi: int
    identity: ApplicationIdentity


@dataclass(frozen=True)
class VisionMatch:
    action: CaptionAction
    rect: tuple[int, int, int, int]
    score: float
    profile_id: str
    crop: bytes = b""


@dataclass(frozen=True)
class VisionSnapshot:
    context: VisionContext
    image: QImage
    proposals: dict[CaptionAction, tuple[int, int, int, int]]
    suggested_actions: frozenset[CaptionAction] = frozenset()


@dataclass(frozen=True)
class CachedButton:
    action: CaptionAction
    rect: tuple[float, float, float, float]
    image_file: str
    visual: str = ""


@dataclass(frozen=True)
class VisionProfile:
    profile_id: str
    origin: str
    identity: ApplicationIdentity
    crop_size: tuple[int, int]
    buttons: tuple[CachedButton, ...]
    directory: Path
    image_file: Optional[str] = None
    image_rect: Optional[tuple[float, float, float, float]] = None


@dataclass(frozen=True)
class ObservationResult:
    profile: VisionProfile
    saved: frozenset[tuple[CaptionAction, str]]
    existing: frozenset[tuple[CaptionAction, str]]
    unavailable: frozenset[tuple[CaptionAction, str]]
    unresolved: frozenset[tuple[CaptionAction, str]]

    @property
    def complete(self) -> frozenset[tuple[CaptionAction, str]]:
        return self.saved | self.existing | self.unavailable


@dataclass(frozen=True)
class TrackedApplication:
    executable_hash: str
    friendly_name: str
    manifest_path: Path

    @property
    def key(self) -> str:
        return self.executable_hash

    @property
    def label(self) -> str:
        return self.friendly_name


@dataclass(frozen=True)
class TrackedAsset:
    application: TrackedApplication
    identity: ApplicationIdentity
    origin: str
    profile_id: str
    action: CaptionAction
    visual: str
    crop_size: tuple[int, int]
    rect: Optional[tuple[int, int, int, int]]
    image_path: Path
    image_rect: Optional[tuple[int, int, int, int]] = None
    configuration_state: str = "configured"

    @property
    def reference_rect(self) -> Optional[tuple[int, int, int, int]]:
        return self.image_rect or self.rect

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.application.executable_hash,
            self.identity.fingerprint,
            self.origin,
            self.action.name,
            self.visual,
        )

    @property
    def label(self) -> str:
        action = (
            self.visual.title()
            if self.action is CaptionAction.MAXIMIZE_RESTORE
            else self.action.name.title()
        )
        source = "manual" if self.origin == "user" else self.origin
        if self.configuration_state == "suggested":
            source = "suggested"
        elif self.configuration_state == "missing":
            source = "draw a box"
        return (
            f"{action} — {self.identity.window_state} · "
            f"{self.identity.dpi} DPI · {self.identity.theme} · "
            f"{source} · {self.identity.window_class}"
        )


@dataclass
class _VisionRequest:
    function: object
    args: tuple
    kwargs: dict
    completed: threading.Event
    result: object = None
    callback: object = None


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return cleaned[:60] or "application"


def rects_overlap(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> bool:
    return not (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )


def infer_missing_caption_rects(
    proposals: dict[CaptionAction, tuple[int, int, int, int]],
    image_size: tuple[int, int],
    *,
    caption_side: str,
    dpi: int,
) -> tuple[
    dict[CaptionAction, tuple[int, int, int, int]],
    frozenset[CaptionAction],
]:
    """Suggest missing adjacent caption slots without activating them."""
    width, height = image_size
    valid = {
        action: rect
        for action, rect in proposals.items()
        if (
            len(rect) == 4
            and 0 <= rect[0] < rect[2] <= width
            and 0 <= rect[1] < rect[3] <= height
        )
    }
    if not valid:
        return {}, frozenset()

    expected_width = max(24, round(36 * max(dpi, 1) / 96))
    measured_widths = sorted(rect[2] - rect[0] for rect in valid.values())
    measured_width = measured_widths[len(measured_widths) // 2]
    slot_width = (
        measured_width
        if round(expected_width * 0.6) <= measured_width <= round(expected_width * 1.6)
        else expected_width
    )
    order = (
        (
            CaptionAction.CLOSE,
            CaptionAction.MAXIMIZE_RESTORE,
            CaptionAction.MINIMIZE,
        )
        if caption_side == "left"
        else (
            CaptionAction.MINIMIZE,
            CaptionAction.MAXIMIZE_RESTORE,
            CaptionAction.CLOSE,
        )
    )
    rank = {action: index for index, action in enumerate(order)}
    completed = dict(valid)
    suggested: set[CaptionAction] = set()
    for action in order:
        if action in completed:
            continue
        anchor_action, anchor_rect = min(
            valid.items(),
            key=lambda item: abs(rank[item[0]] - rank[action]),
        )
        shift = (rank[action] - rank[anchor_action]) * slot_width
        candidate = (
            anchor_rect[0] + shift,
            anchor_rect[1],
            anchor_rect[2] + shift,
            anchor_rect[3],
        )
        if not (
            0 <= candidate[0] < candidate[2] <= width
            and 0 <= candidate[1] < candidate[3] <= height
        ):
            continue
        if any(rects_overlap(candidate, rect) for rect in completed.values()):
            continue
        completed[action] = candidate
        suggested.add(action)
    return completed, frozenset(suggested)


def normalized_rect(
    rect: tuple[int, int, int, int],
    size: tuple[int, int],
) -> tuple[float, float, float, float]:
    width, height = size
    return tuple(
        value
        for value in (
            rect[0] / width,
            rect[1] / height,
            rect[2] / width,
            rect[3] / height,
        )
    )


def denormalized_rect(
    rect: tuple[float, float, float, float],
    size: tuple[int, int],
) -> tuple[int, int, int, int]:
    width, height = size
    return (
        round(rect[0] * width),
        round(rect[1] * height),
        round(rect[2] * width),
        round(rect[3] * height),
    )


def fixed_caption_strip_rect(
    size: tuple[int, int],
    dpi: int,
    caption_side: str,
) -> tuple[int, int, int, int]:
    canvas_width, canvas_height = size
    strip_width = min(
        canvas_width,
        max(1, round(CAPTION_STRIP_WIDTH_DIP * dpi / 96)),
    )
    strip_height = min(
        canvas_height,
        max(1, round(CAPTION_STRIP_HEIGHT_DIP * dpi / 96)),
    )
    left = 0 if caption_side == "left" else canvas_width - strip_width
    return (left, 0, left + strip_width, strip_height)


def rect_is_within(
    rect: tuple[int, int, int, int],
    container: tuple[int, int, int, int],
) -> bool:
    return (
        container[0] <= rect[0] < rect[2] <= container[2]
        and container[1] <= rect[1] < rect[3] <= container[3]
    )


def qimage_to_bgr(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width = converted.width()
    height = converted.height()
    buffer = np.frombuffer(converted.bits(), dtype=np.uint8).reshape(
        (height, converted.bytesPerLine())
    )
    rgba = buffer[:, : width * 4].reshape((height, width, 4)).copy()
    return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)


def encode_png(image: np.ndarray) -> bytes:
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Could not encode vision crop")
    return encoded.tobytes()


def encode_jpeg(image: np.ndarray) -> bytes:
    success, encoded = cv2.imencode(
        ".jpg",
        image,
        [cv2.IMWRITE_JPEG_QUALITY, 95],
    )
    if not success:
        raise ValueError("Could not encode vision crop")
    return encoded.tobytes()


def visual_for_action(action: CaptionAction, window_state: str) -> str:
    if action is CaptionAction.MAXIMIZE_RESTORE:
        return "restore" if window_state == "maximized" else "maximize"
    return action.name.lower()


def preprocess(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.Canny(gray, 40, 120)


def is_informative_crop(image: np.ndarray) -> bool:
    if image.size == 0:
        return False
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 120)
    return float(gray.std()) >= 2.0 and cv2.countNonZero(edges) >= 4


def generated_template(action: CaptionAction, size: int) -> np.ndarray:
    canvas = np.zeros((size, size), dtype=np.uint8)
    thickness = max(1, size // 10)
    margin = max(2, size // 5)
    if action is CaptionAction.MINIMIZE:
        y = size - margin
        cv2.line(canvas, (margin, y), (size - margin, y), 255, thickness)
    elif action is CaptionAction.CLOSE:
        cv2.line(
            canvas,
            (margin, margin),
            (size - margin, size - margin),
            255,
            thickness,
        )
        cv2.line(
            canvas,
            (size - margin, margin),
            (margin, size - margin),
            255,
            thickness,
        )
    elif action is CaptionAction.MAXIMIZE_RESTORE:
        cv2.rectangle(
            canvas,
            (margin, margin),
            (size - margin, size - margin),
            255,
            thickness,
        )
    return canvas


class VisionMatcher:
    """Matches generated or learned glyph templates without invoking UI."""

    def propose(
        self,
        image: np.ndarray,
        *,
        dpi: int,
        caption_side: str,
    ) -> list[VisionMatch]:
        edges = preprocess(image)
        height, width = edges.shape
        slot_width = max(24, round(36 * dpi / 96))
        slot_height = min(height, max(24, round(34 * dpi / 96)))
        matches: list[VisionMatch] = []

        for action in CaptionAction:
            best_score = -1.0
            best_location = (0, 0)
            best_size = 0
            for base_size in (10, 12, 14, 16, 18, 20, 22, 24):
                size = max(8, round(base_size * dpi / 96))
                if size >= width or size >= height:
                    continue
                template = preprocess(
                    cv2.cvtColor(
                        generated_template(action, size),
                        cv2.COLOR_GRAY2BGR,
                    )
                )
                result = cv2.matchTemplate(
                    edges,
                    template,
                    cv2.TM_CCOEFF_NORMED,
                )
                _, score, _, location = cv2.minMaxLoc(result)
                if score > best_score:
                    best_score = float(score)
                    best_location = location
                    best_size = size
            if best_size == 0:
                continue
            center_x = best_location[0] + best_size // 2
            rect = (
                max(0, center_x - slot_width // 2),
                0,
                min(width, center_x + slot_width // 2),
                slot_height,
            )
            crop = image[rect[1] : rect[3], rect[0] : rect[2]]
            matches.append(
                VisionMatch(
                    action,
                    rect,
                    best_score,
                    "automatic",
                    encode_png(crop),
                )
            )

        matches.sort(key=lambda match: match.score, reverse=True)
        return self._reject_implausible_order(matches, caption_side)

    @staticmethod
    def _reject_implausible_order(
        matches: list[VisionMatch],
        caption_side: str,
    ) -> list[VisionMatch]:
        confident = [
            match for match in matches if match.score >= AUTOMATIC_SCORE
        ]
        for index, match in enumerate(confident):
            for other in confident[index + 1 :]:
                if rects_overlap(match.rect, other.rect):
                    return []
        if len(confident) < 2:
            return matches
        centers = {
            match.action: (match.rect[0] + match.rect[2]) / 2
            for match in confident
        }
        close = centers.get(CaptionAction.CLOSE)
        if close is None:
            return matches
        others = [
            center
            for action, center in centers.items()
            if action is not CaptionAction.CLOSE
        ]
        if caption_side == "right" and any(close <= value for value in others):
            return []
        if caption_side == "left" and any(close >= value for value in others):
            return []
        return matches

    def choose_at_point(
        self,
        matches: list[VisionMatch],
        point: tuple[int, int],
        *,
        final: bool,
    ) -> Optional[VisionMatch]:
        threshold = FINAL_SCORE if final else AUTOMATIC_SCORE
        containing = [
            match
            for match in matches
            if match.rect[0] <= point[0] < match.rect[2]
            and match.rect[1] <= point[1] < match.rect[3]
        ]
        containing.sort(key=lambda match: match.score, reverse=True)
        if not containing or containing[0].score < threshold:
            return None
        if (
            len(containing) > 1
            and containing[0].score - containing[1].score < WINNER_MARGIN
        ):
            return None
        return containing[0]

    def compare_crop(
        self,
        current: np.ndarray,
        template: np.ndarray,
    ) -> float:
        if current.size == 0 or template.size == 0:
            return 0.0
        current_edges = preprocess(current)
        template_edges = preprocess(template)
        if (
            template_edges.shape[0] > current_edges.shape[0]
            or template_edges.shape[1] > current_edges.shape[1]
        ):
            template_edges = cv2.resize(
                template_edges,
                (current_edges.shape[1], current_edges.shape[0]),
            )
        result = cv2.matchTemplate(
            current_edges,
            template_edges,
            cv2.TM_CCOEFF_NORMED,
        )
        return float(cv2.minMaxLoc(result)[1])


class VisionCache:
    def __init__(
        self,
        base_dir: Optional[Path] = None,
        *,
        legacy_base_dir: Optional[Path] = None,
    ) -> None:
        if base_dir is None:
            base_dir = (
                local_app_data_directory(DISPLAY_NAME) / "vision-cache"
            )
            legacy_base_dir = (
                local_app_data_directory(LEGACY_DATA_DIRECTORY)
                / "vision-cache"
            )
        self.base_dir = base_dir
        self.legacy_base_dir = legacy_base_dir
        self._io_lock = threading.RLock()

    def app_directory(self, identity: ApplicationIdentity) -> Path:
        return self.base_dir / safe_name(identity.friendly_name).lower()

    def manifest_path(self, identity: ApplicationIdentity) -> Path:
        return (
            self.app_directory(identity)
            / f"manifest_{identity.executable_hash}.json"
        )

    @staticmethod
    def _empty_manifest(identity: ApplicationIdentity) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "application": {
                "executable_path": identity.executable_path,
                "executable_hash": identity.executable_hash,
                "friendly_name": identity.friendly_name,
            },
            "assets": [],
            "contexts": [],
        }

    def _read_manifest(self, identity: ApplicationIdentity) -> dict:
        path = self.manifest_path(identity)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") != SCHEMA_VERSION:
                return self._empty_manifest(identity)
            if (
                data.get("application", {}).get("executable_hash")
                != identity.executable_hash
            ):
                return self._empty_manifest(identity)
            return data
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return self._empty_manifest(identity)

    @staticmethod
    def _read_tracked_manifest(path: Path) -> Optional[dict]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if (
                data.get("schema_version") != SCHEMA_VERSION
                or not isinstance(data.get("application"), dict)
                or not isinstance(data.get("contexts"), list)
            ):
                return None
            return data
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _referenced_files(data: dict) -> set[str]:
        referenced = {
            context["caption_asset"]["image_file"]
            for context in data.get("contexts", [])
            if context.get("caption_asset")
            and context["caption_asset"].get("image_file")
        }
        referenced.update(
            item["image_file"]
            for context in data.get("contexts", [])
            for item in context.get("buttons", [])
            if item.get("image_file")
        )
        return referenced

    def _all_referenced_files(self, directory: Path) -> set[str]:
        referenced = set()
        for manifest_path in directory.glob("manifest_*.json"):
            data = self._read_tracked_manifest(manifest_path)
            if data is not None:
                referenced.update(self._referenced_files(data))
        return referenced

    def list_tracked_applications(self) -> list[TrackedApplication]:
        applications = {}
        if not self.base_dir.exists():
            return []
        for path in self.base_dir.glob("*/manifest_*.json"):
            data = self._read_tracked_manifest(path)
            if data is None:
                continue
            application_data = data["application"]
            try:
                application = TrackedApplication(
                    str(application_data["executable_hash"]),
                    str(application_data["friendly_name"]),
                    path,
                )
            except (KeyError, TypeError, ValueError):
                continue
            if self.list_tracked_assets(application):
                applications[application.key] = application
        return sorted(
            applications.values(),
            key=lambda item: (item.friendly_name.casefold(), item.key),
        )

    def list_tracked_assets(
        self,
        application: TrackedApplication,
    ) -> list[TrackedAsset]:
        data = self._read_tracked_manifest(application.manifest_path)
        if (
            data is None
            or data["application"].get("executable_hash")
            != application.executable_hash
        ):
            return []
        assets = []
        try:
            for context in data["contexts"]:
                identity = ApplicationIdentity(**context["identity"])
                crop_size = (
                    int(context["crop_size"][0]),
                    int(context["crop_size"][1]),
                )
                caption_asset = context.get("caption_asset") or {}
                grouped_file = (
                    caption_asset.get("image_file")
                    if caption_asset.get("status") == "available"
                    else None
                )
                grouped_rect = (
                    denormalized_rect(
                        tuple(
                            float(value)
                            for value in caption_asset["rect"]
                        ),
                        crop_size,
                    )
                    if grouped_file and caption_asset.get("rect") is not None
                    else None
                )
                configured_rects = {
                    CaptionAction[button["action"]]: denormalized_rect(
                        tuple(float(value) for value in button["rect"]),
                        crop_size,
                    )
                    for button in context["buttons"]
                    if button.get("status") == "available"
                    and button.get("rect") is not None
                }
                completed_rects, suggested_actions = infer_missing_caption_rects(
                    configured_rects,
                    crop_size,
                    caption_side=identity.caption_side,
                    dpi=identity.dpi,
                )
                for button in context["buttons"]:
                    image_file = grouped_file or button.get("image_file")
                    configured = (
                        button.get("status") == "available"
                        and button.get("rect") is not None
                    )
                    if not image_file or (not configured and not grouped_file):
                        continue
                    image_path = (
                        application.manifest_path.parent
                        / image_file
                    )
                    if (
                        not image_path.is_file()
                        or QImage(str(image_path)).isNull()
                    ):
                        continue
                    action = CaptionAction[button["action"]]
                    rect = (
                        configured_rects[action]
                        if configured
                        else completed_rects.get(action)
                    )
                    assets.append(
                        TrackedAsset(
                            application,
                            identity,
                            str(context["origin"]),
                            str(context["profile_id"]),
                            action,
                            str(button["visual"]),
                            crop_size,
                            rect,
                            image_path,
                            grouped_rect,
                            (
                                "configured"
                                if configured
                                else (
                                    "suggested"
                                    if action in suggested_actions
                                    else "missing"
                                )
                            ),
                        )
                    )
        except (KeyError, TypeError, ValueError):
            return []
        action_order = {
            CaptionAction.MINIMIZE: 0,
            CaptionAction.MAXIMIZE_RESTORE: 1,
            CaptionAction.CLOSE: 2,
        }
        return sorted(
            assets,
            key=lambda item: (
                action_order[item.action],
                item.visual,
                item.identity.window_state,
                item.identity.dpi,
                item.identity.theme,
                0 if item.origin == "user" else 1,
                item.origin,
                item.identity.window_class,
            ),
        )

    @staticmethod
    def _profile_id(
        identity: ApplicationIdentity,
        origin: str,
        buttons: list[dict],
        caption_asset: Optional[dict] = None,
    ) -> str:
        return hashlib.sha256(
            (
                identity.fingerprint
                + origin
                + json.dumps(buttons, sort_keys=True)
                + json.dumps(caption_asset, sort_keys=True)
            ).encode("utf-8")
        ).hexdigest()[:20]

    def update_tracked_rect(
        self,
        asset: TrackedAsset,
        rect: tuple[int, int, int, int],
    ) -> TrackedAsset:
        with self._io_lock:
            return self._update_tracked_rect_unlocked(asset, rect)

    def _update_tracked_rect_unlocked(
        self,
        asset: TrackedAsset,
        rect: tuple[int, int, int, int],
    ) -> TrackedAsset:
        width, height = asset.crop_size
        if not (
            0 <= rect[0] < rect[2] <= width
            and 0 <= rect[1] < rect[3] <= height
        ):
            raise ValueError("The action rectangle is outside the preview.")
        data = self._read_tracked_manifest(asset.application.manifest_path)
        if (
            data is None
            or data["application"].get("executable_hash")
            != asset.application.executable_hash
        ):
            raise FileNotFoundError("The tracked manifest is unavailable.")
        source_context = None
        source_button = None
        for context in data["contexts"]:
            if (
                context.get("identity") == asdict(asset.identity)
                and context.get("origin") == asset.origin
            ):
                source_context = context
                for button in context.get("buttons", []):
                    if (
                        button.get("action") == asset.action.name
                        and button.get("visual") == asset.visual
                        and (
                            (
                                source_context.get("caption_asset") or {}
                            ).get("image_file")
                            or button.get("image_file")
                        )
                        == asset.image_path.name
                    ):
                        source_button = button
                        break
                break
        if source_context is None or source_button is None:
            raise FileNotFoundError(
                "The selected tracked action is no longer available."
            )
        if not asset.image_path.is_file():
            raise FileNotFoundError("The tracked JPEG is unavailable.")

        user_context = next(
            (
                context
                for context in data["contexts"]
                if (
                    context.get("identity") == asdict(asset.identity)
                    and context.get("origin") == "user"
                )
            ),
            None,
        )
        if user_context is None:
            user_context = {
                "profile_id": "",
                "origin": "user",
                "identity": asdict(asset.identity),
                "crop_size": [width, height],
                "buttons": [],
                "caption_asset": dict(
                    source_context.get("caption_asset") or {}
                ),
            }
            data["contexts"].append(user_context)
        elif tuple(user_context.get("crop_size", ())) != (width, height):
            raise ValueError(
                "The manual profile uses a different capture size."
            )

        source_caption = source_context.get("caption_asset") or {}
        if source_caption.get("status") == "available":
            user_context["caption_asset"] = dict(source_caption)
            for button in user_context.get("buttons", []):
                button.pop("image_file", None)

        selected_button = next(
            (
                button
                for button in user_context.get("buttons", [])
                if (
                    button.get("action") == asset.action.name
                    and button.get("visual") == asset.visual
                )
            ),
            None,
        )
        if selected_button is None:
            selected_button = {
                "action": asset.action.name,
                "visual": asset.visual,
                "status": "available",
                "rect": None,
            }
            user_context.setdefault("buttons", []).append(selected_button)
        selected_button["status"] = "available"
        selected_button["rect"] = list(
            normalized_rect(rect, asset.crop_size)
        )
        if (
            user_context.get("caption_asset") or {}
        ).get("status") == "available":
            selected_button.pop("image_file", None)
        elif source_button.get("image_file"):
            selected_button["image_file"] = source_button["image_file"]
        user_context["buttons"].sort(
            key=lambda item: (
                CaptionAction[item["action"]].value,
                str(item.get("visual", "")),
            )
        )
        user_context["profile_id"] = self._profile_id(
            asset.identity,
            "user",
            user_context["buttons"],
            user_context.get("caption_asset"),
        )
        data["contexts"].sort(
            key=lambda item: (
                item["identity"]["window_class"],
                item["identity"]["dpi"],
                item["identity"]["theme"],
                item["identity"]["window_state"],
                item["origin"],
            )
        )
        temporary = (
            asset.application.manifest_path.parent
            / f".{asset.application.manifest_path.name}.tmp"
        )
        temporary.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, asset.application.manifest_path)
        return TrackedAsset(
            asset.application,
            asset.identity,
            "user",
            user_context["profile_id"],
            asset.action,
            asset.visual,
            asset.crop_size,
            rect,
            asset.image_path,
            asset.image_rect,
        )

    def delete_tracked_application(
        self,
        application: TrackedApplication,
    ) -> None:
        """Remove one executable's manifest and JPEGs it alone owns."""
        with self._io_lock:
            manifest_path = application.manifest_path
            data = self._read_tracked_manifest(manifest_path)
            if (
                data is None
                or data["application"].get("executable_hash")
                != application.executable_hash
            ):
                raise FileNotFoundError(
                    "The tracked application is no longer available."
                )
            directory = manifest_path.parent
            owned_files = self._referenced_files(data)
            manifest_path.unlink()
            retained_files = self._all_referenced_files(directory)
            for filename in owned_files - retained_files:
                if filename != Path(filename).name:
                    continue
                try:
                    (directory / filename).unlink()
                except FileNotFoundError:
                    pass
            try:
                if not any(directory.iterdir()):
                    directory.rmdir()
            except OSError:
                pass

    def load(self, identity: ApplicationIdentity) -> list[VisionProfile]:
        directory = self.app_directory(identity)
        data = self._read_manifest(identity)
        profiles = []
        try:
            for context in data["contexts"]:
                if context["identity"] != asdict(identity):
                    continue
                caption_asset = context.get("caption_asset") or {}
                grouped_file = (
                    caption_asset.get("image_file")
                    if caption_asset.get("status") == "available"
                    else None
                )
                buttons = tuple(
                    CachedButton(
                        CaptionAction[item["action"]],
                        tuple(float(value) for value in item["rect"]),
                        grouped_file or item["image_file"],
                        item["visual"],
                    )
                    for item in context["buttons"]
                    if item.get("status") == "available"
                    and (grouped_file or item.get("image_file"))
                )
                profiles.append(
                    VisionProfile(
                        context["profile_id"],
                        context["origin"],
                        identity,
                        tuple(context["crop_size"]),
                        buttons,
                        directory,
                        grouped_file,
                        (
                            tuple(
                                float(value)
                                for value in caption_asset["rect"]
                            )
                            if grouped_file
                            and caption_asset.get("rect") is not None
                            else None
                        ),
                    )
                )
        except (KeyError, TypeError, ValueError):
            return []
        return profiles

    @staticmethod
    def _pixel_hash(image: np.ndarray) -> str:
        digest = hashlib.sha256()
        digest.update(str(image.shape).encode("ascii"))
        digest.update(image.tobytes())
        return digest.hexdigest()[:20]

    def save(
        self,
        *,
        identity: ApplicationIdentity,
        origin: str,
        image: np.ndarray,
        assignments: dict[CaptionAction, tuple[int, int, int, int]],
        statuses: Optional[dict[CaptionAction, str]] = None,
        visuals: Optional[dict[CaptionAction, str]] = None,
    ) -> VisionProfile:
        with self._io_lock:
            return self._save_unlocked(
                identity=identity,
                origin=origin,
                image=image,
                assignments=assignments,
                statuses=statuses,
                visuals=visuals,
            )

    def observation_statuses(
        self,
        identity: ApplicationIdentity,
        origin: str = "automatic",
    ) -> dict[tuple[CaptionAction, str], str]:
        with self._io_lock:
            manifest = self._read_manifest(identity)
            context = next(
                (
                    item
                    for item in manifest["contexts"]
                    if item.get("identity") == asdict(identity)
                    and item.get("origin") == origin
                ),
                None,
            )
            if context is None:
                return {}
            result = {}
            for item in context.get("buttons", []):
                try:
                    action = CaptionAction[item["action"]]
                    visual = str(
                        item.get("visual")
                        or visual_for_action(action, identity.window_state)
                    )
                    result[(action, visual)] = str(
                        item.get("status", "unresolved")
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            if (
                origin == "automatic"
                and context.get("capture_layout_version")
                != AUTOMATIC_LAYOUT_VERSION
            ):
                return {
                    key: (
                        "unavailable"
                        if status == "unavailable"
                        else "unresolved"
                    )
                    for key, status in result.items()
                }
            return result

    def save_observation(
        self,
        *,
        identity: ApplicationIdentity,
        image: np.ndarray,
        assignments: dict[CaptionAction, tuple[int, int, int, int]],
        statuses: Optional[dict[CaptionAction, str]] = None,
        visuals: Optional[dict[CaptionAction, str]] = None,
    ) -> ObservationResult:
        """Persist independently validated automatic caption observations."""
        with self._io_lock:
            statuses = dict(statuses or {})
            visuals = dict(visuals or {})
            before = self.observation_statuses(identity)
            height, width = image.shape[:2]
            strip_rect = fixed_caption_strip_rect(
                (width, height),
                identity.dpi,
                identity.caption_side,
            )
            valid_assignments = {}
            for action, rect in assignments.items():
                in_bounds = (
                    len(rect) == 4
                    and 0 <= rect[0] < rect[2] <= width
                    and 0 <= rect[1] < rect[3] <= height
                    and rect_is_within(rect, strip_rect)
                )
                crop = (
                    image[rect[1] : rect[3], rect[0] : rect[2]]
                    if in_bounds
                    else np.empty((0, 0, 3), dtype=np.uint8)
                )
                if in_bounds and is_informative_crop(crop):
                    valid_assignments[action] = rect
                    statuses[action] = "available"
                else:
                    statuses[action] = "unresolved"

            profile = self._save_unlocked(
                identity=identity,
                origin="automatic",
                image=image,
                assignments=valid_assignments,
                statuses=statuses,
                visuals=visuals,
            )
            after = self.observation_statuses(identity)
            saved = set()
            existing = set()
            unavailable = set()
            unresolved = set()
            for action in CaptionAction:
                visual = visuals.get(
                    action,
                    visual_for_action(action, identity.window_state),
                )
                key = (action, visual)
                state = after.get(key, "unresolved")
                if state == "available":
                    if before.get(key) == "available":
                        existing.add(key)
                    else:
                        saved.add(key)
                elif state == "unavailable":
                    unavailable.add(key)
                else:
                    unresolved.add(key)
            return ObservationResult(
                profile,
                frozenset(saved),
                frozenset(existing),
                frozenset(unavailable),
                frozenset(unresolved),
            )

    def _save_unlocked(
        self,
        *,
        identity: ApplicationIdentity,
        origin: str,
        image: np.ndarray,
        assignments: dict[CaptionAction, tuple[int, int, int, int]],
        statuses: Optional[dict[CaptionAction, str]] = None,
        visuals: Optional[dict[CaptionAction, str]] = None,
    ) -> VisionProfile:
        height, width = image.shape[:2]
        statuses = statuses or {}
        visuals = visuals or {}
        directory = self.app_directory(identity)
        directory.mkdir(parents=True, exist_ok=True)
        manifest = self._read_manifest(identity)
        existing_context = next(
            (
                context
                for context in manifest["contexts"]
                if context.get("identity") == asdict(identity)
                and context.get("origin") == origin
            ),
            None,
        )
        existing_layout_is_current = (
            (existing_context or {}).get("capture_layout_version")
            == AUTOMATIC_LAYOUT_VERSION
            and bool((existing_context or {}).get("caption_asset"))
        )
        previous_buttons = {
            item["action"]: item
            for item in (existing_context or {}).get("buttons", [])
        }
        strip_rect = fixed_caption_strip_rect(
            (width, height),
            identity.dpi,
            identity.caption_side,
        )

        merged_assignments = dict(assignments)
        if origin == "automatic" and existing_layout_is_current:
            for action in CaptionAction:
                previous = previous_buttons.get(action.name)
                if (
                    action not in merged_assignments
                    and previous
                    and previous.get("status") == "available"
                    and previous.get("rect") is not None
                ):
                    merged_assignments[action] = denormalized_rect(
                        tuple(float(value) for value in previous["rect"]),
                        (width, height),
                    )

        crops = {}
        for action, rect in merged_assignments.items():
            if not (
                len(rect) == 4
                and 0 <= rect[0] < rect[2] <= width
                and 0 <= rect[1] < rect[3] <= height
                and rect_is_within(rect, strip_rect)
            ):
                raise ValueError(
                    f"{action.name.title()} crop is outside the fixed "
                    "caption strip."
                )
            crop = image[rect[1] : rect[3], rect[0] : rect[2]]
            if (
                action in assignments
                and not is_informative_crop(crop)
            ):
                raise ValueError(
                    f"{action.name.title()} crop contains too little "
                    "visual information."
                )
            crops[action] = crop

        caption_asset = None
        if crops:
            group_rect = strip_rect
            group_crop = image[
                group_rect[1] : group_rect[3],
                group_rect[0] : group_rect[2],
            ]
            if not is_informative_crop(group_crop):
                raise ValueError(
                    "Caption group contains too little visual information."
                )
            pixel_hash = self._pixel_hash(group_crop)
            assets_by_hash = {
                asset["pixel_hash"]: asset["image_file"]
                for asset in manifest["assets"]
            }
            filename = assets_by_hash.get(pixel_hash)
            if filename is None:
                app_name = safe_name(identity.friendly_name).lower()
                state = safe_name(identity.window_state).lower()
                filename = (
                    f"{app_name}_caption_{state}_{pixel_hash[:12]}.jpg"
                )
                temporary = directory / f".{filename}.tmp"
                temporary.write_bytes(encode_jpeg(group_crop))
                os.replace(temporary, directory / filename)
                manifest["assets"].append(
                    {
                        "pixel_hash": pixel_hash,
                        "image_file": filename,
                        "kind": "caption_group",
                    }
                )
            caption_asset = {
                "status": "available",
                "rect": list(
                    normalized_rect(group_rect, (width, height))
                ),
                "image_file": filename,
            }
        elif existing_layout_is_current:
            caption_asset = existing_context.get("caption_asset")

        button_items = []
        cached_buttons = []
        for action in CaptionAction:
            visual = visuals.get(
                action,
                visual_for_action(action, identity.window_state),
            )
            if action in crops:
                normalized = normalized_rect(
                    merged_assignments[action],
                    (width, height),
                )
                item = {
                    "action": action.name,
                    "visual": visual,
                    "status": "available",
                    "rect": list(normalized),
                }
                cached_buttons.append(
                    CachedButton(
                        action,
                        normalized,
                        caption_asset["image_file"],
                        visual,
                    )
                )
            elif (
                origin == "automatic"
                and previous_buttons.get(action.name, {}).get("status")
                == "available"
                and (
                    existing_layout_is_current
                    or action not in statuses
                )
            ):
                item = previous_buttons[action.name]
                cached_buttons.append(
                    CachedButton(
                        action,
                        tuple(item["rect"]),
                        caption_asset["image_file"],
                        item["visual"],
                    )
                )
            elif (
                origin == "automatic"
                and action.name in previous_buttons
                and action not in statuses
            ):
                item = previous_buttons[action.name]
            else:
                item = {
                    "action": action.name,
                    "visual": visual,
                    "status": statuses.get(action, "unresolved"),
                    "rect": None,
                }
            button_items.append(item)

        profile_id = self._profile_id(
            identity,
            origin,
            button_items,
            caption_asset,
        )
        context_item = {
            "profile_id": profile_id,
            "origin": origin,
            "identity": asdict(identity),
            "crop_size": [width, height],
            "buttons": button_items,
            "caption_asset": caption_asset,
        }
        if origin == "automatic":
            context_item["capture_layout_version"] = (
                AUTOMATIC_LAYOUT_VERSION
            )
        manifest["contexts"] = [
            context
            for context in manifest["contexts"]
            if not (
                context.get("identity") == asdict(identity)
                and context.get("origin") == origin
            )
        ]
        manifest["contexts"].append(context_item)
        if origin == "automatic" and caption_asset is not None:
            for context in manifest["contexts"]:
                if (
                    context is context_item
                    or context.get("origin") != "user"
                    or context.get("identity") != asdict(identity)
                    or tuple(context.get("crop_size", ()))
                    != (width, height)
                ):
                    continue
                context["caption_asset"] = dict(caption_asset)
                context.pop("legacy_individual_assets", None)
                for button in context.get("buttons", []):
                    button.pop("image_file", None)
                context["profile_id"] = self._profile_id(
                    identity,
                    "user",
                    context["buttons"],
                    context.get("caption_asset"),
                )
        manifest["contexts"].sort(
            key=lambda item: (
                item["identity"]["window_class"],
                item["identity"]["dpi"],
                item["identity"]["theme"],
                item["identity"]["window_state"],
                item["origin"],
            )
        )

        referenced = self._referenced_files(manifest)
        manifest["assets"] = [
            asset
            for asset in manifest["assets"]
            if asset["image_file"] in referenced
        ]
        manifest_path = self.manifest_path(identity)
        temporary_manifest = directory / f".{manifest_path.name}.tmp"
        temporary_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary_manifest, manifest_path)
        all_referenced = self._all_referenced_files(directory)
        for pattern in ("*.jpg", "*.jpeg", "*.png"):
            for stale_crop in directory.glob(pattern):
                if stale_crop.name not in all_referenced:
                    stale_crop.unlink()
        return VisionProfile(
            profile_id,
            origin,
            identity,
            (width, height),
            tuple(cached_buttons),
            directory,
            (
                caption_asset.get("image_file")
                if caption_asset
                else None
            ),
            (
                tuple(caption_asset["rect"])
                if caption_asset and caption_asset.get("rect")
                else None
            ),
        )

    def migrate_legacy(self) -> None:
        if self.legacy_base_dir is not None:
            self._upgrade_consolidated_manifests(self.legacy_base_dir)
            self._migrate_legacy_storage()
        self._upgrade_consolidated_manifests(self.base_dir)
        if not self.base_dir.exists():
            return

        for legacy_manifest in list(
            self.base_dir.glob("*/*/manifest.json")
        ):
            legacy_directory = legacy_manifest.parent
            remove_legacy = False
            try:
                data = json.loads(
                    legacy_manifest.read_text(encoding="utf-8")
                )
                if data.get("schema_version") != LEGACY_SCHEMA_VERSION:
                    raise ValueError("Unsupported legacy manifest")
                identity = ApplicationIdentity(**data["identity"])
                width, height = (
                    int(data["crop_size"][0]),
                    int(data["crop_size"][1]),
                )
                image = np.zeros((height, width, 3), dtype=np.uint8)
                assignments = {}
                for item in data["buttons"]:
                    action = CaptionAction[item["action"]]
                    rect = denormalized_rect(
                        tuple(float(value) for value in item["rect"]),
                        (width, height),
                    )
                    crop = cv2.imread(
                        str(legacy_directory / item["image_file"])
                    )
                    if crop is None:
                        raise ValueError("Missing legacy crop")
                    crop_width = rect[2] - rect[0]
                    crop_height = rect[3] - rect[1]
                    if crop.shape[:2] != (crop_height, crop_width):
                        crop = cv2.resize(crop, (crop_width, crop_height))
                    image[rect[1] : rect[3], rect[0] : rect[2]] = crop
                    assignments[action] = rect
                self.save(
                    identity=identity,
                    origin=data["origin"],
                    image=image,
                    assignments=assignments,
                )
                remove_legacy = True
            except OSError:
                pass
            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                pass
            finally:
                if remove_legacy:
                    shutil.rmtree(legacy_directory, ignore_errors=True)

    @staticmethod
    def _upgrade_consolidated_manifests(root: Path) -> None:
        if not root.exists():
            return
        for manifest_path in root.glob("*/manifest_*.json"):
            try:
                data = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                if data.get("schema_version") != CONSOLIDATED_SCHEMA_VERSION:
                    continue
                data["schema_version"] = SCHEMA_VERSION
                for context in data.get("contexts", []):
                    context["legacy_individual_assets"] = True
                    if context.get("origin") == "automatic":
                        context.pop("capture_layout_version", None)
                temporary = (
                    manifest_path.parent / f".{manifest_path.name}.tmp"
                )
                temporary.write_text(
                    json.dumps(data, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                os.replace(temporary, manifest_path)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue

    @staticmethod
    def _replace_image_references(
        data: dict,
        replacements: dict[str, str],
    ) -> None:
        for asset in data.get("assets", []):
            filename = asset.get("image_file")
            if filename in replacements:
                asset["image_file"] = replacements[filename]
        for context in data.get("contexts", []):
            caption_asset = context.get("caption_asset") or {}
            filename = caption_asset.get("image_file")
            if filename in replacements:
                caption_asset["image_file"] = replacements[filename]
            for button in context.get("buttons", []):
                filename = button.get("image_file")
                if filename in replacements:
                    button["image_file"] = replacements[filename]

    @staticmethod
    def _context_key(context: dict) -> str:
        return json.dumps(
            {
                "identity": context.get("identity"),
                "origin": context.get("origin"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _merge_manifest_data(
        self,
        target: Optional[dict],
        source: dict,
        *,
        source_is_newer: bool,
    ) -> dict:
        if target is None:
            return source
        contexts = {
            self._context_key(context): context
            for context in target.get("contexts", [])
        }
        for context in source.get("contexts", []):
            key = self._context_key(context)
            if source_is_newer or key not in contexts:
                contexts[key] = context
        merged = {
            "schema_version": SCHEMA_VERSION,
            "application": source["application"],
            "contexts": sorted(
                contexts.values(),
                key=lambda item: self._context_key(item),
            ),
            "assets": [],
        }
        assets = {
            asset["image_file"]: asset
            for asset in target.get("assets", [])
            if asset.get("image_file")
        }
        assets.update(
            {
                asset["image_file"]: asset
                for asset in source.get("assets", [])
                if asset.get("image_file")
            }
        )
        referenced = self._referenced_files(merged)
        merged["assets"] = [
            assets[filename]
            for filename in sorted(referenced)
            if filename in assets
        ]
        return merged

    @staticmethod
    def _asset_destination(
        source: Path,
        target_directory: Path,
        executable_hash: str,
    ) -> Path:
        target = target_directory / source.name
        if not target.exists() or target.read_bytes() == source.read_bytes():
            return target
        candidate = target.with_name(
            f"{target.stem}_{executable_hash}{target.suffix}"
        )
        if (
            not candidate.exists()
            or candidate.read_bytes() == source.read_bytes()
        ):
            return candidate
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
        return target.with_name(
            f"{target.stem}_{executable_hash}_{digest}{target.suffix}"
        )

    def _migrate_legacy_storage(self) -> None:
        legacy_root = self.legacy_base_dir
        if legacy_root is None or not legacy_root.exists():
            return
        self.base_dir.mkdir(parents=True, exist_ok=True)
        for source_directory in list(legacy_root.iterdir()):
            if not source_directory.is_dir():
                continue
            manifests = list(source_directory.glob("manifest_*.json"))
            if not manifests:
                continue
            directory_succeeded = True
            for source_manifest in manifests:
                temporary_manifest = None
                try:
                    source_data = self._read_tracked_manifest(
                        source_manifest
                    )
                    if source_data is None:
                        raise ValueError("Invalid legacy manifest")
                    application = source_data["application"]
                    executable_hash = str(application["executable_hash"])
                    friendly_name = str(application["friendly_name"])
                    target_directory = (
                        self.base_dir / safe_name(friendly_name).lower()
                    )
                    target_directory.mkdir(parents=True, exist_ok=True)
                    replacements = {}
                    for filename in self._referenced_files(source_data):
                        source_asset = source_directory / filename
                        if not source_asset.is_file():
                            raise FileNotFoundError(source_asset)
                        destination = self._asset_destination(
                            source_asset,
                            target_directory,
                            executable_hash,
                        )
                        replacements[filename] = destination.name
                        if not destination.exists():
                            temporary_asset = destination.with_name(
                                f".{destination.name}.tmp"
                            )
                            shutil.copy2(source_asset, temporary_asset)
                            os.replace(temporary_asset, destination)
                    source_data = json.loads(json.dumps(source_data))
                    self._replace_image_references(
                        source_data,
                        replacements,
                    )
                    target_manifest = (
                        target_directory
                        / f"manifest_{executable_hash}.json"
                    )
                    target_data = self._read_tracked_manifest(
                        target_manifest
                    )
                    merged = self._merge_manifest_data(
                        target_data,
                        source_data,
                        source_is_newer=(
                            not target_manifest.exists()
                            or source_manifest.stat().st_mtime_ns
                            >= target_manifest.stat().st_mtime_ns
                        ),
                    )
                    temporary_manifest = target_directory / (
                        f".{target_manifest.name}.tmp"
                    )
                    temporary_manifest.write_text(
                        json.dumps(merged, indent=2, sort_keys=True),
                        encoding="utf-8",
                    )
                    validated = self._read_tracked_manifest(
                        temporary_manifest
                    )
                    if validated is None:
                        raise ValueError("Migrated manifest did not validate")
                    for filename in self._referenced_files(validated):
                        image_path = target_directory / filename
                        if (
                            not image_path.is_file()
                            or QImage(str(image_path)).isNull()
                        ):
                            raise ValueError(
                                "Migrated image did not validate"
                            )
                    os.replace(temporary_manifest, target_manifest)
                except (
                    OSError,
                    KeyError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    directory_succeeded = False
                    if temporary_manifest is not None:
                        try:
                            temporary_manifest.unlink()
                        except OSError:
                            pass
            if directory_succeeded:
                shutil.rmtree(source_directory)
        try:
            if not any(legacy_root.iterdir()):
                legacy_root.rmdir()
                legacy_parent = legacy_root.parent
                if legacy_parent.exists() and not any(
                    legacy_parent.iterdir()
                ):
                    legacy_parent.rmdir()
        except OSError:
            pass

    def clear(self) -> None:
        with self._io_lock:
            if self.base_dir.exists():
                shutil.rmtree(self.base_dir)
            if (
                self.legacy_base_dir is not None
                and self.legacy_base_dir.exists()
            ):
                shutil.rmtree(self.legacy_base_dir)

    def export_all_data(
        self,
        destination_parent: Path,
    ) -> DataExportResult:
        with self._io_lock:
            return export_application_data(
                destination_parent,
                current_root=self.base_dir.parent,
                legacy_root=(
                    self.legacy_base_dir.parent
                    if self.legacy_base_dir is not None
                    else None
                ),
            )


class CaptionVisionDetector:
    """Captures on the Qt thread and performs CV/cache I/O off-thread."""

    def __init__(
        self,
        cache: Optional[VisionCache] = None,
        *,
        worker_timeout_ms: int = 150,
        shutdown_timeout_s: float = 0.5,
    ) -> None:
        self.cache = cache or VisionCache()
        self.matcher = VisionMatcher()
        self.worker_timeout_ms = worker_timeout_ms
        self.shutdown_timeout_s = shutdown_timeout_s
        self._requests: queue.Queue[Optional[_VisionRequest]] = queue.Queue(
            maxsize=1
        )
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._busy = False
        self._stable: dict[tuple[str, CaptionAction], tuple[tuple[int, ...], int]] = {}
        self._profiles: dict[str, list[VisionProfile]] = {}
        self._observed_assets: set[
            tuple[str, CaptionAction, str]
        ] = set()
        self._pending_observations: set[str] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        try:
            self.cache.migrate_legacy()
        except OSError:
            pass
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker,
                name="CaptionVision",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(self.shutdown_timeout_s)
        if thread is None or not thread.is_alive():
            self._thread = None

    @staticmethod
    def capture_rect(context: VisionContext) -> tuple[int, int, int, int]:
        left, top, right, bottom = context.bounds
        window_width = right - left
        window_height = bottom - top
        width = max(
            1,
            min(round(320 * context.dpi / 96), round(window_width * 0.45)),
        )
        height = max(
            1,
            min(round(96 * context.dpi / 96), round(window_height * 0.20)),
        )
        if context.identity.caption_side == "left":
            return (left, top, left + width, top + height)
        return (right - width, top, right, top + height)

    def capture(
        self,
        context: VisionContext,
        *,
        window_capture: bool = False,
    ) -> Optional[QImage]:
        left, top, right, bottom = self.capture_rect(context)
        screen = QGuiApplication.screenAt(QPoint(left, top))
        if screen is None:
            return None
        if window_capture:
            window_left, window_top, _window_right, _window_bottom = (
                context.bounds
            )
            pixmap = screen.grabWindow(
                context.hwnd,
                left - window_left,
                top - window_top,
                right - left,
                bottom - top,
            )
        else:
            geometry = screen.geometry()
            pixmap = screen.grabWindow(
                0,
                left - geometry.left(),
                top - geometry.top(),
                right - left,
                bottom - top,
            )
        if pixmap.isNull():
            return None
        image = pixmap.toImage()
        if image.isNull() or image.width() != right - left:
            return None
        return image

    def _run(self, function, *args, **kwargs):
        with self._lock:
            if self._busy or self._thread is None:
                return None
            self._busy = True
        request = _VisionRequest(
            function,
            args,
            kwargs,
            threading.Event(),
        )
        try:
            self._requests.put_nowait(request)
        except queue.Full:
            with self._lock:
                self._busy = False
            return None
        if not request.completed.wait(self.worker_timeout_ms / 1000.0):
            return None
        return request.result

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            request = self._requests.get()
            if request is None:
                return
            try:
                request.result = request.function(
                    *request.args,
                    **request.kwargs,
                )
            except Exception:
                request.result = None
            finally:
                request.completed.set()
                with self._lock:
                    self._busy = False
                if request.callback is not None:
                    try:
                        request.callback(request.result)
                    except Exception:
                        pass

    def _enqueue(self, function, *args, callback=None, **kwargs) -> bool:
        with self._lock:
            if self._busy or self._thread is None:
                return False
            self._busy = True
        request = _VisionRequest(
            function,
            args,
            kwargs,
            threading.Event(),
            callback=callback,
        )
        try:
            self._requests.put_nowait(request)
        except queue.Full:
            with self._lock:
                self._busy = False
            return False
        return True

    def proposals(
        self,
        image: QImage,
        context: VisionContext,
    ) -> list[VisionMatch]:
        bgr = qimage_to_bgr(image)
        return self._run(
            self.matcher.propose,
            bgr,
            dpi=context.dpi,
            caption_side=context.identity.caption_side,
        ) or []

    def observe_caption_assets(
        self,
        context: VisionContext,
        assignments: dict[CaptionAction, tuple[int, int, int, int]],
        statuses: dict[CaptionAction, str],
        visuals: dict[CaptionAction, str],
    ) -> None:
        key = context.identity.fingerprint
        requested = {
            (
                key,
                action,
                visuals.get(
                    action,
                    visual_for_action(action, context.identity.window_state),
                ),
            )
            for action in CaptionAction
        }
        with self._lock:
            if (
                requested.issubset(self._observed_assets)
                or key in self._pending_observations
            ):
                return
            self._pending_observations.add(key)
        image = self.capture(context)
        if image is None:
            with self._lock:
                self._pending_observations.discard(key)
            return
        bgr = qimage_to_bgr(image)

        def completed(result) -> None:
            with self._lock:
                self._pending_observations.discard(key)
                if isinstance(result, ObservationResult):
                    self._observed_assets.update(
                        (key, action, visual)
                        for action, visual in result.complete
                    )
                if isinstance(result, ObservationResult) and result.saved:
                    self._profiles.pop(
                        context.identity.fingerprint,
                        None,
                    )

        queued = self._enqueue(
            self._save_observation,
            context,
            bgr,
            dict(assignments),
            dict(statuses),
            dict(visuals),
            callback=completed,
        )
        if not queued:
            with self._lock:
                self._pending_observations.discard(key)

    def _save_observation(
        self,
        context: VisionContext,
        image: np.ndarray,
        assignments: dict[CaptionAction, tuple[int, int, int, int]],
        statuses: dict[CaptionAction, str],
        visuals: dict[CaptionAction, str],
    ) -> Optional[ObservationResult]:
        existing = self.cache.observation_statuses(context.identity)
        pending_actions = {
            action
            for action in CaptionAction
            if existing.get(
                (
                    action,
                    visuals.get(
                        action,
                        visual_for_action(
                            action,
                            context.identity.window_state,
                        ),
                    ),
                )
            )
            not in ("available", "unavailable")
        }
        if not pending_actions:
            profile = next(
                (
                    item
                    for item in self.cache.load(context.identity)
                    if item.origin == "automatic"
                ),
                None,
            )
            if profile is None:
                return None
            available = frozenset(
                key
                for key, status in existing.items()
                if status == "available"
            )
            unavailable = frozenset(
                key
                for key, status in existing.items()
                if status == "unavailable"
            )
            return ObservationResult(
                profile,
                frozenset(),
                available,
                unavailable,
                frozenset(),
            )
        statuses = {
            action: status
            for action, status in statuses.items()
            if action in pending_actions
        }
        matches = self.matcher.propose(
            image,
            dpi=context.dpi,
            caption_side=context.identity.caption_side,
        )
        for match in matches:
            if (
                match.action in pending_actions
                and match.action not in assignments
                and statuses.get(match.action) != "unavailable"
                and match.score >= AUTOMATIC_SCORE
            ):
                assignments[match.action] = match.rect
        try:
            return self.cache.save_observation(
                identity=context.identity,
                image=image,
                assignments=assignments,
                statuses=statuses,
                visuals=visuals,
            )
        except (OSError, ValueError):
            return None

    def snapshot(
        self,
        context: VisionContext,
        *,
        window_capture: bool = False,
    ) -> Optional[VisionSnapshot]:
        image = self.capture(context, window_capture=window_capture)
        if image is None:
            return None
        if not is_informative_crop(qimage_to_bgr(image)):
            return None
        proposals = {
            match.action: match.rect
            for match in self.proposals(image, context)
            if match.score >= AUTOMATIC_SCORE
        }
        completed, suggested = infer_missing_caption_rects(
            proposals,
            (image.width(), image.height()),
            caption_side=context.identity.caption_side,
            dpi=context.dpi,
        )
        return VisionSnapshot(context, image, completed, suggested)

    def probe_calibrated(
        self,
        context: VisionContext,
        point: tuple[int, int],
        *,
        final: bool,
    ) -> Optional[VisionMatch]:
        profiles = [
            profile
            for profile in self._load_profiles(context.identity)
            if profile.origin == "user"
        ]
        return self._probe_profiles(profiles, context, point, final=final)

    def probe_automatic(
        self,
        context: VisionContext,
        point: tuple[int, int],
        *,
        final: bool,
    ) -> Optional[VisionMatch]:
        automatic_profiles = [
            profile
            for profile in self._load_profiles(context.identity)
            if profile.origin == "automatic"
        ]
        cached = self._probe_profiles(
            automatic_profiles,
            context,
            point,
            final=final,
        )
        if cached is not None:
            return cached

        image = self.capture(context)
        if image is None:
            return None
        bgr = qimage_to_bgr(image)
        matches = self._run(
            self.matcher.propose,
            bgr,
            dpi=context.dpi,
            caption_side=context.identity.caption_side,
        ) or []
        crop_left, crop_top, _, _ = self.capture_rect(context)
        local_point = (point[0] - crop_left, point[1] - crop_top)
        match = self.matcher.choose_at_point(matches, local_point, final=final)
        if match is None:
            return None
        identity = (
            context.identity.fingerprint,
            match.action,
        )
        quantized = tuple(round(value / 3) for value in match.rect)
        with self._lock:
            previous, count = self._stable.get(identity, ((), 0))
            count = count + 1 if previous == quantized else 1
            self._stable[identity] = (quantized, count)
        if count >= AUTOMATIC_PERSISTENCE_COUNT:
            try:
                confident_assignments = {
                    candidate.action: candidate.rect
                    for candidate in matches
                    if candidate.score >= AUTOMATIC_SCORE
                }
                self.cache.save(
                    identity=context.identity,
                    origin="automatic",
                    image=bgr,
                    assignments=confident_assignments,
                )
                self._profiles.pop(context.identity.fingerprint, None)
            except OSError:
                pass
        profile_id = hashlib.sha256(
            (
                context.identity.fingerprint
                + match.action.name
                + repr(quantized)
            ).encode("utf-8")
        ).hexdigest()[:20]
        return VisionMatch(
            match.action,
            match.rect,
            match.score,
            profile_id,
            match.crop,
        )

    def _probe_profiles(
        self,
        profiles: list[VisionProfile],
        context: VisionContext,
        point: tuple[int, int],
        *,
        final: bool,
    ) -> Optional[VisionMatch]:
        if not profiles:
            return None
        image = self.capture(context)
        if image is None:
            return None
        bgr = qimage_to_bgr(image)
        crop_left, crop_top, _, _ = self.capture_rect(context)
        local_point = (point[0] - crop_left, point[1] - crop_top)
        threshold = FINAL_SCORE if final else AUTOMATIC_SCORE
        for profile in profiles:
            size = (image.width(), image.height())
            if profile.image_file and profile.image_rect:
                selected = None
                for button in profile.buttons:
                    rect = denormalized_rect(button.rect, size)
                    if (
                        rect[0] <= local_point[0] < rect[2]
                        and rect[1] <= local_point[1] < rect[3]
                    ):
                        selected = (button, rect)
                        break
                if selected is None:
                    continue
                group_rect = denormalized_rect(profile.image_rect, size)
                template = cv2.imread(
                    str(profile.directory / profile.image_file)
                )
                if template is None:
                    continue
                current = bgr[
                    group_rect[1] : group_rect[3],
                    group_rect[0] : group_rect[2],
                ]
                score = self._run(
                    self.matcher.compare_crop,
                    current,
                    template,
                )
                if score is not None and score >= threshold:
                    button, rect = selected
                    return VisionMatch(
                        button.action,
                        rect,
                        score,
                        profile.profile_id,
                        encode_png(current),
                    )
                continue
            for button in profile.buttons:
                rect = denormalized_rect(button.rect, size)
                if not (
                    rect[0] <= local_point[0] < rect[2]
                    and rect[1] <= local_point[1] < rect[3]
                ):
                    continue
                template = cv2.imread(
                    str(profile.directory / button.image_file)
                )
                if template is None:
                    continue
                current = bgr[rect[1] : rect[3], rect[0] : rect[2]]
                score = self._run(
                    self.matcher.compare_crop,
                    current,
                    template,
                )
                if score is not None and score >= threshold:
                    return VisionMatch(
                        button.action,
                        rect,
                        score,
                        profile.profile_id,
                        encode_png(current),
                    )
        return None

    def _load_profiles(
        self,
        identity: ApplicationIdentity,
    ) -> list[VisionProfile]:
        key = identity.fingerprint
        profiles = self._profiles.get(key)
        if profiles is None:
            profiles = self.cache.load(identity)
            self._profiles[key] = profiles
        return profiles

    def save_calibration(
        self,
        snapshot: VisionSnapshot,
        assignments: dict[CaptionAction, tuple[int, int, int, int]],
    ) -> VisionProfile:
        image = qimage_to_bgr(snapshot.image)
        merged_assignments = {}
        for existing in self.cache.load(snapshot.context.identity):
            if (
                existing.origin != "user"
                or existing.crop_size
                != (snapshot.image.width(), snapshot.image.height())
            ):
                continue
            merged_assignments.update(
                {
                    button.action: denormalized_rect(
                        button.rect,
                        existing.crop_size,
                    )
                    for button in existing.buttons
                }
            )
        merged_assignments.update(assignments)
        profile = self.cache.save(
            identity=snapshot.context.identity,
            origin="user",
            image=image,
            assignments=merged_assignments,
            statuses={
                action: "unavailable"
                for action in CaptionAction
                if action not in merged_assignments
            },
        )
        self._profiles.pop(snapshot.context.identity.fingerprint, None)
        return profile

    def list_tracked_applications(self) -> list[TrackedApplication]:
        return self.cache.list_tracked_applications()

    def list_tracked_assets(
        self,
        application: TrackedApplication,
    ) -> list[TrackedAsset]:
        return self.cache.list_tracked_assets(application)

    def update_tracked_rect(
        self,
        asset: TrackedAsset,
        rect: tuple[int, int, int, int],
    ) -> TrackedAsset:
        updated = self.cache.update_tracked_rect(asset, rect)
        self._profiles.pop(asset.identity.fingerprint, None)
        return updated

    def delete_tracked_application(
        self,
        application: TrackedApplication,
    ) -> None:
        self.cache.delete_tracked_application(application)
        executable_hash = application.executable_hash
        with self._lock:
            self._profiles = {
                key: profiles
                for key, profiles in self._profiles.items()
                if not profiles
                or profiles[0].identity.executable_hash != executable_hash
            }
            # Observation keys are irreversible identity fingerprints. Clear
            # them so the deleted executable is eligible for fresh learning.
            self._observed_assets.clear()
            self._pending_observations.clear()

    def clear_cache(self) -> None:
        self.cache.clear()
        self._profiles.clear()
        self._observed_assets.clear()
        self._pending_observations.clear()

    def export_all_data(
        self,
        destination_parent: Path,
        *,
        idle_timeout_s: float = 5.0,
    ) -> DataExportResult:
        deadline = time.monotonic() + idle_timeout_s
        while True:
            with self._lock:
                if not self._busy:
                    self._busy = True
                    break
            if time.monotonic() >= deadline:
                raise DataExportError(
                    "Caption data is still being updated. Try exporting "
                    "again in a moment."
                )
            time.sleep(0.01)
        try:
            return self.cache.export_all_data(destination_parent)
        finally:
            with self._lock:
                self._busy = False
