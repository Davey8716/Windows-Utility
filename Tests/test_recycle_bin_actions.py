from PySide6.QtWidgets import QMessageBox

from resurface.ui import styles
from resurface.ui.controllers import recycle_bin_actions
from resurface.ui.controllers.recycle_bin_actions import RecycleBinActionsController


class App:
    def __init__(self, state=None, answer=QMessageBox.StandardButton.Yes):
        self.state = state or {}
        self.answer = answer
        self.messages = []
        self.modals = []
        self.modal_options = []

    @staticmethod
    def _message_box_icon(name): return name
    @staticmethod
    def _message_box_button(name): return getattr(QMessageBox.StandardButton, name)

    def _show_modal_message(self, *args, **kwargs):
        self.modals.append(args)
        self.modal_options.append(kwargs)
        return self.answer

    def _show_timed_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class Service:
    def __init__(self, *, has_items=True, emptied=True, deleted=0):
        self.has_items_result = has_items
        self.emptied = emptied
        self.deleted = deleted
        self.closed = 0
        self.cleanup_calls = 0

    def open(self): return True
    def has_items(self): return self.has_items_result
    def empty(self): return self.emptied
    def cleanup_items_older_than(self, _days):
        self.cleanup_calls += 1
        return self.deleted
    def close(self):
        self.closed += 1
        return True


def immediate(action): action()


def test_empty_cancel_does_not_mutate_service():
    app, service = App(answer=QMessageBox.StandardButton.Cancel), Service()
    RecycleBinActionsController(app, service, immediate).empty_recycle_bin()
    assert service.closed == 0 and app.messages == []
    assert app.modal_options == [{"popup_corner_radius": 6}]


def test_empty_always_closes_after_attempt_without_a_failure_popup():
    app, service = App(), Service(emptied=False)
    RecycleBinActionsController(app, service, immediate).empty_recycle_bin()
    assert service.closed == 1
    assert app.messages == []


def test_empty_skips_confirmation_when_the_recycle_bin_is_empty():
    app, service = App(), Service(has_items=False)
    RecycleBinActionsController(app, service, immediate).empty_recycle_bin()
    assert app.modals == []
    assert service.closed == 0


def test_manual_cleanup_closes_and_reports_no_matches():
    app = App({"recycle_bin_age_rule_days": 30})
    service = Service(deleted=0)
    RecycleBinActionsController(app, service, immediate).run_cleanup_now()
    assert service.closed == 1
    assert "No Recycle Bin items older than 30 days" in app.messages[0][0][2]
    assert app.modal_options == [{"popup_corner_radius": styles.BUTTON_CORNER_RADIUS}]
    assert app.messages[0][1]["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS


def test_auto_cleanup_persists_popup_day_once(monkeypatch):
    app = App({
        "recycle_bin_auto_clean_enabled": True,
        "recycle_bin_age_rule_days": 14,
        "recycle_bin_last_auto_clean_popup_days": None,
    })
    service = Service(deleted=2)
    saved = []
    monkeypatch.setattr(recycle_bin_actions, "save_state", lambda state: saved.append(dict(state)))
    controller = RecycleBinActionsController(app, service, immediate)
    controller.run_auto_cleanup()
    controller.run_auto_cleanup()
    assert len(app.messages) == 1
    assert app.messages[0][1]["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
    assert app.state["recycle_bin_last_auto_clean_popup_days"] == 14
    assert len(saved) == 1


def test_auto_cleanup_skips_empty_recycle_bin(monkeypatch):
    app = App({
        "recycle_bin_auto_clean_enabled": True,
        "recycle_bin_age_rule_days": 14,
        "recycle_bin_last_auto_clean_popup_days": None,
    })
    service = Service(has_items=False)
    saved = []
    monkeypatch.setattr(recycle_bin_actions, "save_state", lambda state: saved.append(dict(state)))

    RecycleBinActionsController(app, service, immediate).run_auto_cleanup()

    assert service.cleanup_calls == 0
    assert app.messages == []
    assert app.state["recycle_bin_last_auto_clean_popup_days"] is None
    assert saved == []


def test_auto_cleanup_no_matches_uses_rounded_popup(monkeypatch):
    app = App({
        "recycle_bin_auto_clean_enabled": True,
        "recycle_bin_age_rule_days": 14,
        "recycle_bin_last_auto_clean_popup_days": None,
    })
    service = Service(deleted=0)
    monkeypatch.setattr(recycle_bin_actions, "save_state", lambda _state: None)

    RecycleBinActionsController(app, service, immediate).run_auto_cleanup()

    assert len(app.messages) == 1
    assert app.messages[0][1]["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
