from __future__ import annotations

from resurface.core.state_manager import save_state
from resurface.ui import styles


class RecycleBinActionsController:
    def __init__(self, app, service, run_with_optional_minimize):
        self.app = app
        self.service = service
        self.run_with_optional_minimize = run_with_optional_minimize

    def open_recycle_bin(self) -> None:
        def action():
            if not self.service.open():
                self.app._show_timed_message(
                    self.app._message_box_icon("Warning"), "Recycle Bin",
                    "Could not open Recycle Bin.",
                )
        self.run_with_optional_minimize(action)

    def empty_recycle_bin(self) -> None:
        if not self.service.has_items():
            self._refresh_empty_action()
            return
        answer = self.app._show_modal_message(
            self.app._message_box_icon("NoIcon"), "Empty Recycle Bin",
            "Permanently delete all items currently in Recycle Bin?",
            self.app._message_box_button("Yes") | self.app._message_box_button("Cancel"),
            self.app._message_box_button("Cancel"),
            popup_corner_radius=6,
        )
        if answer != self.app._message_box_button("Yes"):
            return

        def action():
            try:
                succeeded = self.service.empty()
                if succeeded:
                    self.app._show_timed_message(
                        self.app._message_box_icon("Information"), "Recycle Bin",
                        "Recycle Bin emptied.", show_close_now_button=True,
                        popup_corner_radius=6,
                    )
            finally:
                self.service.close()
                self._refresh_empty_action()
        self.run_with_optional_minimize(action)

    def _refresh_empty_action(self) -> None:
        quick_actions = getattr(self.app, "quick_actions", None)
        if quick_actions is not None:
            quick_actions.action_changed.emit("recycle.empty")
        recycle_page = getattr(getattr(self.app, "pages", None), "recycle_bin_page", None)
        if recycle_page is not None:
            recycle_page.refresh_empty_action_availability()

    def run_auto_cleanup(self) -> None:
        if (
            self.app.state.get("recycle_bin_auto_clean_enabled", False)
            and self.service.has_items()
        ):
            self._run_age_cleanup(automatic=True)

    def run_cleanup_now(self) -> None:
        self._run_age_cleanup(automatic=False)

    def _save_state_safely(self) -> None:
        try:
            save_state(self.app.state)
        except Exception as exc:
            print(f"[STATE] Save failed: {exc}")

    def _run_age_cleanup(self, *, automatic: bool) -> None:
        days = int(self.app.state.get("recycle_bin_age_rule_days", 30))
        show_auto_popup = not automatic or self.app.state.get("recycle_bin_last_auto_clean_popup_days") != days
        if days <= 0:
            if not automatic:
                self.app._show_timed_message(
                    self.app._message_box_icon("Warning"), "Recycle Bin Cleanup",
                    "Choose a valid age rule before running cleanup.",
                )
            return
        if not automatic:
            answer = self.app._show_modal_message(
                self.app._message_box_icon("NoIcon"), "Recycle Bin Cleanup",
                f"Permanently delete Recycle Bin items older than {days} days?",
                self.app._message_box_button("Yes") | self.app._message_box_button("Cancel"),
                self.app._message_box_button("Cancel"),
            )
            if answer != self.app._message_box_button("Yes"):
                return

        def action():
            try:
                deleted = self.service.cleanup_items_older_than(days)
                if deleted > 0:
                    if show_auto_popup:
                        title = "Recycle Bin Auto-Clean" if automatic else "Recycle Bin Cleanup"
                        self.app._show_timed_message(
                            self.app._message_box_icon("Information"), title,
                            f"Deleted {deleted} Recycle Bin item(s) older than {days} days.",
                            show_close_now_button=True,
                            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
                        )
                elif automatic:
                    if show_auto_popup:
                        self.app._show_timed_message(
                            self.app._message_box_icon("Information"), "Recycle Bin Auto-Clean",
                            f"No Recycle Bin items older than {days} days were found.",
                            show_close_now_button=True,
                            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
                        )
                else:
                    self.app._show_timed_message(
                        self.app._message_box_icon("Information"), "Recycle Bin Cleanup",
                        f"No Recycle Bin items older than {days} days were found.",
                        show_close_now_button=True,
                    )
                if automatic and show_auto_popup:
                    self.app.state["recycle_bin_last_auto_clean_popup_days"] = days
                    self._save_state_safely()
            finally:
                if not automatic:
                    self.service.close()
        if automatic:
            action()
        else:
            self.run_with_optional_minimize(action)
