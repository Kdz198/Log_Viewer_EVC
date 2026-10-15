"""Log entry detail panel with DevTools-style JSON and log syntax highlighting,
modern metadata header card with 1-click Trace ID copy/filter, and quick actions.
"""
import json
import re
from datetime import tzinfo

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QFontDatabase, QIcon, QKeySequence,
                           QPainter, QPalette, QSyntaxHighlighter, QTextCharFormat,
                           QTextCursor, QTextFormat)
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSizePolicy,
                               QTextEdit, QToolButton, QVBoxLayout, QWidget)

from ..parser import LogEntry, display_time, pretty_message
from .theme import Theme, get_syntax_colors, is_dark_mode

MATCH_BG = QColor(255, 215, 0, 95)
ACTIVE_MATCH_BG = QColor(255, 140, 0, 200)

HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")


class JsonLogSyntaxHighlighter(QSyntaxHighlighter):
    """High-performance syntax highlighter for JSON payloads, HTTP headers, trace IDs,
    endpoints, and Java stack traces.
    """

    def __init__(self, document, dark: bool | None = None):
        super().__init__(document)
        self.dark = is_dark_mode() if dark is None else dark
        self._init_formats()

    def update_theme(self, dark: bool):
        self.dark = dark
        self._init_formats()
        self.rehighlight()

    def _init_formats(self):
        colors = get_syntax_colors(self.dark)

        # JSON Key
        self.fmt_key = QTextCharFormat()
        self.fmt_key.setForeground(colors["key"])
        self.fmt_key.setFontWeight(QFont.DemiBold)

        # JSON String value
        self.fmt_str = QTextCharFormat()
        self.fmt_str.setForeground(colors["string"])

        # JSON Number
        self.fmt_num = QTextCharFormat()
        self.fmt_num.setForeground(colors["number"])

        # JSON Boolean & Null
        self.fmt_bool = QTextCharFormat()
        self.fmt_bool.setForeground(colors["boolean"])
        self.fmt_bool.setFontWeight(QFont.Bold)

        self.fmt_null = QTextCharFormat()
        self.fmt_null.setForeground(colors["null"])
        self.fmt_null.setFontWeight(QFont.Bold)

        # HTTP Methods
        self.fmt_get = QTextCharFormat()
        self.fmt_get.setForeground(colors["get"])
        self.fmt_get.setFontWeight(QFont.Bold)

        self.fmt_post = QTextCharFormat()
        self.fmt_post.setForeground(colors["post"])
        self.fmt_post.setFontWeight(QFont.Bold)

        self.fmt_put = QTextCharFormat()
        self.fmt_put.setForeground(colors["put"])
        self.fmt_put.setFontWeight(QFont.Bold)

        self.fmt_delete = QTextCharFormat()
        self.fmt_delete.setForeground(colors["delete"])
        self.fmt_delete.setFontWeight(QFont.Bold)

        # Section labels (Headers:, Payload:, Response:, Result:)
        self.fmt_section = QTextCharFormat()
        self.fmt_section.setForeground(colors["section"])
        self.fmt_section.setFontWeight(QFont.Bold)

        # Trace ID
        self.fmt_trace = QTextCharFormat()
        self.fmt_trace.setForeground(colors["trace_id"])
        self.fmt_trace.setFontWeight(QFont.DemiBold)

        # URL / Endpoint
        self.fmt_url = QTextCharFormat()
        self.fmt_url.setForeground(colors["url"])

        # Stack trace line
        self.fmt_stack = QTextCharFormat()
        self.fmt_stack.setForeground(colors["stacktrace"])

        # Bracket / Punctuation
        self.fmt_punct = QTextCharFormat()
        self.fmt_punct.setForeground(colors["punctuation"])

        # Regex patterns
        self.re_str = re.compile(r'"(?:\\.|[^"\\])*"')
        self.re_key = re.compile(r'("(?:\\.|[^"\\])*")\s*:')
        self.re_num = re.compile(r'(?<=[:\s,\[])(-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)(?=[\s,\]\}]|$)')
        self.re_bool = re.compile(r'\b(true|false)\b')
        self.re_null = re.compile(r'\b(null)\b')
        self.re_section = re.compile(r'^(Headers|Payload|Result|Response|Params|Body|Request):\s*')
        self.re_trace = re.compile(r'\[([A-Za-z0-9_-]{12,})\]')
        self.re_req_res = re.compile(r'▶️\s*\[(REQUEST|RESPONSE)\]')
        self.re_endpoint = re.compile(r'(?:GET|POST|PUT|DELETE|PATCH)\s+([/\w\-.~%!$&\'()*+,;=:@]+)')
        self.re_stack_at = re.compile(r'^\s*at\s+[\w$./]+(?:\(.*?\))?')
        self.re_stack_cause = re.compile(r'^(?:Caused by:|[a-zA-Z0-9_$.]+(?:Exception|Error):.*)$')
        self.re_brackets = re.compile(r'[{}\[\]]')

    def highlightBlock(self, text: str):
        if not text:
            return

        # Stack trace line
        if self.re_stack_at.match(text) or self.re_stack_cause.match(text):
            self.setFormat(0, len(text), self.fmt_stack)
            return

        # Section headers (e.g. Headers:, Payload:)
        if m := self.re_section.match(text):
            self.setFormat(m.start(1), m.end(1) - m.start(1) + 1, self.fmt_section)

        # Request / Response marker
        for m in self.re_req_res.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.fmt_section)

        # Endpoints
        for m in self.re_endpoint.finditer(text):
            self.setFormat(m.start(1), m.end(1) - m.start(1), self.fmt_url)

        # Trace IDs
        for m in self.re_trace.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.fmt_trace)

        # HTTP methods
        for m in re.finditer(r'\b(GET|POST|PUT|DELETE|PATCH)\b', text):
            word = m.group(1)
            fmt = self.fmt_get
            if word == "POST":
                fmt = self.fmt_post
            elif word in ("PUT", "PATCH"):
                fmt = self.fmt_put
            elif word == "DELETE":
                fmt = self.fmt_delete
            self.setFormat(m.start(), len(word), fmt)

        # JSON Keys
        key_spans = set()
        for m in self.re_key.finditer(text):
            start = m.start(1)
            length = m.end(1) - start
            self.setFormat(start, length, self.fmt_key)
            key_spans.add((start, m.end(1)))

        # JSON String values
        string_spans = []
        for m in self.re_str.finditer(text):
            s, e = m.span()
            if (s, e) in key_spans:
                continue
            self.setFormat(s, e - s, self.fmt_str)
            string_spans.append((s, e))

        all_quoted = list(key_spans) + string_spans

        # JSON Numbers (only outside quotes)
        for m in self.re_num.finditer(text):
            s, e = m.span(1)
            if not any(qs <= s and e <= qe for qs, qe in all_quoted):
                self.setFormat(s, e - s, self.fmt_num)

        # Booleans (only outside quotes)
        for m in self.re_bool.finditer(text):
            s, e = m.span(1)
            if not any(qs <= s and e <= qe for qs, qe in all_quoted):
                self.setFormat(s, e - s, self.fmt_bool)

        # Null (only outside quotes)
        for m in self.re_null.finditer(text):
            s, e = m.span(1)
            if not any(qs <= s and e <= qe for qs, qe in all_quoted):
                self.setFormat(s, e - s, self.fmt_null)

        # Brackets
        for m in self.re_brackets.finditer(text):
            s = m.start()
            if not any(qs <= s and s < qe for qs, qe in all_quoted):
                self.setFormat(s, 1, self.fmt_punct)


class DetailPanel(QWidget):
    filter_trace_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_entry = False
        self._current_entry: LogEntry | None = None
        self._current_tz: tzinfo | None = None
        self._matches: list[tuple[int, int]] = []
        self._current_match = -1
        self._font_size = 11

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- Top Metadata Header Card ---
        self.meta_card = QFrame()
        self.meta_card.setObjectName("detailMetaCard")
        self._apply_meta_card_style()

        meta_lay = QVBoxLayout(self.meta_card)
        meta_lay.setContentsMargins(10, 8, 10, 8)
        meta_lay.setSpacing(6)

        # Row 1: Badges (Level, Time, Trace ID, Actions)
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.level_badge = QLabel("LEVEL")
        self.level_badge.setObjectName("levelBadge")
        self.level_badge.setAlignment(Qt.AlignCenter)
        self.level_badge.setFixedHeight(22)

        self.time_label = QLabel()
        self.time_label.setStyleSheet("font-weight: 600; font-family: Consolas, monospace;")

        # Trace ID Pill with quick copy and filter
        self.trace_box = QWidget()
        trace_lay = QHBoxLayout(self.trace_box)
        trace_lay.setContentsMargins(0, 0, 0, 0)
        trace_lay.setSpacing(4)
        self.trace_label = QLabel()
        self.trace_label.setStyleSheet(
            "background: rgba(45, 212, 191, 0.15); color: #2dd4bf; "
            "border: 1px solid rgba(45, 212, 191, 0.35); border-radius: 4px; "
            "padding: 2px 6px; font-family: Consolas, monospace; font-size: 11px; font-weight: 600;"
        )
        self.copy_trace_btn = QToolButton(text="📋")
        self.copy_trace_btn.setToolTip("Sao chép Trace ID vào clipboard")
        self.copy_trace_btn.setStyleSheet("padding: 2px 4px; border: none; font-size: 11px;")
        self.copy_trace_btn.clicked.connect(self._copy_trace_id)

        self.filter_trace_btn = QToolButton(text="🔍")
        self.filter_trace_btn.setToolTip("Lọc tất cả log theo Trace ID này")
        self.filter_trace_btn.setStyleSheet("padding: 2px 4px; border: none; font-size: 11px;")
        self.filter_trace_btn.clicked.connect(self._filter_trace)

        trace_lay.addWidget(self.trace_label)
        trace_lay.addWidget(self.copy_trace_btn)
        trace_lay.addWidget(self.filter_trace_btn)

        row1.addWidget(self.level_badge)
        row1.addWidget(self.time_label)
        row1.addWidget(self.trace_box)
        row1.addStretch(1)

        # Action buttons
        self.copy_json_btn = QPushButton("📋 Copy JSON")
        self.copy_json_btn.setToolTip("Sao chép riêng phần JSON Payload hoặc Response đã format")
        self.copy_json_btn.setStyleSheet(
            "QPushButton { padding: 3px 8px; font-weight: 500; font-size: 11px; "
            "background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 4px; } "
            "QPushButton:hover { background: rgba(59, 130, 246, 0.28); }"
        )
        self.copy_json_btn.clicked.connect(self._copy_json)

        self.copy_all_btn = QPushButton("📋 Copy Tất cả")
        self.copy_all_btn.setToolTip("Sao chép đầy đủ chi tiết log gồm thông tin header và message")
        self.copy_all_btn.setStyleSheet(
            "QPushButton { padding: 3px 8px; font-size: 11px; border-radius: 4px; } "
        )
        self.copy_all_btn.clicked.connect(self._copy_all)

        self.wrap_btn = QToolButton(text="🔤 Wrap")
        self.wrap_btn.setCheckable(True)
        self.wrap_btn.setChecked(True)
        self.wrap_btn.setToolTip("Tự động xuống dòng")
        self.wrap_btn.setStyleSheet("padding: 3px 6px; font-size: 11px;")
        self.wrap_btn.toggled.connect(self._toggle_wrap)

        self.zoom_out_btn = QToolButton(text="A-")
        self.zoom_out_btn.setToolTip("Thu nhỏ chữ")
        self.zoom_out_btn.setStyleSheet("padding: 3px 6px; font-size: 11px;")
        self.zoom_out_btn.clicked.connect(lambda: self._adjust_font_size(-1))

        self.zoom_in_btn = QToolButton(text="A+")
        self.zoom_in_btn.setToolTip("Phóng to chữ")
        self.zoom_in_btn.setStyleSheet("padding: 3px 6px; font-size: 11px;")
        self.zoom_in_btn.clicked.connect(lambda: self._adjust_font_size(+1))

        self.search_btn = QToolButton(text="🔍 Tìm (Ctrl+F)")
        self.search_btn.setToolTip("Tìm kiếm trong nội dung chi tiết log (Ctrl+F)")
        self.search_btn.setStyleSheet("padding: 3px 6px; font-size: 11px;")
        self.search_btn.clicked.connect(self.open_search)

        row1.addWidget(self.copy_json_btn)
        row1.addWidget(self.copy_all_btn)
        row1.addWidget(self.wrap_btn)
        row1.addWidget(self.zoom_out_btn)
        row1.addWidget(self.zoom_in_btn)
        row1.addWidget(self.search_btn)

        # Row 2: Secondary info (Thread, Logger, Source file)
        self.row2 = QWidget()
        row2_lay = QHBoxLayout(self.row2)
        row2_lay.setContentsMargins(0, 0, 0, 0)
        row2_lay.setSpacing(12)

        self.thread_label = QLabel()
        self.thread_label.setStyleSheet("color: gray; font-size: 11px;")
        self.logger_label = QLabel()
        self.logger_label.setStyleSheet("color: gray; font-size: 11px;")
        self.source_label = QLabel()
        self.source_label.setStyleSheet("color: gray; font-size: 11px;")

        row2_lay.addWidget(self.thread_label)
        row2_lay.addWidget(self.logger_label)
        row2_lay.addWidget(self.source_label)
        row2_lay.addStretch(1)

        meta_lay.addLayout(row1)
        meta_lay.addWidget(self.row2)
        self.meta_card.hide()

        # --- In-Editor Search Bar (Ctrl+F) ---
        self.search_bar = QWidget()
        self.search_bar.setObjectName("detailSearchBar")
        self.search_bar.setStyleSheet(
            "#detailSearchBar { border-bottom: 1px solid palette(mid); background: palette(window); }"
        )
        s_lay = QHBoxLayout(self.search_bar)
        s_lay.setContentsMargins(8, 4, 8, 4)
        s_lay.setSpacing(6)

        self.search = QLineEdit(
            placeholderText="Tìm trong chi tiết log… (Enter: tiếp, Shift+Enter: trước, Esc: đóng)",
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

        # --- Text Editor ---
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._setup_editor_font()
        self.editor.setPlaceholderText("Chọn 1 dòng trong bảng log để xem chi tiết đầy đủ (nhấn Ctrl+F để tìm kiếm)")

        # Connect Syntax Highlighter
        self.highlighter = JsonLogSyntaxHighlighter(self.editor.document())

        lay.addWidget(self.meta_card)
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

    def _apply_meta_card_style(self):
        dark = is_dark_mode()
        bg = "#1e1e2e" if dark else "#f1f5f9"
        border = "#313244" if dark else "#e2e8f0"
        self.meta_card.setStyleSheet(
            f"#detailMetaCard {{ background: {bg}; border-bottom: 1px solid {border}; }}"
        )

    def _setup_editor_font(self):
        font = QFont("Cascadia Code")
        if not font.exactMatch():
            font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(self._font_size)
        self.editor.setFont(font)

    def _adjust_font_size(self, delta: int):
        self._font_size = max(8, min(24, self._font_size + delta))
        self._setup_editor_font()

    def _toggle_wrap(self, checked: bool):
        self.editor.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if checked else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def has_entry(self) -> bool:
        return self._has_entry

    def show_entry(self, e: LogEntry | None, tz: tzinfo | None):
        self._current_entry = e
        self._current_tz = tz
        if e is None:
            self._has_entry = False
            self.meta_card.hide()
            self.editor.clear()
            self._clear_highlights()
            return

        self._has_entry = True
        self.meta_card.show()
        self._apply_meta_card_style()

        # Update Level Badge
        lv = e.level or "INFO"
        self.level_badge.setText(f"● {lv}")
        badge_style = self._get_level_badge_style(lv)
        self.level_badge.setStyleSheet(badge_style)

        # Update Time
        time_str = display_time(e, tz)
        self.time_label.setText(f"🕒 {time_str}")
        self.time_label.setToolTip(f"Thời gian gốc (UTC): {e.ts_raw}")

        # Update Trace ID
        if e.trace_id:
            self.trace_box.show()
            self.trace_label.setText(f"Trace: {e.trace_id}")
            self.trace_label.setToolTip(f"Trace ID: {e.trace_id}")
        else:
            self.trace_box.hide()

        # Secondary info
        self.thread_label.setText(f"🧵 {e.thread}" if e.thread else "")
        self.thread_label.setVisible(bool(e.thread))
        self.logger_label.setText(f"📁 {e.logger.split('.')[-1]}" if e.logger else "")
        self.logger_label.setToolTip(e.logger)
        self.logger_label.setVisible(bool(e.logger))
        self.source_label.setText(f"📄 {e.source.split('/')[-1]}" if e.source else "")
        self.source_label.setToolTip(e.source)
        self.source_label.setVisible(bool(e.source))

        # Pretty Body
        raw_body = f"{e.message}\n{e.extra}" if e.extra else e.message
        body = pretty_message(raw_body)
        self.editor.setPlainText(body)

        # Re-run search if active
        if self.search_bar.isVisible() and self.search.text():
            self._run_search()

    def _get_level_badge_style(self, level: str) -> str:
        dark = is_dark_mode()
        if level == "ERROR":
            bg = "rgba(239, 68, 68, 0.22)" if dark else "#fee2e2"
            color = "#fca5a5" if dark else "#991b1b"
            border = "#ef4444"
        elif level == "WARN":
            bg = "rgba(245, 158, 11, 0.22)" if dark else "#fef3c7"
            color = "#fcd34d" if dark else "#92400e"
            border = "#f59e0b"
        elif level == "DEBUG":
            bg = "rgba(100, 116, 139, 0.22)" if dark else "#f1f5f9"
            color = "#cbd5e1" if dark else "#475569"
            border = "#64748b"
        else:  # INFO
            bg = "rgba(59, 130, 246, 0.22)" if dark else "#dbeafe"
            color = "#93c5fd" if dark else "#1e40af"
            border = "#3b82f6"

        return (
            f"background-color: {bg}; color: {color}; border: 1px solid {border}; "
            f"border-radius: 11px; padding: 2px 10px; font-weight: bold; font-size: 11px;"
        )

    def _copy_trace_id(self):
        if self._current_entry and self._current_entry.trace_id:
            QApplication.clipboard().setText(self._current_entry.trace_id)
            self._flash_button(self.copy_trace_btn, "✓")

    def _filter_trace(self):
        if self._current_entry and self._current_entry.trace_id:
            self.filter_trace_requested.emit(self._current_entry.trace_id)

    def _copy_json(self):
        """Extract and copy valid JSON block from message/payload if present."""
        if not self._current_entry:
            return
        text = self.editor.toPlainText()
        # Look for JSON payload or first bracket/brace
        for m in re.finditer(r'(?:Payload|Result|Response|Body):\s*([\[{].*?)(?=\n[A-Z][a-zA-Z0-9_ -]+:|\Z)', text, re.DOTALL):
            candidate = m.group(1).strip()
            try:
                obj = json.loads(candidate)
                formatted = json.dumps(obj, indent=2, ensure_ascii=False)
                QApplication.clipboard().setText(formatted)
                self._flash_button(self.copy_json_btn, "✓ Đã copy JSON!")
                return
            except Exception:
                pass

        # Try to find any top-level JSON in editor
        for m in re.finditer(r'([\[{].*?[\]}])', text, re.DOTALL):
            candidate = m.group(1).strip()
            try:
                obj = json.loads(candidate)
                formatted = json.dumps(obj, indent=2, ensure_ascii=False)
                QApplication.clipboard().setText(formatted)
                self._flash_button(self.copy_json_btn, "✓ Đã copy JSON!")
                return
            except Exception:
                pass

        # Fallback to entire text
        QApplication.clipboard().setText(text)
        self._flash_button(self.copy_json_btn, "✓ Đã copy!")

    def _copy_all(self):
        if not self._current_entry:
            return
        e = self._current_entry
        tz = self._current_tz
        head = [
            f"Thời gian : {display_time(e, tz)}   (gốc: {e.ts_raw})",
            f"Level     : {e.level}",
            f"Thread    : {e.thread}",
            f"Logger    : {e.logger}",
        ]
        if e.trace_id:
            head.append(f"Trace ID  : {e.trace_id}")
        if e.source:
            head.append(f"File      : {e.source}")
        body = self.editor.toPlainText()
        full = "\n".join(head) + "\n" + ("─" * 80) + "\n" + body
        QApplication.clipboard().setText(full)
        self._flash_button(self.copy_all_btn, "✓ Đã copy!")

    def _flash_button(self, btn, text: str):
        old_text = btn.text()
        btn.setText(text)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1400, lambda: btn.setText(old_text))

    # --- Search functionality ---
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
            self.search.setStyleSheet("QLineEdit { border: 1px solid #ef4444; }")
            return

        full_text = self.editor.toPlainText()
        self._matches = [(m.start(), m.end()) for m in pattern.finditer(full_text) if m.start() < m.end()]
        if not self._matches:
            self._current_match = -1
            self.editor.setExtraSelections([])
            self.count_label.setText("0/0")
            self.search.setStyleSheet("QLineEdit { border: 1px solid #ef4444; }")
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
