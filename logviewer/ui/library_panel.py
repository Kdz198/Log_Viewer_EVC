"""Left sidebar: saved days, auto-grouped by month.
Click a day to open it; tick several days (or a whole month) and they are
opened merged right away.
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QMenu, QMessageBox,
                               QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..library import Library
from .minio_dialog import open_in_explorer
from .theme import Theme, is_dark_mode

KIND, KEY = Qt.UserRole, Qt.UserRole + 1
ERROR_COLOR = QColor(Theme.ERROR)


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
        self.setObjectName("libraryPanel")

        # --- Header Section ---
        head = QVBoxLayout()
        head.setContentsMargins(12, 12, 12, 8)
        head.setSpacing(8)

        # Primary MinIO Button
        minio_btn = QPushButton("☁  Tải từ MinIO…")
        minio_btn.setToolTip("Đăng nhập MinIO Console, chọn nơi lưu và tải gói log theo ngày (Ctrl+M)")
        minio_btn.setCursor(Qt.PointingHandCursor)
        minio_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #2563eb;"
            "  color: #ffffff;"
            "  border: none;"
            "  border-radius: 8px;"
            "  padding: 8px 12px;"
            "  font-weight: 600;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #1d4ed8;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #1e40af;"
            "}"
        )
        minio_btn.clicked.connect(self.open_minio)

        title_row = QHBoxLayout()
        title = QLabel("Lịch sử log đã lưu")
        title.setStyleSheet("font-weight: 600; font-size: 13px;")
        title_row.addWidget(title)
        title_row.addStretch(1)

        hint = QLabel("Click để mở · Tick để gộp · Del để xoá")
        hint.setStyleSheet("color: gray; font-size: 11px;")

        head.addWidget(minio_btn)
        head.addLayout(title_row)
        head.addWidget(hint)

        # --- Tree Widget ---
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._apply_tree_style()
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemChanged.connect(self._on_check_changed)
        self.tree.itemClicked.connect(self._on_clicked)
        self.tree.itemActivated.connect(self._on_clicked)
        self.tree.installEventFilter(self)

        # ticking a month fires one itemChanged per day, so open once they settle
        self._open_timer = QTimer(self, singleShot=True, interval=250)
        self._open_timer.timeout.connect(self._open_checked)

        # --- Multi-selection Floating Bottom Bar ---
        self.sel_label = QLabel()
        self.sel_label.setStyleSheet("font-weight: 600; font-size: 11px; color: #3b82f6;")
        clear_btn = QPushButton("Bỏ chọn")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(
            "QPushButton { border: 1px solid palette(mid); border-radius: 4px; padding: 2px 8px; font-size: 11px; }"
            "QPushButton:hover { background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border-color: #ef4444; }"
        )
        clear_btn.clicked.connect(self.clear_checks)

        self.bar = QFrame()
        self.bar.setObjectName("selBar")
        dark = is_dark_mode()
        self.bar.setStyleSheet(
            f"#selBar {{ background: {'#1e1e2e' if dark else '#f1f5f9'}; "
            f"border-top: 1px solid {'#313244' if dark else '#e2e8f0'}; }}"
        )
        bar_lay = QHBoxLayout(self.bar)
        bar_lay.setContentsMargins(12, 8, 12, 8)
        bar_lay.addWidget(self.sel_label, 1)
        bar_lay.addWidget(clear_btn)
        self.bar.hide()

        # --- Empty State ---
        self.empty = QLabel("📂 Chưa có log nào.\n\nMở file log (.zip, .tar.gz, .log) hoặc tải từ MinIO để tự động lưu vào đây.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet("color: gray; font-size: 12px; padding: 30px 16px; line-height: 1.4;")
        self.empty.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(head)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.empty)
        lay.addWidget(self.bar)
        self.refresh()

    def _apply_tree_style(self):
        dark = is_dark_mode()
        bg = "#181825" if dark else "#f8fafc"
        hover_bg = "rgba(255, 255, 255, 0.05)" if dark else "rgba(0, 0, 0, 0.04)"
        sel_bg = "rgba(59, 130, 246, 0.22)" if dark else "rgba(59, 130, 246, 0.15)"
        border_r = "#313244" if dark else "#e2e8f0"

        self.tree.setStyleSheet(
            f"QTreeWidget {{"
            f"  background-color: {bg};"
            f"  border: none;"
            f"  border-right: 1px solid {border_r};"
            f"}}"
            f"QTreeWidget::item {{"
            f"  padding: 6px 4px;"
            f"  border-radius: 4px;"
            f"  margin: 1px 4px;"
            f"}}"
            f"QTreeWidget::item:hover {{"
            f"  background-color: {hover_bg};"
            f"}}"
            f"QTreeWidget::item:selected {{"
            f"  background-color: {sel_bg};"
            f"  color: #3b82f6;"
            f"  font-weight: 600;"
            f"}}"
        )

    # ---------- building ----------
    def refresh(self):
        checked = set(self.checked_ids())
        collapsed = {
            self.tree.topLevelItem(i).data(0, KEY)
            for i in range(self.tree.topLevelItemCount())
            if not self.tree.topLevelItem(i).isExpanded()
        }
        self.tree.blockSignals(True)
        self.tree.clear()
        month_node = None
        for it in sorted(self.lib.items, key=lambda i: (i.date, i.name), reverse=True):
            month = _month_label(it.date)
            if month_node is None or month_node.data(0, KEY) != month:
                month_node = QTreeWidgetItem([f"📅 {month}", ""])
                month_node.setData(0, KIND, "month")
                month_node.setData(0, KEY, month)
                month_node.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                month_node.setForeground(0, QColor("gray"))
                f = QFont(month_node.font(0))
                f.setBold(True)
                month_node.setFont(0, f)
                self.tree.addTopLevelItem(month_node)
                month_node.setExpanded(month not in collapsed)

            err_badge = f"{it.errors:,} ERROR" if it.errors else ""
            node = QTreeWidgetItem([it.name, err_badge])
            node.setData(0, KIND, "item")
            node.setData(0, KEY, it.id)
            node.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            node.setCheckState(0, Qt.Checked if it.id in checked else Qt.Unchecked)
            node.setForeground(1, ERROR_COLOR)
            f_err = QFont(node.font(1))
            f_err.setBold(True)
            f_err.setPointSize(max(7, f_err.pointSize() - 1))
            node.setFont(1, f_err)
            node.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            stored_path = self.lib.path_of(it)
            node.setToolTip(
                0,
                f"File gốc: {it.original}\n"
                f"Nơi lưu: {stored_path}\n"
                f"{it.entries:,} entry · {it.errors:,} ERROR · {it.warns:,} WARN\n"
                f"Import lúc {it.imported_at.replace('T', ' ')}",
            )
            node.setToolTip(1, f"{it.errors:,} lỗi ERROR")
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
        self.tree.blockSignals(True)
        for n in self._day_nodes():
            f = QFont(n.font(0))
            is_active = n.data(0, KEY) in self.current_ids
            f.setBold(is_active)
            n.setFont(0, f)
            if is_active:
                n.setForeground(0, QColor("#3b82f6"))
            else:
                n.setData(0, Qt.ForegroundRole, None)
        self.tree.blockSignals(False)

    def _update_bar(self):
        n = len(self.checked_ids())
        self.bar.setVisible(n > 0)
        self.sel_label.setText(f"Đang gộp {n} ngày" if n > 1 else "Đã chọn 1 ngày")

    # ---------- interaction ----------
    def _on_check_changed(self, node, col):
        self._toggled = True
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
        if not it:
            return
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
            month_clean = node.data(0, KEY).replace("📅 ", "").lower()
            menu.addAction(f"Xem gộp cả {month_clean}", lambda: self.open_items.emit(ids))
            menu.addSeparator()
            menu.addAction(f"🗑 Xoá cứng cả {month_clean}…", lambda: self._hard_remove(ids))
        else:
            item_id = node.data(0, KEY)
            it = self.lib.get(item_id)
            checked = self.checked_ids()
            menu.addAction("Mở ngày này", lambda: self.open_items.emit([item_id]))
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
