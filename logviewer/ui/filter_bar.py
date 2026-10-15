"""Modern filter bar with interactive level pill buttons, live counts,
instant solo filter on right-click, and sleek search chips.
"""
import re
from dataclasses import dataclass

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QPushButton, QSizePolicy, QToolButton, QWidget)

from ..parser import LEVELS
from .theme import Theme, is_dark_mode


@dataclass
class FilterState:
    levels: set[str]
    pattern: re.Pattern | None


class LevelPillButton(QPushButton):
    """Modern checkable pill button displaying log level and live count badge."""

    def __init__(self, level: str, parent=None):
        super().__init__(parent)
        self.level = level
        self.count = 0
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.toggled.connect(self._update_appearance)
        self._update_appearance()

    def set_count(self, count: int):
        self.count = count
        self._update_appearance()

    def _update_appearance(self):
        dark = is_dark_mode()
        active = self.isChecked()
        count_str = f"{self.count:,}" if self.count else "0"
        self.setText(f"● {self.level}  {count_str}")
        self.setToolTip(
            f"Bật/tắt log level {self.level} ({count_str} entry)\n"
            f"Click phải: chỉ hiển thị riêng {self.level} (Solo)"
        )

        # Style tokens depending on level
        if self.level == "ERROR":
            accent = Theme.ERROR
            active_bg = "rgba(239, 68, 68, 0.22)" if dark else "#fee2e2"
            active_text = "#fca5a5" if dark else "#991b1b"
        elif self.level == "WARN":
            accent = Theme.WARN
            active_bg = "rgba(245, 158, 11, 0.22)" if dark else "#fef3c7"
            active_text = "#fcd34d" if dark else "#92400e"
        elif self.level == "DEBUG":
            accent = Theme.DEBUG
            active_bg = "rgba(100, 116, 139, 0.22)" if dark else "#f1f5f9"
            active_text = "#cbd5e1" if dark else "#475569"
        else:  # INFO
            accent = Theme.INFO
            active_bg = "rgba(59, 130, 246, 0.22)" if dark else "#dbeafe"
            active_text = "#93c5fd" if dark else "#1e40af"

        if active:
            self.setStyleSheet(
                f"LevelPillButton {{"
                f"  background-color: {active_bg};"
                f"  color: {active_text};"
                f"  border: 1px solid {accent};"
                f"  border-radius: 13px;"
                f"  padding: 3px 12px;"
                f"  font-weight: 600;"
                f"  font-size: 11px;"
                f"}}"
                f"LevelPillButton:hover {{"
                f"  background-color: {accent};"
                f"  color: #ffffff;"
                f"}}"
            )
        else:
            dim_text = "#6c7086" if dark else "#94a3b8"
            dim_border = "#313244" if dark else "#e2e8f0"
            self.setStyleSheet(
                f"LevelPillButton {{"
                f"  background-color: transparent;"
                f"  color: {dim_text};"
                f"  border: 1px solid {dim_border};"
                f"  border-radius: 13px;"
                f"  padding: 3px 12px;"
                f"  font-weight: 500;"
                f"  font-size: 11px;"
                f"}}"
                f"LevelPillButton:hover {{"
                f"  border-color: {accent};"
                f"  color: {accent};"
                f"}}"
            )

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        solo_act = menu.addAction(f"Chỉ hiển thị {self.level} (Solo)")
        all_act = menu.addAction("Hiển thị tất cả Level")
        none_act = menu.addAction("Tắt tất cả Level")
        action = menu.exec(self.mapToGlobal(pos))
        if action == solo_act:
            p = self.parentWidget()
            if hasattr(p, "solo_level"):
                p.solo_level(self.level)
        elif action == all_act:
            p = self.parentWidget()
            if hasattr(p, "set_all_levels"):
                p.set_all_levels(True)
        elif action == none_act:
            p = self.parentWidget()
            if hasattr(p, "set_all_levels"):
                p.set_all_levels(False)


class FilterBar(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("filterBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        # Level pill buttons
        self.level_boxes: dict[str, LevelPillButton] = {}
        for lv in LEVELS:
            btn = LevelPillButton(lv, self)
            btn.toggled.connect(self.changed)
            self.level_boxes[lv] = btn
            lay.addWidget(btn)

        lay.addSpacing(6)

        # Global search input with modern styling
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Tìm nhanh: message, trace ID, endpoint, mã đơn… (Ctrl+Shift+F)")
        self.search.setClearButtonEnabled(True)
        self._apply_search_style()
        lay.addWidget(self.search, 1)

        # Regex and Case toggle chips
        self.regex = QPushButton(".* Regex")
        self.regex.setCheckable(True)
        self.regex.setCursor(Qt.PointingHandCursor)
        self.regex.setToolTip("Bật chế độ tìm kiếm theo biểu thức chính quy (Regular Expression)")

        self.case = QPushButton("Aa Case")
        self.case.setCheckable(True)
        self.case.setCursor(Qt.PointingHandCursor)
        self.case.setToolTip("Phân biệt chữ hoa / chữ thường")

        self._style_chip(self.regex)
        self._style_chip(self.case)

        self.regex.toggled.connect(lambda: (self._style_chip(self.regex), self.changed.emit()))
        self.case.toggled.connect(lambda: (self._style_chip(self.case), self.changed.emit()))

        lay.addWidget(self.regex)
        lay.addWidget(self.case)

        # Debounce typing so large logs don't re-filter on every keystroke
        self._timer = QTimer(self, singleShot=True, interval=280)
        self._timer.timeout.connect(self.changed)
        self.search.textChanged.connect(self._timer.start)

    def _apply_search_style(self, error: bool = False):
        dark = is_dark_mode()
        bg = "#1e1e2e" if dark else "#ffffff"
        border = "#ef4444" if error else ("#313244" if dark else "#cbd5e1")
        text = "#cdd6f4" if dark else "#0f172a"
        focus_border = "#3b82f6"

        self.search.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {bg};"
            f"  color: {text};"
            f"  border: 1px solid {border};"
            f"  border-radius: 8px;"
            f"  padding: 5px 12px;"
            f"  font-size: 12px;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border: 1px solid {focus_border};"
            f"}}"
        )

    def _style_chip(self, btn: QPushButton):
        dark = is_dark_mode()
        active = btn.isChecked()
        if active:
            btn.setStyleSheet(
                "QPushButton {"
                "  background-color: rgba(59, 130, 246, 0.22);"
                "  color: #60a5fa;"
                "  border: 1px solid #3b82f6;"
                "  border-radius: 6px;"
                "  padding: 4px 10px;"
                "  font-weight: 600;"
                "  font-size: 11px;"
                "}"
            )
        else:
            border = "#313244" if dark else "#e2e8f0"
            color = "#a6adc8" if dark else "#64748b"
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: transparent;"
                f"  color: {color};"
                f"  border: 1px solid {border};"
                f"  border-radius: 6px;"
                f"  padding: 4px 10px;"
                f"  font-size: 11px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  border-color: #3b82f6;"
                f"  color: #3b82f6;"
                f"}}"
            )

    def solo_level(self, solo_lv: str):
        for lv, btn in self.level_boxes.items():
            btn.blockSignals(True)
            btn.setChecked(lv == solo_lv)
            btn.blockSignals(False)
            btn._update_appearance()
        self.changed.emit()

    def set_all_levels(self, active: bool):
        for btn in self.level_boxes.values():
            btn.blockSignals(True)
            btn.setChecked(active)
            btn.blockSignals(False)
            btn._update_appearance()
        self.changed.emit()

    def set_counts(self, counts: dict[str, int]):
        for lv, btn in self.level_boxes.items():
            btn.set_count(counts.get(lv, 0))

    def set_search(self, text: str):
        self.search.setText(text)
        self._timer.stop()
        self.changed.emit()

    def state(self) -> FilterState | None:
        """None when the regex is invalid."""
        text = self.search.text()
        pattern = None
        if text:
            flags = 0 if self.case.isChecked() else re.IGNORECASE
            try:
                pattern = re.compile(text if self.regex.isChecked() else re.escape(text), flags)
                self._apply_search_style(error=False)
            except re.error:
                self._apply_search_style(error=True)
                return None
        else:
            self._apply_search_style(error=False)

        return FilterState(
            levels={lv for lv, btn in self.level_boxes.items() if btn.isChecked()},
            pattern=pattern,
        )
