import re
from datetime import tzinfo

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QFontDatabase, QTextCursor, QTextFormat
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from ..parser import LogEntry, display_time, pretty_message

MATCH_BG = QColor(255, 215, 0, 95)
ACTIVE_MATCH_BG = QColor(255, 140, 0, 200)


class DetailPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_entry = False
        self._matches: list[tuple[int, int]] = []
        self._current_match = -1

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- Search bar (shown on Ctrl+F) ---
        self.search_bar = QWidget()
        self.search_bar.setObjectName("detailSearchBar")
        self.search_bar.setStyleSheet(
            "#detailSearchBar { border-bottom: 1px solid palette(mid); background: palette(window); }"
        )
        s_lay = QHBoxLayout(self.search_bar)
        s_lay.setContentsMargins(8, 4, 8, 4)
        s_lay.setSpacing(6)

        self.search = QLineEdit(
            placeholderText="Tìm trong chi tiết log… (Enter: kế tiếp, Shift+Enter: trước đó, Esc: đóng)",
            clearButtonEnabled=True,
        )
        self.count_label = QLabel("")
        self.count_label.setMinimumWidth(55)
        self.count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.count_label.setStyleSheet("color: gray;")

        self.prev_btn = QToolButton(text="▲", toolTip="Kết quả trước (Shift+Enter)")
        self.next_btn = QToolButton(text="▼", toolTip="Kết quả tiếp theo (Enter)")
        self.regex = QCheckBox("Regex")
        self.case = QCheckBox("Aa", toolTip="Phân biệt hoa/thường")
        self.close_btn = QToolButton(text="✕", toolTip="Đóng tìm kiếm (Esc)")

        s_lay.addWidget(self.search, 1)
        s_lay.addWidget(self.count_label)
        s_lay.addWidget(self.prev_btn)
        s_lay.addWidget(self.next_btn)
        s_lay.addWidget(self.regex)
        s_lay.addWidget(self.case)
        s_lay.addWidget(self.close_btn)
        self.search_bar.hide()

        # --- Text editor ---
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.editor.setPlaceholderText("Chọn 1 dòng để xem chi tiết (nhấn Ctrl+F để tìm trong chi tiết)")

        lay.addWidget(self.search_bar)
        lay.addWidget(self.editor, 1)

        # --- Connections ---
        self.search.textChanged.connect(self._run_search)
        self.regex.toggled.connect(self._run_search)
        self.case.toggled.connect(self._run_search)
        self.prev_btn.clicked.connect(lambda: self.find_next(-1))
        self.next_btn.clicked.connect(lambda: self.find_next(+1))
        self.close_btn.clicked.connect(self.close_search)

        self.search.installEventFilter(self)
        self.editor.installEventFilter(self)

    def has_entry(self) -> bool:
        return self._has_entry

    def show_entry(self, e: LogEntry | None, tz: tzinfo | None):
        if e is None:
            self._has_entry = False
            self.editor.clear()
            self._clear_highlights()
            return
        self._has_entry = True
        head = [
            f"Thời gian : {display_time(e, tz)}   (gốc: {e.ts_raw})",
            f"Level     : {e.level}",
            f"Thread    : {e.thread}",
            f"Logger    : {e.logger}",
        ]
        if e.trace_id:
            head.append(f"Trace ID  : {e.trace_id}")
        head.append(f"File      : {e.source}")
        raw_body = f"{e.message}\n{e.extra}" if e.extra else e.message
        body = pretty_message(raw_body)
        self.editor.setPlainText("\n".join(head) + "\n" + "─" * 80 + "\n" + body)
        if self.search_bar.isVisible() and self.search.text():
            self._run_search()

    def open_search(self):
        self.search_bar.show()
        selected = self.editor.textCursor().selectedText().strip()
        if selected and "\u2029" not in selected and "\n" not in selected:
            self.search.setText(selected)
        elif self.search.text():
            self._run_search()
        self.search.setFocus()
        self.search.selectAll()

    def close_search(self):
        self.search_bar.hide()
        self._clear_highlights()
        self.editor.setFocus()

    def find_next(self, step: int = 1):
        if not self._matches:
            return
        self._current_match = (self._current_match + step) % len(self._matches)
        self._apply_highlights(scroll=True)

    def _clear_highlights(self):
        self._matches = []
        self._current_match = -1
        self.editor.setExtraSelections([])
        self.count_label.setText("")
        self.search.setStyleSheet("")

    def _run_search(self):
        text = self.search.text()
        if not text or not self.search_bar.isVisible():
            self._clear_highlights()
            return

        flags = 0 if self.case.isChecked() else re.IGNORECASE
        try:
            pattern = re.compile(text if self.regex.isChecked() else re.escape(text), flags)
        except re.error:
            self.editor.setExtraSelections([])
            self._matches = []
            self._current_match = -1
            self.count_label.setText("Lỗi")
            self.search.setStyleSheet("QLineEdit { border: 1px solid #e5484d; }")
            return

        full_text = self.editor.toPlainText()
        self._matches = [(m.start(), m.end()) for m in pattern.finditer(full_text) if m.start() < m.end()]
        if not self._matches:
            self._current_match = -1
            self.editor.setExtraSelections([])
            self.count_label.setText("0/0")
            self.search.setStyleSheet("QLineEdit { border: 1px solid #e5484d; }")
            return

        self.search.setStyleSheet("")
        self._current_match = 0
        self._apply_highlights(scroll=True)

    def _apply_highlights(self, scroll: bool = False):
        doc = self.editor.document()
        selections: list[QTextEdit.ExtraSelection] = []
        for i, (start, end) in enumerate(self._matches):
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(doc)
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.KeepAnchor)
            sel.cursor = cur
            sel.format.setBackground(ACTIVE_MATCH_BG if i == self._current_match else MATCH_BG)
            if i == self._current_match:
                sel.format.setProperty(QTextFormat.FullWidthSelection, False)
            selections.append(sel)

        self.editor.setExtraSelections(selections)
        self.count_label.setText(f"{self._current_match + 1}/{len(self._matches)}")

        if scroll and 0 <= self._current_match < len(self._matches):
            start, _ = self._matches[self._current_match]
            cur = QTextCursor(doc)
            cur.setPosition(start)
            self.editor.setTextCursor(cur)
            self.editor.centerCursor()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key_Escape and self.search_bar.isVisible():
                self.close_search()
                return True
            if obj is self.search and key in (Qt.Key_Return, Qt.Key_Enter):
                self.find_next(-1 if (mods & Qt.ShiftModifier) else +1)
                return True
            if key == Qt.Key_F3 and self.search_bar.isVisible():
                self.find_next(-1 if (mods & Qt.ShiftModifier) else +1)
                return True
        return super().eventFilter(obj, event)

