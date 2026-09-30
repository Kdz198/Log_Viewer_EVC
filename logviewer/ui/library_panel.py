"""Left sidebar: saved days, auto-grouped by month.
Click a day to open it; tick several days (or a whole month) and they are
opened merged right away."""
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMenu,
                               QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..library import Library

KIND, KEY = Qt.UserRole, Qt.UserRole + 1
ERROR_COLOR = QColor("#e5484d")


def _month_label(date: str) -> str:
    try:
        return datetime.strptime(date, "%Y-%m-%d").strftime("Tháng %m/%Y")
    except ValueError:
        return "Không rõ ngày"


class LibraryPanel(QWidget):
    open_items = Signal(list)  # item ids, 1 = single day, more = merged
    removed = Signal(list)

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.lib = library
        self.current_ids: set[str] = set()
        self._toggled = False

        title = QLabel("Đã lưu")
        title.setStyleSheet("font-weight: 600; font-size: 13px;")
        hint = QLabel("Click để mở 1 ngày · tick nhiều ngày để gộp")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        head = QVBoxLayout()
        head.setContentsMargins(10, 8, 8, 6)
        head.setSpacing(2)
        head.addWidget(title)
        head.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setStyleSheet("QTreeWidget { border: none; } QTreeWidget::item { padding: 4px 2px; }")
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemChanged.connect(self._on_check_changed)
        self.tree.itemClicked.connect(self._on_clicked)
        self.tree.itemActivated.connect(self._on_clicked)

        # ticking a month fires one itemChanged per day, so open once they settle
        self._open_timer = QTimer(self, singleShot=True, interval=250)
        self._open_timer.timeout.connect(self._open_checked)

        # shown while days are ticked
        self.sel_label = QLabel()
        clear_btn = QPushButton("Bỏ chọn")
        clear_btn.setFlat(True)
        clear_btn.clicked.connect(self.clear_checks)
        self.bar = QWidget()
        self.bar.setStyleSheet("QWidget#bar { border-top: 1px solid palette(mid); }")
        self.bar.setObjectName("bar")
        bar_lay = QHBoxLayout(self.bar)
        bar_lay.setContentsMargins(10, 6, 8, 8)
        bar_lay.addWidget(self.sel_label, 1)
        bar_lay.addWidget(clear_btn)
        self.bar.hide()

        self.empty = QLabel("Chưa có ngày nào.\nMở 1 file log, app sẽ tự lưu vào đây.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet("color: gray; padding: 20px;")
        self.empty.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(head)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.empty)
        lay.addWidget(self.bar)
        self.refresh()

    # ---------- building ----------
    def refresh(self):
        checked = set(self.checked_ids())
        collapsed = {self.tree.topLevelItem(i).data(0, KEY) for i in range(self.tree.topLevelItemCount())
                     if not self.tree.topLevelItem(i).isExpanded()}
        self.tree.blockSignals(True)
        self.tree.clear()
        month_node = None
        for it in sorted(self.lib.items, key=lambda i: (i.date, i.name), reverse=True):
            month = _month_label(it.date)
            if month_node is None or month_node.data(0, KEY) != month:
                month_node = QTreeWidgetItem([month, ""])
                month_node.setData(0, KIND, "month")
                month_node.setData(0, KEY, month)
                month_node.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                month_node.setForeground(0, QColor("gray"))
                self.tree.addTopLevelItem(month_node)
                month_node.setExpanded(month not in collapsed)
            node = QTreeWidgetItem([it.name, f"{it.errors:,}" if it.errors else ""])
            node.setData(0, KIND, "item")
            node.setData(0, KEY, it.id)
            node.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            node.setCheckState(0, Qt.Checked if it.id in checked else Qt.Unchecked)
            node.setForeground(1, ERROR_COLOR)
            node.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            node.setToolTip(0, f"{it.original}\n{it.entries:,} entry · {it.errors:,} ERROR · {it.warns:,} WARN\n"
                               f"Import lúc {it.imported_at.replace('T', ' ')}")
            node.setToolTip(1, f"{it.errors:,} ERROR")
            month_node.addChild(node)
        self.tree.blockSignals(False)
        self.empty.setVisible(not self.lib.items)
        self._paint_current()
        self._update_bar()

    def _day_nodes(self):
        for i in range(self.tree.topLevelItemCount()):
            month = self.tree.topLevelItem(i)
            for j in range(month.childCount()):
                yield month.child(j)

    def checked_ids(self) -> list[str]:
        return [n.data(0, KEY) for n in self._day_nodes() if n.checkState(0) == Qt.Checked]

    def clear_checks(self):
        self.tree.blockSignals(True)
        for n in self._day_nodes():
            n.setCheckState(0, Qt.Unchecked)
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, Qt.Unchecked)
        self.tree.blockSignals(False)
        self._update_bar()

    def set_current(self, ids: list[str]):
        self.current_ids = set(ids)
        self._paint_current()

    def _paint_current(self):
        # setFont emits itemChanged, which would look like a checkbox toggle
        self.tree.blockSignals(True)
        for n in self._day_nodes():
            f = QFont(n.font(0))
            f.setBold(n.data(0, KEY) in self.current_ids)
            n.setFont(0, f)
        self.tree.blockSignals(False)

    def _update_bar(self):
        n = len(self.checked_ids())
        self.bar.setVisible(n > 0)
        self.sel_label.setText(f"Đang gộp {n} ngày" if n > 1 else "Đã chọn 1 ngày")

    # ---------- interaction ----------
    def _on_check_changed(self, node, col):
        self._toggled = True  # the click that follows was on the checkbox, not "open"
        self._update_bar()
        self._open_timer.start()

    def _open_checked(self):
        ids = self.checked_ids()
        if ids:
            self.open_items.emit(ids)

    def _on_clicked(self, node, _col=0):
        toggled, self._toggled = self._toggled, False
        if toggled:
            return
        if node.data(0, KIND) == "item":
            self.open_items.emit([node.data(0, KEY)])
        else:
            node.setExpanded(not node.isExpanded())

    def _rename(self, item_id: str):
        it = self.lib.get(item_id)
        name, ok = QInputDialog.getText(self, "Đổi tên", "Tên mới:", text=it.name)
        if ok and name.strip():
            self.lib.rename(item_id, name.strip())
            self.refresh()

    def _remove(self, ids: list[str]):
        names = ", ".join(self.lib.get(i).name for i in ids[:5]) + ("…" if len(ids) > 5 else "")
        if QMessageBox.question(self, "Xoá khỏi danh sách",
                                f"Xoá {len(ids)} ngày đã lưu ({names})?\n"
                                "File gốc bạn đã tải về không bị ảnh hưởng.") == QMessageBox.Yes:
            self.lib.remove(ids)
            self.refresh()
            self.removed.emit(ids)

    def _context_menu(self, pos):
        node = self.tree.itemAt(pos)
        if node is None:
            return
        menu = QMenu(self)
        if node.data(0, KIND) == "month":
            ids = [node.child(j).data(0, KEY) for j in range(node.childCount())]
            menu.addAction(f"Xem gộp cả {node.data(0, KEY).lower()}", lambda: self.open_items.emit(ids))
        else:
            item_id = node.data(0, KEY)
            checked = self.checked_ids()
            menu.addAction("Mở", lambda: self.open_items.emit([item_id]))
            if len(checked) > 1:
                menu.addAction(f"Xem gộp {len(checked)} ngày đã chọn", lambda: self.open_items.emit(checked))
            menu.addAction("Đổi tên…", lambda: self._rename(item_id))
            menu.addSeparator()
            menu.addAction("Xoá khỏi danh sách", lambda: self._remove([item_id]))
            if len(checked) > 1:
                menu.addAction(f"Xoá {len(checked)} ngày đã chọn", lambda: self._remove(checked))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
