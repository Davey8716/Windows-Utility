from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QScrollArea, QToolButton, QWidget

from resurface.ui import styles
from resurface.ui.application_window import UtilityControlApp
from resurface.ui.navigation_shell import NavigationShell
from resurface.ui.tooltips import format_tooltip_text


def build_shell():
    QApplication.instance() or QApplication([])
    return NavigationShell(
        app_version="test",
        sidebar_width=220,
        page_title_top_inset=43,
    )


def test_shell_owns_ordered_scrollable_page_hosts():
    shell = build_shell()
    try:
        expected_ids = [definition.page_id for definition in shell.PAGE_DEFINITIONS]
        assert [entry["id"] for entry in shell.page_registry] == expected_ids
        assert list(shell.page_by_id) == expected_ids
        assert shell.navigation_list.count() == len(expected_ids)
        assert shell.page_stack.count() == len(expected_ids)
        assert "hover_window_controls" not in expected_ids
        assert shell.navigation_list.item(0).toolTip() == format_tooltip_text(
            shell.page_registry[0]["description"]
        )
        assert all(
            isinstance(scroll, QScrollArea)
            for scroll in shell.page_scroll_areas.values()
        )
    finally:
        shell.deleteLater()


def test_navigation_emits_resolved_page_for_changes_fallback_and_same_page():
    shell = build_shell()
    changes = []
    shell.page_changed.connect(changes.append)
    try:
        assert shell.navigate_to("screen_mover") == "screen_mover"
        assert shell.navigate_to("missing") == "overview"
        assert shell.navigate_to("overview") == "overview"
        assert changes == ["screen_mover", "overview", "overview"]

        changes.clear()
        assert shell.navigate_to("maintenance", emit_signal=False) == "maintenance"
        assert changes == []
        assert shell.page_stack.currentWidget() is shell.page_by_id["maintenance"]
    finally:
        shell.deleteLater()


def test_content_must_be_constructed_with_its_final_parent():
    shell = build_shell()
    try:
        content = QWidget(shell.content_parent("overview"))
        shell.mount_content("overview", content)
        assert content.parentWidget() is shell.content_parent("overview")

        wrong_parent = QWidget()
        misplaced = QWidget(wrong_parent)
        try:
            shell.mount_content("overview", misplaced)
        except ValueError as exc:
            assert "final parent" in str(exc)
        else:
            raise AssertionError("mount_content accepted staged content")
        finally:
            wrong_parent.deleteLater()
    finally:
        shell.deleteLater()


def test_apply_theme_refreshes_navigation_presentation():
    shell = build_shell()
    try:
        shell.apply_theme()
        assert shell.navigation_list.styleSheet() == styles.navigation_list_style()
        assert (
            shell.about_licensing_button.styleSheet()
            == styles.sidebar_about_licensing_button_style()
        )
        assert shell.footer_divider.styleSheet() == styles.sidebar_footer_divider_style()
        assert not shell.about_licensing_button.icon().isNull()
        assert shell.version_label.styleSheet() == styles.sidebar_version_label_style()
        assert all(
            not shell.navigation_list.item(row).icon().isNull()
            for row in range(shell.navigation_list.count())
        )
    finally:
        shell.deleteLater()


def test_about_licensing_footer_control_emits_without_changing_navigation():
    shell = build_shell()
    requests = []
    shell.about_licensing_requested.connect(lambda: requests.append(True))
    try:
        shell.navigate_to("maintenance", emit_signal=False)
        shell.about_licensing_button.click()

        assert requests == [True]
        assert shell.page_stack.currentWidget() is shell.page_by_id["maintenance"]
        assert shell.about_licensing_button.accessibleName() == "About and licensing"
        assert shell.about_licensing_button.sizePolicy().horizontalPolicy() == (
            shell.about_licensing_button.sizePolicy().Policy.Expanding
        )
    finally:
        shell.deleteLater()


def test_about_licensing_footer_is_divided_and_uses_a_shield_icon():
    shell = build_shell()
    try:
        layout = shell.navigation_sidebar.layout()
        divider_index = layout.indexOf(shell.footer_divider)
        button_index = layout.indexOf(shell.about_licensing_button)
        version_index = layout.indexOf(shell.version_label)

        assert isinstance(shell.footer_divider, QFrame)
        assert shell.footer_divider.frameShape() == QFrame.Shape.HLine
        assert divider_index < button_index < version_index
        assert shell.about_licensing_button.toolButtonStyle() == (
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
    finally:
        shell.deleteLater()


def test_about_licensing_dialog_uses_current_version_and_close_button():
    class Window:
        APP_VERSION = "2.4.6"

        def _message_box_button(self, name):
            return f"button:{name}"

        def _message_box_icon(self, name):
            return f"icon:{name}"

        def _show_modal_message(self, *args, **kwargs):
            self.message = (args, kwargs)

    window = Window()
    UtilityControlApp._show_about_licensing(window)

    args, kwargs = window.message
    assert args == (
        "icon:NoIcon",
        "About & Licensing",
        "Windows Resurface\nVersion 2.4.6\n\n"
        "Licensing information will be added in a future release.",
        "button:Close",
        "button:Close",
    )
    assert kwargs == {
        "center_text_block": True,
        "fixed_popup_width": 410,
        "popup_corner_radius": 6,
        "text_color": styles.TEXT_LIGHT,
    }


def test_organising_utilities_title_has_a_theme_aware_help_button():
    shell = build_shell()
    try:
        button = shell.page_title_help_button("organising_utilities")

        assert isinstance(button, QToolButton)
        assert button.objectName() == "OrganisingUtilitiesHelpButton"
        assert button.text() == "?"
        assert button.size().width() == button.size().height() == 28
        assert button.accessibleName() == "Organising Utilities help"
        assert button.toolTip() == format_tooltip_text(
            "About Organising Utilities backups"
        )
        assert button.parentWidget().findChild(
            QWidget, "PageTitle"
        ) is not None

        styles.set_theme(False)
        shell.apply_theme()
        assert "#6a7480" in button.styleSheet()
    finally:
        styles.set_theme(True)
        shell.deleteLater()
