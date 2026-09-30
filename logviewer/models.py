"""Table model: holds all entries and shows only the filtered row indices.
QTableView only asks for visible rows, so a full day of logs stays smooth."""
from datetime import tzinfo

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from .parser import LogEntry, display_time

MAX_MSG_CHARS = 400


class LogTableModel(QAbstractTableModel):
    COLUMNS = ("Thời gian", "Level", "Message")
    COL_TIME, COL_LEVEL, COL_MESSAGE = range(3)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: list[LogEntry] = []
        self.rows: list[int] = []
        self.tz: tzinfo | None = None

    def set_entries(self, entries: list[LogEntry]):
        self.beginResetModel()
        self.entries = entries
        self.rows = list(range(len(entries)))
        self.endResetModel()

    def set_rows(self, rows: list[int]):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def entry_at(self, row: int) -> LogEntry:
        return self.entries[self.rows[row]]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        e = self.entry_at(index.row())
        col = index.column()
        if role == Qt.DisplayRole:
            if col == self.COL_TIME:
                return display_time(e, self.tz)
            if col == self.COL_LEVEL:
                return e.level
            return e.message if len(e.message) <= MAX_MSG_CHARS else e.message[:MAX_MSG_CHARS] + "…"
        if role == Qt.ToolTipRole and col == self.COL_MESSAGE and len(e.message) > MAX_MSG_CHARS:
            return e.message[:2000]
        return None
