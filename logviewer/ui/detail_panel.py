from datetime import tzinfo

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QPlainTextEdit

from ..parser import LogEntry, display_time, pretty_message


class DetailPanel(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.setPlaceholderText("Chọn 1 dòng để xem chi tiết")

    def show_entry(self, e: LogEntry | None, tz: tzinfo | None):
        if e is None:
            self.clear()
            return
        head = [
            f"Thời gian : {display_time(e, tz)}   (gốc: {e.ts_raw})",
            f"Level     : {e.level}",
            f"Thread    : {e.thread}",
            f"Logger    : {e.logger}",
        ]
        if e.trace_id:
            head.append(f"Trace ID  : {e.trace_id}")
        head.append(f"File      : {e.source}")
        body = pretty_message(e.message)
        if e.extra:
            body += "\n" + e.extra
        self.setPlainText("\n".join(head) + "\n" + "─" * 80 + "\n" + body)
