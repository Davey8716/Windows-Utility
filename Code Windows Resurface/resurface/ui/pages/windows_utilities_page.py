from __future__ import annotations

import subprocess
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from resurface.features.system.maintenance_actions import MaintenanceActions
from resurface.features.system.windows_tool_catalog import WindowsToolCatalog, WindowsToolSpec
from resurface.ui import styles
from resurface.ui.tooltips import tooltip_text


class WindowsUtilitiesPage(QWidget):
    def __init__(
        self,
        catalog: WindowsToolCatalog,
        router_service,
        explorer_windows,
        windows,
        maintenance_actions: MaintenanceActions,
        register_tooltip: Callable,
        run_with_optional_minimize: Callable,
        set_output_context: Callable[[str], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.catalog = catalog
        self.router_service = router_service
        self.explorer_windows = explorer_windows
        self.windows = windows
        self.maintenance_actions = maintenance_actions
        self.register_tooltip = register_tooltip
        self.run_with_optional_minimize = run_with_optional_minimize
        self.set_output_context = set_output_context
        self.page_layout = QVBoxLayout(self)
        self.page_layout.setContentsMargins(0, 0, 0, 0)
        self._build()

    def _build(self):
        row = QWidget()
        row.setProperty("centeredControlGrid", True)
        row.setFixedWidth((styles.PAGE_CONTROL_WIDTH * 2) + styles.PAGE_CONTROL_GAP)
        row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(styles.PAGE_CONTROL_GAP)
        self.page_layout.addWidget(row, 0, Qt.AlignmentFlag.AlignHCenter)

        columns = []
        for _ in range(2):
            column = QWidget()
            column.setFixedWidth(styles.PAGE_CONTROL_WIDTH)
            column.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            layout = QVBoxLayout(column)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
            row_layout.addWidget(column)
            row_layout.setAlignment(column, Qt.AlignmentFlag.AlignTop)
            columns.append((column, layout))

        groups = self.catalog.groups()
        for index in (0, 1, 2):
            self._add_dropdown(columns[0][1], groups[index])
        for index in (3, 4, 5):
            self._add_dropdown(columns[1][1], groups[index])

        widths = []
        for column, _layout in columns:
            width = max(combo.width() for combo in column.findChildren(QComboBox))
            column.setFixedWidth(width)
            widths.append(width)
        row.setFixedWidth(widths[0] + styles.PAGE_CONTROL_GAP + widths[1])

    def _add_dropdown(self, layout, group):
        placeholder = f" {group.label} "
        combo = QComboBox()
        combo.addItem(placeholder)
        tools_by_label = {tool.label: tool for tool in group.tools}
        combo.addItems(sorted(tools_by_label))
        combo.setCurrentText(placeholder)
        combo.view().setRowHidden(0, True)
        combo.setProperty("styleFontSize", 15)
        combo.setStyleSheet(styles.organizing_combo_style(15))
        styles.fit_page_combo_width(combo, placeholder=placeholder, font_size=15)
        self.register_tooltip(combo, tooltip_text(group.tooltip_key))

        def selected(text: str):
            if text == placeholder:
                return
            tool = tools_by_label.get(text)
            if tool is not None:
                self.set_output_context(text)
                action = lambda: self.launch(tool)
                if tool.minimize:
                    self.run_with_optional_minimize(action)
                else:
                    action()
            combo.setCurrentText(placeholder)

        combo.currentTextChanged.connect(selected)
        layout.addWidget(combo)

    def launch(self, tool: WindowsToolSpec):
        if tool.launch_kind == "maintenance":
            self.maintenance_actions.show_ip_config()
            return
        if tool.launch_kind == "router":
            self.router_service.open_router_page()
            return
        if tool.launch_kind == "folder":
            self.explorer_windows.open_or_focus_folder(tool.target)
            return
        if tool.launch_kind == "explorer_title":
            self.explorer_windows.open_or_focus_title(
                tool.title_candidates[0],
                lambda: self.maintenance_actions.shell_execute(tool.target, tool.parameters),
            )
            return

        def raw_launch():
            if tool.launch_kind == "shell_open":
                self.maintenance_actions.shell_open(tool.target)
            elif tool.launch_kind == "shell_execute":
                self.maintenance_actions.shell_execute(tool.target, tool.parameters)
            elif tool.launch_kind == "shell_execute_elevated":
                self.maintenance_actions.shell_execute_elevated(tool.target, tool.parameters)
            elif tool.launch_kind == "popen":
                subprocess.Popen([tool.target])
            else:
                raise ValueError(f"Unsupported Windows tool launch kind: {tool.launch_kind}")

        if tool.title_candidates:
            self.windows.open_or_focus_titles(tool.title_candidates, raw_launch)
        else:
            raw_launch()
