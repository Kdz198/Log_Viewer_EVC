import re
from dataclasses import dataclass

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QWidget

from ..parser import LEVELS


@dataclass
class FilterState:
    levels: set[str]
    pattern: re.Pattern | None


class FilterBar(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)

        self.level_boxes: dict[str, QCheckBox] = {}
        for lv in LEVELS:
            cb = QCheckBox(lv)
            cb.setChecked(True)
            cb.toggled.connect(self.changed)
            self.level_boxes[lv] = cb
            lay.addWidget(cb)

        self.search = QLineEdit(placeholderText="Tìm kiếm: nội dung, trace ID, mã KH… (Ctrl+F)",
                                clearButtonEnabled=True)
        self.regex = QCheckBox("Regex")
        self.case = QCheckBox("Aa")
        self.case.setToolTip("Phân biệt hoa/thường")

        lay.addSpacing(8)
        lay.addWidget(self.search, 1)
        lay.addWidget(self.regex)
        lay.addWidget(self.case)

        # debounce typing so a full day isn't re-filtered on every keystroke
        self._timer = QTimer(self, singleShot=True, interval=300)
        self._timer.timeout.connect(self.changed)
        self.search.textChanged.connect(self._timer.start)
        for cb in (self.regex, self.case):
            cb.toggled.connect(self.changed)

    def set_counts(self, counts: dict[str, int]):
        for lv, cb in self.level_boxes.items():
            cb.setText(f"{lv} ({counts.get(lv, 0):,})")

    def set_search(self, text: str):
        self.search.setText(text)
        self._timer.stop()
        self.changed.emit()

    def state(self) -> FilterState | None:
        """None when the regex is invalid."""
        text = self.search.text()
        pattern = None
        self.search.setStyleSheet("")
        if text:
            flags = 0 if self.case.isChecked() else re.IGNORECASE
            try:
                pattern = re.compile(text if self.regex.isChecked() else re.escape(text), flags)
            except re.error:
                self.search.setStyleSheet("QLineEdit { border: 1px solid #e5484d; }")
                return None
        return FilterState(levels={lv for lv, cb in self.level_boxes.items() if cb.isChecked()},
                           pattern=pattern)
