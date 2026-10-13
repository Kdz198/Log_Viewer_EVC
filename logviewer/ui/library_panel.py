"""Left sidebar: saved days, auto-grouped by month.
Click a day to open it; tick several days (or a whole month) and they are
opened merged right away."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QInputDialog,
                               QLabel, QMenu, QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..library import Library
from .minio_dialog import open_in_explorer

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
    open_minio = Signal()

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.lib = library
        self.current_ids: set[str] = set()
        self._toggled = False

        minio_btn = QPushButton("☁ Tải từ MinIO…")
        minio_btn.setToolTip("Đăng nhập MinIO Console, chọn nơi lưu và tải gói log theo ngày (Ctrl+M)")
        minio_btn.setStyleSheet("font-weight: 600; padding: 5px 8px;")
        minio_btn.clicked.connect(self.open_minio)

        title = QLabel("Đã lưu")
        title.setStyleSheet("font-weight: 600; font-size: 13px;")
        hint = QLabel("Click để mở · tick nhiều ngày để gộp · Del để xoá cứng")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        head = QVBoxLayout()
        head.setContentsMargins(10, 8, 8, 6)
        head.setSpacing(4)
        head.addWidget(minio_btn)
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
        self.tree.installEventFilter(self)

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

        self.empty = QLabel("Chưa có ngày nào.\nMở 1 file log hoặc tải từ MinIO, app sẽ tự lưu vào đây.")
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
            stored_path = self.lib.path_of(it)
            node.setToolTip(
                0,
                f"File gốc: {it.original}\n"
                f"Nơi lưu: {stored_path}\n"
                f"{it.entries:,} entry · {it.errors:,} ERROR · {it.warns:,} WARN\n"
                f"Import lúc {it.imported_at.replace('T', ' ')}",
            )
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

    def _hard_remove(self, ids: list[str]):
        items = [self.lib.get(i) for i in ids if self.lib.get(i)]
        if not items:
            return
        names = ", ".join(it.name for it in items[:5]) + ("…" if len(items) > 5 else "")
        paths_preview = "\n".join(f"• {self.lib.path_of(it)}" for it in items[:4])
        if len(items) > 4:
            paths_preview += f"\n… và {len(items) - 4} file khác"

        ext_sources = [Path(it.source_path) for it in items if it.source_path and Path(it.source_path).is_file()]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Xoá cứng file log")
        box.setText(f"Bạn có chắc muốn XOÁ CỨNG (xoá vĩnh viễn khỏi ổ cứng) {len(items)} ngày ({names})?")
        box.setInformativeText(f"File trong thư mục lưu sẽ bị xoá vĩnh viễn:\n{paths_preview}")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)

        del_ext_cb = None
        if ext_sources:
            del_ext_cb = QCheckBox(f"Xoá luôn cả file gốc lúc import ở ngoài ({len(ext_sources)} file)")
            del_ext_cb.setChecked(True)
            box.setCheckBox(del_ext_cb)

        if box.exec() == QMessageBox.Yes:
            del_orig = bool(del_ext_cb and del_ext_cb.isChecked())
            self.lib.remove(ids, delete_files=True, delete_original=del_orig)
            self.refresh()
            self.removed.emit(ids)

    def _soft_remove(self, ids: list[str]):
        items = [self.lib.get(i) for i in ids if self.lib.get(i)]
        if not items:
            return
        names = ", ".join(it.name for it in items[:5]) + ("…" if len(items) > 5 else "")
        if QMessageBox.question(
            self,
            "Bỏ khỏi danh sách",
            f"Bỏ {len(items)} ngày ({names}) khỏi danh sách hiển thị?\n"
            f"(File log trong thư mục lưu {self.lib.files_dir} vẫn được giữ lại)",
        ) == QMessageBox.Yes:
            self.lib.remove(ids, delete_files=False)
            self.refresh()
            self.removed.emit(ids)

    def eventFilter(self, obj, event):
        if obj is self.tree and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete:
            checked = self.checked_ids()
            if checked:
                self._hard_remove(checked)
                return True
            cur = self.tree.currentItem()
            if cur and cur.data(0, KIND) == "item":
                self._hard_remove([cur.data(0, KEY)])
                return True
        return super().eventFilter(obj, event)

    def _context_menu(self, pos):
        node = self.tree.itemAt(pos)
        if node is None:
            menu = QMenu(self)
            menu.addAction("Mở thư mục lưu log…", lambda: open_in_explorer(self.lib.files_dir))
            menu.exec(self.tree.viewport().mapToGlobal(pos))
            return
        menu = QMenu(self)
        if node.data(0, KIND) == "month":
            ids = [node.child(j).data(0, KEY) for j in range(node.childCount())]
            menu.addAction(f"Xem gộp cả {node.data(0, KEY).lower()}", lambda: self.open_items.emit(ids))
            menu.addSeparator()
            menu.addAction(f"🗑 Xoá cứng cả {node.data(0, KEY).lower()}…", lambda: self._hard_remove(ids))
        else:
            item_id = node.data(0, KEY)
            it = self.lib.get(item_id)
            checked = self.checked_ids()
            menu.addAction("Mở", lambda: self.open_items.emit([item_id]))
            if len(checked) > 1:
                menu.addAction(f"Xem gộp {len(checked)} ngày đã chọn", lambda: self.open_items.emit(checked))
            if it:
                menu.addAction("Mở vị trí file trong Explorer", lambda: open_in_explorer(self.lib.path_of(it)))
            menu.addAction("Đổi tên…", lambda: self._rename(item_id))
            menu.addSeparator()
            menu.addAction("🗑 Xoá cứng file (xoá vĩnh viễn khỏi ổ cứng)…", lambda: self._hard_remove([item_id]))
            if len(checked) > 1:
                menu.addAction(
                    f"🗑 Xoá cứng {len(checked)} ngày đã chọn…",
                    lambda: self._hard_remove(checked),
                )
            menu.addAction("Bỏ khỏi danh sách (giữ lại file)", lambda: self._soft_remove([item_id]))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

