from PySide6.QtWidgets import QApplication, QScrollArea, QToolButton, QWidget

from resurface.ui import styles
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
        assert shell.version_label.styleSheet() == styles.sidebar_version_label_style()
        assert all(
            not shell.navigation_list.item(row).icon().isNull()
            for row in range(shell.navigation_list.count())
        )
    finally:
        shell.deleteLater()


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
        assert "#eef2f6" in button.styleSheet()
    finally:
        styles.set_theme(True)
        shell.deleteLater()
