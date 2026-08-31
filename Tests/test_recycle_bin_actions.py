from PySide6.QtWidgets import QMessageBox

from resurface.ui.controllers import recycle_bin_actions
from resurface.ui.controllers.recycle_bin_actions import RecycleBinActionsController


class App:
    def __init__(self, state=None, answer=QMessageBox.StandardButton.Yes):
        self.state = state or {}
        self.answer = answer
        self.messages = []
        self.modals = []

    @staticmethod
    def _message_box_icon(name): return name
    @staticmethod
    def _message_box_button(name): return getattr(QMessageBox.StandardButton, name)

    def _show_modal_message(self, *args):
        self.modals.append(args)
        return self.answer

    def _show_timed_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class Service:
    def __init__(self, *, emptied=True, deleted=0):
        self.emptied = emptied
        self.deleted = deleted
        self.closed = 0

    def open(self): return True
    def empty(self): return self.emptied
    def cleanup_items_older_than(self, _days): return self.deleted
    def close(self):
        self.closed += 1
        return True


def immediate(action): action()


def test_empty_cancel_does_not_mutate_service():
    app, service = App(answer=QMessageBox.StandardButton.Cancel), Service()
    RecycleBinActionsController(app, service, immediate).empty_recycle_bin()
    assert service.closed == 0 and app.messages == []


def test_empty_always_closes_after_attempt():
    app, service = App(), Service(emptied=False)
    RecycleBinActionsController(app, service, immediate).empty_recycle_bin()
    assert service.closed == 1
    assert app.messages[0][0][2] == "Could not empty Recycle Bin."


def test_manual_cleanup_closes_and_reports_no_matches():
    app = App({"recycle_bin_age_rule_days": 30})
    service = Service(deleted=0)
    RecycleBinActionsController(app, service, immediate).run_cleanup_now()
    assert service.closed == 1
    assert "No Recycle Bin items older than 30 days" in app.messages[0][0][2]


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
    assert app.state["recycle_bin_last_auto_clean_popup_days"] == 14
    assert len(saved) == 1
