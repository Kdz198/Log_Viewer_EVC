import bisect
import re
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QSplitter, QTableView,
                               QVBoxLayout, QWidget)

try:
    from .. import __version__
    from ..library import Library
    from ..loader import HOUR_RE, load_source, merged_text
    from ..models import LogTableModel
    from ..parser import VN_TZ, LogEntry, parse_text
    from .detail_panel import DetailPanel
    from .filter_bar import FilterBar
    from .library_panel import LibraryPanel
    from .loading_overlay import LoadingOverlay
    from .log_delegate import LogDelegate
    from .minio_dialog import MinioDialog
    from .theme import get_app_stylesheet, is_dark_mode
except (ImportError, ValueError):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from logviewer import __version__
    from logviewer.library import Library
    from logviewer.loader import HOUR_RE, load_source, merged_text
    from logviewer.models import LogTableModel
    from logviewer.parser import VN_TZ, LogEntry, parse_text
    from logviewer.ui.detail_panel import DetailPanel
    from logviewer.ui.filter_bar import FilterBar
    from logviewer.ui.library_panel import LibraryPanel
    from logviewer.ui.loading_overlay import LoadingOverlay
    from logviewer.ui.log_delegate import LogDelegate
    from logviewer.ui.minio_dialog import MinioDialog
    from logviewer.ui.theme import get_app_stylesheet, is_dark_mode


class LoadWorker(QThread):
    progress = Signal(str)
    loaded = Signal(object, object, object)  # entries, chunks, per_file
    failed = Signal(str)

    def __init__(self, paths: list):
        super().__init__()
        self.paths = paths

    def run(self):
        try:
            chunks = []
            entries: list[LogEntry] = []
            per_file: list[tuple[Path, list, list[LogEntry]]] = []
            for path in self.paths:
                f_chunks = load_source(path, self.progress.emit)
                f_entries: list[LogEntry] = []
                total_chunks = len(f_chunks)
                for idx, (name, text) in enumerate(f_chunks, 1):
                    self.progress.emit(f"Đang phân tích {Path(name).name} ({idx}/{total_chunks})")
                    f_entries += parse_text(text, source=name)
                chunks += f_chunks
                entries += f_entries
                per_file.append((Path(path), f_chunks, f_entries))
            self.loaded.emit(entries, chunks, per_file)
        except Exception as ex:  # shown to the user, never crash the UI
            self.failed.emit(f"{type(ex).__name__}: {ex}")


def detect_date(chunks, entries: list[LogEntry], source: Path | None = None) -> str:
    """Day of a log bundle: from the hourly file names, else the most common VN date."""
    for name, _ in chunks:
        if m := HOUR_RE.search(name):
            return m.group(1)
    days = Counter(e.ts.astimezone(VN_TZ).date().isoformat() for e in entries if e.ts and e.ts.tzinfo)
    if days:
        return days.most_common(1)[0][0]
    if source and (m := re.search(r"(\d{4}-\d{2}-\d{2})", source.name)):
        return m.group(1)
    return ""


class EmptyStateWidget(QWidget):
    """Welcoming card shown when no log file is opened."""
    open_minio_requested = Signal()
    open_file_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("emptyStateWidget")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 40, 20, 40)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setObjectName("emptyCard")
        dark = is_dark_mode()
        bg = "#1e1e2e" if dark else "#ffffff"
        border = "#313244" if dark else "#e2e8f0"
        card.setStyleSheet(
            f"#emptyCard {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border};"
            f"  border-radius: 12px;"
            f"  max-width: 580px;"
            f"}}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(36, 32, 36, 32)
        card_lay.setSpacing(14)
        card_lay.setAlignment(Qt.AlignCenter)

        icon_label = QLabel("⚡")
        icon_label.setStyleSheet("font-size: 38px;")
        icon_label.setAlignment(Qt.AlignCenter)

        title = QLabel("Chào mừng đến với Log Viewer")
        t_font = QFont(title.font())
        t_font.setPointSize(16)
        t_font.setBold(True)
        title.setFont(t_font)
        title.setAlignment(Qt.AlignCenter)

        desc = QLabel(
            "Kéo thả file log (.zip, .tar.gz, .log) vào đây,\n"
            "hoặc chọn một trong các thao tác nhanh bên dưới:"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: gray; font-size: 13px; line-height: 1.4;")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        minio_btn = QPushButton("☁ Tải từ MinIO…")
        minio_btn.setCursor(Qt.PointingHandCursor)
        minio_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #2563eb;"
            "  color: #ffffff;"
            "  border: none;"
            "  border-radius: 8px;"
            "  padding: 8px 16px;"
            "  font-weight: 600;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover { background-color: #1d4ed8; }"
        )
        minio_btn.clicked.connect(self.open_minio_requested)

        file_btn = QPushButton("📁 Mở file…")
        file_btn.setCursor(Qt.PointingHandCursor)
        file_btn.setStyleSheet(
            "QPushButton {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 8px;"
            "  padding: 8px 16px;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover { background-color: rgba(59, 130, 246, 0.12); border-color: #3b82f6; }"
        )
        file_btn.clicked.connect(self.open_file_requested)

        folder_btn = QPushButton("📂 Mở thư mục…")
        folder_btn.setCursor(Qt.PointingHandCursor)
        folder_btn.setStyleSheet(
            "QPushButton {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 8px;"
            "  padding: 8px 16px;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover { background-color: rgba(59, 130, 246, 0.12); border-color: #3b82f6; }"
        )
        folder_btn.clicked.connect(self.open_folder_requested)

        btn_row.addWidget(minio_btn)
        btn_row.addWidget(file_btn)
        btn_row.addWidget(folder_btn)

        hints = QLabel(
            "Phím tắt:  <b>Ctrl+M</b> MinIO  ·  <b>Ctrl+O</b> Mở file  ·  <b>F8/F7</b> Duyệt ERROR/WARN  ·  <b>Ctrl+F</b> Tìm chi tiết"
        )
        hints.setAlignment(Qt.AlignCenter)
        hints.setStyleSheet("color: gray; font-size: 11px; margin-top: 10px;")

        card_lay.addWidget(icon_label)
        card_lay.addWidget(title)
        card_lay.addWidget(desc)
        card_lay.addLayout(btn_row)
        card_lay.addWidget(hints)

        outer.addWidget(card)


class MainWindow(QMainWindow):
    def __init__(self, library: Library | None = None):
        super().__init__()
        self.setWindowTitle(f"Log Viewer {__version__}")
        self.resize(1400, 850)
        self.setAcceptDrops(True)
        self.setStyleSheet(get_app_stylesheet())

        self.library = library or Library()
        self.current_label = ""
        self.last_dir = str(Path.home() / "Downloads")
        self.chunks: list = []
        self.worker: LoadWorker | None = None
        self._import_from: Path | None = None
        self._import_many: bool = False
        self._loading_ids: list[str] = []
        self._pending_label: str = ""
        self._queued: tuple | None = None

        self.model = LogTableModel(self)
        self.filter_bar = FilterBar()

        # Table View
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setMouseTracking(True)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.delegate = LogDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.table.entered.connect(lambda idx: self.delegate.set_hover_row(idx.row()))
        self.table.viewport().installEventFilter(self)

        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setHighlightSections(False)
        hh.resizeSection(0, 180)
        hh.resizeSection(1, 85)
        hh.setStretchLastSection(True)
        dark = is_dark_mode()
        hh_bg = "#181825" if dark else "#f1f5f9"
        hh_border = "#313244" if dark else "#e2e8f0"
        self.table.setStyleSheet(
            f"QHeaderView::section {{"
            f"  padding: 7px 10px;"
            f"  border: none;"
            f"  border-bottom: 1px solid {hh_border};"
            f"  background: {hh_bg};"
            f"  font-weight: 600;"
            f"  font-size: 11px;"
            f"}}"
        )
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._filter_by_row_trace)
        self.table.selectionModel().currentRowChanged.connect(self._show_current)

        # Detail Panel
        self.detail = DetailPanel()
        self.detail.filter_trace_requested.connect(self.filter_bar.set_search)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.detail)
        self.splitter.setSizes([560, 260])

        # Modern Empty State Card
        self.empty_state = EmptyStateWidget()
        self.empty_state.open_minio_requested.connect(self.open_minio_dialog)
        self.empty_state.open_file_requested.connect(self.open_dialog)
        self.empty_state.open_folder_requested.connect(self.open_folder_dialog)

        viewer = QWidget()
        lay = QVBoxLayout(viewer)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.filter_bar)
        lay.addWidget(self.empty_state, 1)
        lay.addWidget(self.splitter, 1)
        self.splitter.hide()

        self.library_panel = LibraryPanel(self.library)
        self.library_panel.open_items.connect(self.open_items)
        self.library_panel.removed.connect(self._on_library_removed)
        self.library_panel.open_minio.connect(self.open_minio_dialog)

        main_split = QSplitter(Qt.Horizontal)
        main_split.addWidget(self.library_panel)
        main_split.addWidget(viewer)
        main_split.setStretchFactor(1, 1)
        main_split.setSizes([260, 1140])
        self.setCentralWidget(main_split)

        self.status = QLabel("Sẵn sàng")
        self.statusBar().addWidget(self.status, 1)

        self.filter_bar.changed.connect(self.apply_filters)
        self.model.tz = VN_TZ
        self._build_menu()
        self.loading_overlay = LoadingOverlay(self)

    # ---------- menu ----------
    def _build_menu(self):
        def act(menu, text, slot, shortcut=None):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        m = self.menuBar().addMenu("&File")
        act(m, "Tải log từ MinIO…", self.open_minio_dialog, "Ctrl+M")
        act(m, "Đổi thư mục lưu log…", self.change_storage_dialog)
        m.addSeparator()
        act(m, "Mở file…", self.open_dialog, "Ctrl+O")
        act(m, "Mở thư mục…", self.open_folder_dialog, "Ctrl+Shift+O")
        m.addSeparator()
        act(m, "Xuất log gộp cả ngày…", self.export_merged, "Ctrl+S")
        act(m, "Xuất các dòng đang lọc…", self.export_filtered, "Ctrl+Shift+S")
        m.addSeparator()
        act(m, "Thoát", self.close, "Ctrl+Q")

        m = self.menuBar().addMenu("&Xem")
        act(m, "Tìm kiếm (chi tiết / tổng)", self._focus_search, "Ctrl+F")
        act(m, "Tìm kiếm tổng (bộ lọc)", self._focus_global_search, "Ctrl+Shift+F")
        act(m, "ERROR tiếp theo", lambda: self._jump_level("ERROR", +1), "F8")
        act(m, "ERROR trước đó", lambda: self._jump_level("ERROR", -1), "Shift+F8")
        act(m, "WARN tiếp theo", lambda: self._jump_level("WARN", +1), "F7")
        act(m, "WARN trước đó", lambda: self._jump_level("WARN", -1), "Shift+F7")
        act(m, "Xoá tất cả bộ lọc", self.clear_filters, "Ctrl+R")

    # ---------- loading ----------
    def open_minio_dialog(self):
        dlg = MinioDialog(self.library, self)
        dlg.files_downloaded.connect(self.open_downloaded_paths)
        dlg.storage_changed.connect(self._on_storage_changed)
        dlg.exec()

    def change_storage_dialog(self):
        new_dir = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục lưu trữ log", str(self.library.root)
        )
        if not new_dir:
            return
        target = Path(new_dir).resolve()
        if target == self.library.root.resolve():
            return
        try:
            copied = self.library.change_storage_dir(target)
        except OSError as ex:
            QMessageBox.critical(self, "Không đổi được thư mục lưu", f"Lỗi khi chuyển file log:\n{ex}")
            return
        self._on_storage_changed()
        QMessageBox.information(
            self,
            "Đã đổi nơi lưu log",
            f"Đã chuyển thư mục lưu log sang:\n{self.library.root}\n\n"
            f"Đã tự động copy {copied} file log từ thư mục cũ sang thư mục mới.",
        )

    def _on_storage_changed(self):
        self.library_panel.refresh()
        existing_ids = {i.id for i in self.library.items}
        remaining = list(self.library_panel.current_ids & existing_ids)
        self.library_panel.set_current(remaining)
        if not remaining and self.model.entries:
            self._clear_current_view()

    def open_downloaded_paths(self, paths: list[str]):
        if not paths:
            return
        if len(paths) == 1:
            self._start_load(paths, Path(paths[0]).name, import_from=Path(paths[0]))
        else:
            label = f"{len(paths)} ngày từ MinIO"
            self._start_load(paths, label, import_many=True)

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file log", "", "Log (*.zip *.tar.gz *.tgz *.gz *.log *.txt);;Tất cả (*.*)")
        if path:
            self.open_path(path)

    def open_folder_dialog(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa log")
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        """Open a file from disk; it is saved to the library once it loads."""
        self.last_dir = str(Path(path).parent)
        self._start_load([path], Path(path).name, import_from=Path(path))

    def open_items(self, ids: list[str]):
        """Open one saved day, or several merged in chronological order."""
        items = sorted(filter(None, map(self.library.get, ids)), key=lambda i: (i.date, i.name))
        if not items:
            return
        label = items[0].name if len(items) == 1 else f"{len(items)} ngày: {items[0].name} → {items[-1].name}"
        self._start_load([self.library.path_of(i) for i in items], label, ids=[i.id for i in items])

    def _start_load(self, paths: list, label: str, import_from: Path | None = None,
                    ids: list[str] | None = None, import_many: bool = False):
        if self.worker and self.worker.isRunning():
            self._queued = (paths, label, import_from, ids, import_many)  # latest request wins
            return
        self._pending_label = label
        self._import_from = import_from
        self._import_many = import_many
        self._loading_ids = ids or []
        self.status.setText(f"Đang mở {label}…")
        self.loading_overlay.start(f"Đang mở {label}", "Đang chuẩn bị đọc dữ liệu…")
        self.worker = LoadWorker([str(p) for p in paths])
        self.worker.progress.connect(self._on_load_progress)
        self.worker.loaded.connect(self._on_loaded)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_load_progress(self, msg: str):
        self.status.setText(msg)
        self.loading_overlay.set_status(msg)

    def _on_loaded(self, entries: list[LogEntry], chunks, per_file: list | None = None):
        self.chunks = chunks
        self.current_label = self._pending_label
        ids = self._loading_ids
        if self._import_from is not None:
            ids = self._save_to_library(self._import_from, chunks, entries) or ids
        elif self._import_many and per_file:
            saved_ids = []
            for src_path, f_chunks, f_entries in per_file:
                res = self._save_to_library(src_path, f_chunks, f_entries)
                if res:
                    saved_ids.extend(res)
            if saved_ids:
                ids = saved_ids
                items = [self.library.get(i) for i in ids if self.library.get(i)]
                if len(items) > 1:
                    self.current_label = f"{len(items)} ngày: {items[0].name} → {items[-1].name}"
        elif len(ids) == 1:
            self._refresh_stats(ids[0], entries)
        self.library_panel.set_current(ids)
        self.empty_state.hide()
        self.splitter.show()
        self.setWindowTitle(f"{self.current_label} — Log Viewer {__version__}")
        self.model.set_entries(entries)
        self.filter_bar.set_counts(Counter(e.level for e in entries))
        self.apply_filters()
        self.detail.show_entry(None, None)

    def _save_to_library(self, source: Path, chunks, entries) -> list[str] | None:
        levels = Counter(e.level for e in entries)
        stats = {"entries": len(entries), "errors": levels["ERROR"], "warns": levels["WARN"]}
        try:
            item, is_new = self.library.import_source(source, detect_date(chunks, entries, source), stats)
        except OSError as ex:
            QMessageBox.warning(self, "Không lưu được", f"Không lưu được vào danh sách:\n{ex}")
            return None
        self.current_label = item.name
        self.library_panel.refresh()
        self.statusBar().showMessage(
            f"Đã lưu “{item.name}” vào {self.library.files_dir}" if is_new else f"File này đã có sẵn: “{item.name}”",
            5000,
        )
        return [item.id]

    def _refresh_stats(self, item_id: str, entries: list[LogEntry]):
        """Keep sidebar counts in sync when the parser improves after an import."""
        item = self.library.get(item_id)
        levels = Counter(e.level for e in entries)
        stats = (len(entries), levels["ERROR"], levels["WARN"])
        if item and (item.entries, item.errors, item.warns) != stats:
            item.entries, item.errors, item.warns = stats
            self.library.save()
            self.library_panel.refresh()

    def _on_library_removed(self, ids: list):
        remaining = list(self.library_panel.current_ids - set(ids))
        self.library_panel.set_current(remaining)
        if not remaining and self.model.entries:
            self._clear_current_view()

    def _clear_current_view(self):
        self.chunks = []
        self.current_label = ""
        self.setWindowTitle(f"Log Viewer {__version__}")
        self.model.set_entries([])
        self.filter_bar.set_counts(Counter())
        self.detail.show_entry(None, None)
        self.splitter.hide()
        self.empty_state.show()
        self.status.setText("Đã xoá file log.")

    def _on_worker_finished(self):
        self.loading_overlay.stop()
        if self._queued:
            queued, self._queued = self._queued, None
            self._start_load(*queued)

    def _on_failed(self, msg: str):
        self.loading_overlay.stop()
        self.status.setText("Lỗi khi mở file")
        QMessageBox.critical(self, "Không mở được file", msg)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.open_path(urls[0].toLocalFile())

    # ---------- filtering ----------
    def apply_filters(self):
        st = self.filter_bar.state()
        if st is None:
            return
        keep_entry = self._current_entry_index()
        rows = []
        for i, e in enumerate(self.model.entries):
            if e.level and e.level not in st.levels:
                continue
            if st.pattern and not (st.pattern.search(e.message) or (e.extra and st.pattern.search(e.extra))):
                continue
            rows.append(i)
        self.model.set_rows(rows)
        self._update_status()
        # keep the selected entry (or its nearest neighbour) in view so clearing
        # a filter shows the context around it
        if keep_entry is not None and rows:
            self._select_row(min(bisect.bisect_left(rows, keep_entry), len(rows) - 1))
        else:
            self.detail.show_entry(None, None)

    def clear_filters(self):
        fb = self.filter_bar
        fb.search.blockSignals(True)
        fb.search.clear()
        fb.search.blockSignals(False)
        for btn in fb.level_boxes.values():
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
            btn._update_appearance()
        self.apply_filters()

    def _update_status(self):
        total, shown = len(self.model.entries), len(self.model.rows)
        self.status.setText(
            f"📁 {self.current_label}   |   📦 {len(self.chunks)} file   |   📊 Hiển thị {shown:,} / {total:,} entry"
            "   |   F8: ERROR · F7: WARN · Double-click dòng: Lọc theo Trace ID"
        )

    def eventFilter(self, obj, event):
        if obj is self.table.viewport() and event.type() == QEvent.Leave:
            self.delegate.set_hover_row(-1)
        return super().eventFilter(obj, event)

    # ---------- selection / navigation ----------
    def _current_entry_index(self) -> int | None:
        idx = self.table.currentIndex()
        return self.model.rows[idx.row()] if idx.isValid() and idx.row() < len(self.model.rows) else None

    def _select_row(self, row: int):
        idx = self.model.index(row, 0)
        self.table.selectionModel().setCurrentIndex(
            idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        self.table.scrollTo(idx, QAbstractItemView.PositionAtCenter)

    def _show_current(self, *_):
        idx = self.table.currentIndex()
        e = self.model.entry_at(idx.row()) if idx.isValid() else None
        self.detail.show_entry(e, VN_TZ)

    def _jump_level(self, level: str, step: int):
        rows = self.model.rows
        if not rows:
            return
        cur = self.table.currentIndex().row() if self.table.currentIndex().isValid() else (-1 if step > 0 else len(rows))
        r = cur + step
        while 0 <= r < len(rows):
            if self.model.entries[rows[r]].level == level:
                self._select_row(r)
                return
            r += step
        self.statusBar().showMessage(f"Không còn {level} nào {'phía sau' if step > 0 else 'phía trước'}", 3000)

    def _focus_search(self):
        if self.detail.has_entry() and not self.filter_bar.search.hasFocus():
            self.detail.open_search()
        else:
            self._focus_global_search()

    def _focus_global_search(self):
        self.filter_bar.search.setFocus()
        self.filter_bar.search.selectAll()

    def _filter_by_row_trace(self, index):
        e = self.model.entry_at(index.row())
        if e.trace_id:
            self.filter_bar.set_search(e.trace_id)

    def _context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        e = self.model.entry_at(index.row())
        menu = QMenu(self)
        if e.trace_id:
            menu.addAction(f"Lọc theo trace ID {e.trace_id}", lambda: self.filter_bar.set_search(e.trace_id))
        if e.thread:
            menu.addAction(f"Tìm theo thread [{e.thread}]", lambda: self.filter_bar.set_search(f"[{e.thread}]"))
        menu.addAction("Copy dòng log", lambda: QApplication.clipboard().setText(e.raw_text()))
        menu.addAction("Copy message", lambda: QApplication.clipboard().setText(e.message))
        menu.addSeparator()
        menu.addAction("Xoá tất cả bộ lọc", self.clear_filters)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ---------- export ----------
    def _ask_save(self, suffix: str) -> str | None:
        stem = re.sub(r'[\/:*?"<>|]+', "-", self.current_label) or "log"
        default = str(Path(self.last_dir) / f"{stem}{suffix}.log")
        path, _ = QFileDialog.getSaveFileName(self, "Lưu file", default, "Log (*.log *.txt)")
        return path or None

    def export_merged(self):
        if not self.chunks:
            return
        path = self._ask_save("_merged")
        if path:
            Path(path).write_text(merged_text(self.chunks), encoding="utf-8")
            self.statusBar().showMessage(f"Đã lưu {path}", 5000)

    def export_filtered(self):
        if not self.model.rows:
            return
        path = self._ask_save("_filtered")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                for i in self.model.rows:
                    f.write(self.model.entries[i].raw_text() + "\n")
            self.statusBar().showMessage(f"Đã lưu {len(self.model.rows):,} entry vào {path}", 5000)


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
