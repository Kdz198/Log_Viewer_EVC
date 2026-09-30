import bisect
import re
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QFrame, QHeaderView, QLabel,
                               QMainWindow, QMenu, QMessageBox, QSplitter, QTableView, QVBoxLayout,
                               QWidget)

from .. import __version__
from ..library import Library
from ..loader import HOUR_RE, load_source, merged_text
from ..models import LogTableModel
from ..parser import VN_TZ, LogEntry, parse_text
from .detail_panel import DetailPanel
from .filter_bar import FilterBar
from .library_panel import LibraryPanel
from .log_delegate import LogDelegate


class LoadWorker(QThread):
    progress = Signal(str)
    loaded = Signal(object, object)  # entries, chunks
    failed = Signal(str)

    def __init__(self, paths: list):
        super().__init__()
        self.paths = paths

    def run(self):
        try:
            chunks = []
            for path in self.paths:
                chunks += load_source(path, self.progress.emit)
            self.progress.emit("Đang phân tích log…")
            entries: list[LogEntry] = []
            for name, text in chunks:
                entries += parse_text(text, source=name)
            self.loaded.emit(entries, chunks)
        except Exception as ex:  # shown to the user, never crash the UI
            self.failed.emit(f"{type(ex).__name__}: {ex}")


def detect_date(chunks, entries: list[LogEntry]) -> str:
    """Day of a log bundle: from the hourly file names, else the most common VN date."""
    for name, _ in chunks:
        if m := HOUR_RE.search(name):
            return m.group(1)
    days = Counter(e.ts.astimezone(VN_TZ).date().isoformat() for e in entries if e.ts and e.ts.tzinfo)
    return days.most_common(1)[0][0] if days else ""


class MainWindow(QMainWindow):
    def __init__(self, library: Library | None = None):
        super().__init__()
        self.setWindowTitle(f"Log Viewer {__version__}")
        self.resize(1400, 850)
        self.setAcceptDrops(True)

        self.library = library or Library()
        self.current_label = ""
        self.last_dir = str(Path.home() / "Downloads")
        self.chunks: list = []
        self.worker: LoadWorker | None = None
        self._import_from: Path | None = None
        self._loading_ids: list[str] = []
        self._queued: tuple | None = None

        self.model = LogTableModel(self)
        self.filter_bar = FilterBar()
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
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.delegate = LogDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.table.entered.connect(lambda idx: self.delegate.set_hover_row(idx.row()))
        self.table.viewport().installEventFilter(self)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setHighlightSections(False)
        hh.resizeSection(0, 175)
        hh.resizeSection(1, 80)
        hh.setStretchLastSection(True)
        self.table.setStyleSheet(
            "QHeaderView::section { padding: 6px 10px; border: none;"
            " border-bottom: 1px solid palette(mid); background: palette(window); font-weight: 600; }")
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._filter_by_row_trace)
        self.table.selectionModel().currentRowChanged.connect(self._show_current)

        self.detail = DetailPanel()
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.detail)
        splitter.setSizes([560, 260])

        self.empty_hint = QLabel("Kéo thả file .zip / .tar.gz / .log vào đây, hoặc Ctrl+O để mở\n"
                                 "Các ngày đã mở sẽ được lưu ở cột bên trái")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setStyleSheet("font-size: 16px; color: gray; padding: 40px;")

        viewer = QWidget()
        lay = QVBoxLayout(viewer)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.filter_bar)
        lay.addWidget(self.empty_hint)
        lay.addWidget(splitter, 1)

        self.library_panel = LibraryPanel(self.library)
        self.library_panel.open_items.connect(self.open_items)
        self.library_panel.removed.connect(self._on_library_removed)
        main_split = QSplitter(Qt.Horizontal)
        main_split.addWidget(self.library_panel)
        main_split.addWidget(viewer)
        main_split.setStretchFactor(1, 1)
        main_split.setSizes([240, 1160])
        self.setCentralWidget(main_split)

        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)

        self.filter_bar.changed.connect(self.apply_filters)
        self.model.tz = VN_TZ
        self._build_menu()

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
        act(m, "Mở file…", self.open_dialog, "Ctrl+O")
        act(m, "Mở thư mục…", self.open_folder_dialog, "Ctrl+Shift+O")
        m.addSeparator()
        act(m, "Xuất log gộp cả ngày…", self.export_merged, "Ctrl+S")
        act(m, "Xuất các dòng đang lọc…", self.export_filtered, "Ctrl+Shift+S")
        m.addSeparator()
        act(m, "Thoát", self.close, "Ctrl+Q")

        m = self.menuBar().addMenu("&Xem")
        act(m, "Tìm kiếm", self._focus_search, "Ctrl+F")
        act(m, "ERROR tiếp theo", lambda: self._jump_level("ERROR", +1), "F8")
        act(m, "ERROR trước đó", lambda: self._jump_level("ERROR", -1), "Shift+F8")
        act(m, "WARN tiếp theo", lambda: self._jump_level("WARN", +1), "F7")
        act(m, "WARN trước đó", lambda: self._jump_level("WARN", -1), "Shift+F7")
        act(m, "Xoá tất cả bộ lọc", self.clear_filters, "Ctrl+R")

    # ---------- loading ----------
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
                    ids: list[str] | None = None):
        if self.worker and self.worker.isRunning():
            self._queued = (paths, label, import_from, ids)  # latest request wins
            return
        self._pending_label = label
        self._import_from = import_from
        self._loading_ids = ids or []
        self.status.setText(f"Đang mở {label}…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.worker = LoadWorker([str(p) for p in paths])
        self.worker.progress.connect(self.status.setText)
        self.worker.loaded.connect(self._on_loaded)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_loaded(self, entries: list[LogEntry], chunks):
        self.chunks = chunks
        self.current_label = self._pending_label
        ids = self._loading_ids
        if self._import_from is not None:
            ids = self._save_to_library(self._import_from, chunks, entries) or ids
        elif len(ids) == 1:
            self._refresh_stats(ids[0], entries)
        self.library_panel.set_current(ids)
        self.empty_hint.hide()
        self.setWindowTitle(f"{self.current_label} — Log Viewer {__version__}")
        self.model.set_entries(entries)
        self.filter_bar.set_counts(Counter(e.level for e in entries))
        self.apply_filters()
        self.detail.show_entry(None, None)

    def _save_to_library(self, source: Path, chunks, entries) -> list[str] | None:
        levels = Counter(e.level for e in entries)
        stats = {"entries": len(entries), "errors": levels["ERROR"], "warns": levels["WARN"]}
        try:
            item, is_new = self.library.import_source(source, detect_date(chunks, entries), stats)
        except OSError as ex:
            QMessageBox.warning(self, "Không lưu được", f"Không lưu được vào danh sách:\n{ex}")
            return None
        self.current_label = item.name
        self.library_panel.refresh()
        self.statusBar().showMessage(
            f"Đã lưu “{item.name}” vào danh sách" if is_new else f"File này đã có sẵn: “{item.name}”", 5000)
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
        self.library_panel.set_current(list(self.library_panel.current_ids - set(ids)))

    def _on_worker_finished(self):
        QApplication.restoreOverrideCursor()
        if self._queued:
            queued, self._queued = self._queued, None
            self._start_load(*queued)

    def _on_failed(self, msg: str):
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
        for cb in fb.level_boxes.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self.apply_filters()

    def _update_status(self):
        total, shown = len(self.model.entries), len(self.model.rows)
        self.status.setText(f"{self.current_label}  |  {len(self.chunks)} file  |  Hiển thị {shown:,} / {total:,} entry"
                            "  |  F8: ERROR kế tiếp · F7: WARN kế tiếp · double-click: tìm theo trace ID")

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
