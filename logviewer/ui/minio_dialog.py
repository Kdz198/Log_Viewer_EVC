"""Dialog to browse and download daily log packages from MinIO Console, plus configure storage folder."""
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

try:
    from ..library import Library
    from ..minio_client import (MinioConfig, MinioConsoleClient, MinioItem, load_minio_config,
                                save_minio_config)
    from .loading_overlay import LoadingOverlay
except (ImportError, ValueError):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from logviewer.library import Library
    from logviewer.minio_client import (MinioConfig, MinioConsoleClient, MinioItem, load_minio_config,
                                        save_minio_config)
    from logviewer.ui.loading_overlay import LoadingOverlay

SAVED_COLOR = QColor("#16a34a")
_ACTIVE_WORKERS: set[QThread] = set()


def _keep_worker_alive(worker: QThread):
    _ACTIVE_WORKERS.add(worker)
    worker.finished.connect(lambda: _ACTIVE_WORKERS.discard(worker))


def open_in_explorer(path: Path):
    path = path.resolve()
    if sys.platform == "win32":
        if path.is_file():
            subprocess.Popen(["explorer", f"/select,{path}"])
        else:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))


class MinioListWorker(QThread):
    loaded = Signal(list, list, str)  # buckets, items, active_bucket
    failed = Signal(str)

    def __init__(self, cfg: MinioConfig, bucket_override: str = ""):
        super().__init__()
        self.cfg = cfg
        self.bucket_override = bucket_override

    def run(self):
        try:
            base_url, default_bucket = self.cfg.base_url_and_bucket()
            target_bucket = self.bucket_override or default_bucket
            client = MinioConsoleClient(base_url)
            client.login(self.cfg.username, self.cfg.password)
            buckets = client.list_buckets(fallback_bucket=target_bucket)
            items = client.list_objects(target_bucket)
            self.loaded.emit(buckets, items, target_bucket)
        except Exception as ex:
            self.failed.emit(str(ex))


class MinioDownloadWorker(QThread):
    progress = Signal(str)
    finished_files = Signal(list)  # list[Path]
    failed = Signal(str)

    def __init__(self, cfg: MinioConfig, bucket: str, prefixes: list[str], dest_dir: Path):
        super().__init__()
        self.cfg = cfg
        self.bucket = bucket
        self.prefixes = prefixes
        self.dest_dir = dest_dir

    def run(self):
        try:
            base_url, _ = self.cfg.base_url_and_bucket()
            client = MinioConsoleClient(base_url)
            self.progress.emit("Đang đăng nhập MinIO…")
            client.login(self.cfg.username, self.cfg.password)

            self.dest_dir.mkdir(parents=True, exist_ok=True)
            paths: list[Path] = []
            for idx, prefix in enumerate(self.prefixes, 1):
                clean = prefix.rstrip("/").split("/")[-1] or "logs"
                ext = "" if clean.lower().endswith((".zip", ".tar.gz", ".tgz", ".gz", ".log")) else ".zip"
                dest = self.dest_dir / f"{self.bucket}_{clean}{ext}"

                def _cb(msg: str, i=idx, n=len(self.prefixes)):
                    prefix_str = f"[{i}/{n}] " if n > 1 else ""
                    self.progress.emit(prefix_str + msg)

                _cb(f"Đang tải {clean} từ MinIO…")
                client.download_item(self.bucket, prefix, dest, _cb)
                paths.append(dest)

            self.finished_files.emit(paths)
        except Exception as ex:
            self.failed.emit(str(ex))


class MinioDialog(QDialog):
    files_downloaded = Signal(list)   # list[str] paths to downloaded zip/archive files
    storage_changed = Signal()        # emitted when storage folder or items change

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tải log từ MinIO Console & Cấu hình nơi lưu")
        self.resize(740, 660)
        self.library = library
        self.cfg = load_minio_config()
        self._items: list[MinioItem] = []
        self._list_worker: MinioListWorker | None = None
        self._dl_worker: MinioDownloadWorker | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # --- Connection & Storage Group ---
        conn_group = QGroupBox("Cấu hình kết nối MinIO && Thư mục lưu log")
        form = QFormLayout(conn_group)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(8)

        self.url_edit = QLineEdit(self.cfg.url)
        self.url_edit.setPlaceholderText("https://prod-minio.evtruyxuatnguongoc.vn/browser/accounting-file-logs")

        cred_row = QHBoxLayout()
        self.user_edit = QLineEdit(self.cfg.username)
        self.user_edit.setPlaceholderText("Username (MINIO_USERNAME)")
        self.pass_edit = QLineEdit(self.cfg.password)
        self.pass_edit.setPlaceholderText("Password (MINIO_PASSWORD)")
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.remember_cb = QCheckBox("Lưu tài khoản")
        self.remember_cb.setChecked(True)
        self.connect_btn = QPushButton("Kết nối && Lấy danh sách")
        self.connect_btn.setStyleSheet("font-weight: 600; padding: 4px 12px;")

        cred_row.addWidget(QLabel("User:"))
        cred_row.addWidget(self.user_edit, 1)
        cred_row.addWidget(QLabel("Pass:"))
        cred_row.addWidget(self.pass_edit, 1)
        cred_row.addWidget(self.remember_cb)
        cred_row.addWidget(self.connect_btn)

        storage_row = QHBoxLayout()
        self.storage_edit = QLineEdit(str(self.library.root))
        self.storage_edit.setReadOnly(True)
        self.storage_edit.setToolTip(
            "Mọi file tải từ MinIO hoặc import từ ngoài đều được lưu bản copy tại thư mục này.\n"
            "Khi đổi thư mục lưu, app sẽ tự động copy toàn bộ log đã lưu sang thư mục mới."
        )
        choose_dir_btn = QPushButton("📁 Chọn chỗ lưu…")
        choose_dir_btn.setToolTip("Đổi thư mục lưu log (tự động copy các log hiện có sang chỗ mới)")
        open_dir_btn = QPushButton("Mở thư mục")
        open_dir_btn.setToolTip("Mở thư mục lưu log trong Windows Explorer")
        storage_row.addWidget(self.storage_edit, 1)
        storage_row.addWidget(choose_dir_btn)
        storage_row.addWidget(open_dir_btn)

        form.addRow("MinIO URL:", self.url_edit)
        form.addRow("Tài khoản:", cred_row)
        form.addRow("Nơi lưu log:", storage_row)
        lay.addWidget(conn_group)

        # --- Bucket & Filter Bar ---
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Package / Bucket:"))
        self.bucket_combo = QComboBox()
        self.bucket_combo.setEditable(True)
        self.bucket_combo.setMinimumWidth(220)
        _, default_bucket = self.cfg.base_url_and_bucket()
        self.bucket_combo.addItem(default_bucket)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Lọc nhanh ngày (ví dụ: 2026-07-25)…")
        self.search_edit.setClearButtonEnabled(True)

        filter_row.addWidget(self.bucket_combo)
        filter_row.addSpacing(8)
        filter_row.addWidget(self.search_edit, 1)
        lay.addLayout(filter_row)

        # --- Days / Packages Tree ---
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Ngày / Gói log trên MinIO", "Trạng thái trên máy"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.itemChanged.connect(self._update_buttons)
        lay.addWidget(self.tree, 1)

        # --- Footer Status & Buttons ---
        footer = QHBoxLayout()
        self.status_label = QLabel("Nhập tài khoản hoặc cấu hình .env rồi bấm 'Kết nối & Lấy danh sách'.")
        self.status_label.setStyleSheet("color: gray;")
        self.delete_local_btn = QPushButton("🗑 Xoá cứng bản đã lưu")
        self.delete_local_btn.setToolTip("Xoá vĩnh viễn file log của ngày đang chọn khỏi ổ cứng")
        self.delete_local_btn.setEnabled(False)
        self.download_btn = QPushButton("⬇ Tải về && Mở ngày đã chọn")
        self.download_btn.setStyleSheet("font-weight: 600; padding: 6px 16px;")
        self.download_btn.setEnabled(False)
        close_btn = QPushButton("Đóng")

        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.delete_local_btn)
        footer.addWidget(self.download_btn)
        footer.addWidget(close_btn)
        lay.addLayout(footer)

        # --- Signals ---
        choose_dir_btn.clicked.connect(self._choose_storage_dir)
        open_dir_btn.clicked.connect(self._open_storage_dir)
        self.connect_btn.clicked.connect(self.fetch_list)
        self.bucket_combo.activated.connect(self._on_bucket_activated)
        self.search_edit.textChanged.connect(self._populate_tree)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        self.delete_local_btn.clicked.connect(self._hard_delete_selected_dates)
        self.download_btn.clicked.connect(self.download_selected)
        close_btn.clicked.connect(self.reject)

        self.loading_overlay = LoadingOverlay(self)

        # Auto-connect if credentials are already configured in .env or saved config
        if self.cfg.username and self.cfg.password:
            self.fetch_list()
        elif not self.cfg.username:
            self.user_edit.setFocus()
        else:
            self.pass_edit.setFocus()

    def _open_storage_dir(self):
        open_in_explorer(self.library.files_dir)

    def _on_bucket_activated(self, _index: int):
        self.fetch_list(use_combo_bucket=True)

    def _choose_storage_dir(self):
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
        self.storage_edit.setText(str(self.library.root))
        self._populate_tree()
        self.storage_changed.emit()
        QMessageBox.information(
            self,
            "Đã đổi nơi lưu log",
            f"Đã chuyển thư mục lưu log sang:\n{self.library.root}\n\n"
            f"Đã tự động copy {copied} file log từ thư mục cũ sang thư mục mới."
        )

    def _collect_config(self) -> MinioConfig:
        url = self.url_edit.text().strip()
        cfg = MinioConfig(
            url=url,
            bucket=self.bucket_combo.currentText().strip(),
            username=self.user_edit.text().strip(),
            password=self.pass_edit.text(),
        )
        save_minio_config(cfg, save_password=self.remember_cb.isChecked())
        self.cfg = cfg
        return cfg

    def fetch_list(self, use_combo_bucket: bool = False):
        if self._list_worker and self._list_worker.isRunning():
            return
        cfg = self._collect_config()
        if not cfg.username or not cfg.password:
            QMessageBox.information(self, "Thiếu thông tin",
                                    "Vui lòng nhập Username và Password MinIO (hoặc điền trong file .env).")
            return

        _, url_bucket = cfg.base_url_and_bucket()
        target_bucket = self.bucket_combo.currentText().strip() if use_combo_bucket else url_bucket

        self.connect_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.status_label.setText(f"Đang kết nối MinIO và tải danh sách từ '{target_bucket}'…")
        self.loading_overlay.start("Đang kết nối MinIO…", f"Đang lấy danh sách ngày từ '{target_bucket}'…")
        self._list_worker = MinioListWorker(cfg, bucket_override=target_bucket)
        _keep_worker_alive(self._list_worker)
        self._list_worker.loaded.connect(self._on_list_loaded)
        self._list_worker.failed.connect(self._on_list_failed)
        self._list_worker.finished.connect(self._on_list_finished)
        self._list_worker.start()

    def _on_list_finished(self):
        self.loading_overlay.stop()
        self.connect_btn.setEnabled(True)

    def _on_list_loaded(self, buckets: list[str], items: list[MinioItem], active_bucket: str):
        self.loading_overlay.stop()
        self.bucket_combo.blockSignals(True)
        self.bucket_combo.clear()
        for b in buckets:
            self.bucket_combo.addItem(b)
        self.bucket_combo.setCurrentText(active_bucket)
        self.bucket_combo.blockSignals(False)

        self._items = items
        self._populate_tree()
        self.status_label.setText(
            f"Đã tải {len(items)} mục từ '{active_bucket}'. Double-click 1 ngày hoặc tick chọn để tải về."
        )

    def _on_list_failed(self, err: str):
        self.loading_overlay.stop()
        self.status_label.setText("Lỗi kết nối MinIO")
        QMessageBox.warning(self, "Không lấy được danh sách MinIO", err)

    def _populate_tree(self):
        filt = self.search_edit.text().strip().lower()
        saved_dates = {it.date for it in self.library.items if it.date}

        self.tree.blockSignals(True)
        self.tree.clear()
        for item in self._items:
            disp = item.display_name
            if filt and filt not in disp.lower():
                continue
            icon = "📁 " if item.is_folder else "📄 "
            is_saved = disp in saved_dates
            status = "✓ Đã có trên máy" if is_saved else ""
            node = QTreeWidgetItem([f"{icon}{disp}", status])
            node.setData(0, Qt.UserRole, item.name)
            node.setData(0, Qt.UserRole + 1, disp)
            node.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            node.setCheckState(0, Qt.Unchecked)
            if is_saved:
                node.setForeground(1, SAVED_COLOR)
            self.tree.addTopLevelItem(node)
        self.tree.blockSignals(False)
        self._update_buttons()

    def _selected_prefixes(self) -> list[str]:
        checked = []
        for i in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(i)
            if node.checkState(0) == Qt.Checked:
                checked.append(node.data(0, Qt.UserRole))
        if checked:
            return checked
        cur = self.tree.currentItem()
        return [cur.data(0, Qt.UserRole)] if cur else []

    def _selected_saved_items(self):
        prefixes = self._selected_prefixes()
        dates = {p.rstrip("/").split("/")[-1] for p in prefixes}
        return [it for it in self.library.items if it.date in dates]

    def _update_buttons(self, *_):
        if self._dl_worker and self._dl_worker.isRunning():
            self.download_btn.setEnabled(False)
            self.delete_local_btn.setEnabled(False)
            return
        sel = self._selected_prefixes()
        self.download_btn.setEnabled(bool(sel))
        self.delete_local_btn.setEnabled(bool(self._selected_saved_items()))
        if len(sel) > 1:
            self.download_btn.setText(f"⬇ Tải về && Mở ({len(sel)} ngày)")
        else:
            self.download_btn.setText("⬇ Tải về && Mở ngày đã chọn")

    def _context_menu(self, pos):
        node = self.tree.itemAt(pos)
        if node is None:
            return
        prefix = node.data(0, Qt.UserRole)
        disp = node.data(0, Qt.UserRole + 1)
        saved = [it for it in self.library.items if it.date == disp]
        menu = QMenu(self)
        menu.addAction(f"⬇ Tải về & Mở ({disp})", lambda: self._start_download([prefix]))
        if saved:
            menu.addAction("Mở vị trí file đã lưu", lambda: open_in_explorer(self.library.path_of(saved[0])))
            menu.addSeparator()
            menu.addAction(
                f"🗑 Xoá cứng file đã lưu của ngày {disp}",
                lambda: self._confirm_hard_delete(saved),
            )
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _hard_delete_selected_dates(self):
        saved = self._selected_saved_items()
        if saved:
            self._confirm_hard_delete(saved)

    def _confirm_hard_delete(self, items):
        files_text = "\n".join(f"• {self.library.path_of(i)}" for i in items[:5])
        if len(items) > 5:
            files_text += f"\n… và {len(items) - 5} file khác"
        ans = QMessageBox.warning(
            self,
            "Xoá cứng file log",
            f"Bạn có chắc muốn XOÁ VĨNH VIỄN {len(items)} file log khỏi ổ cứng?\n\n{files_text}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            self.library.remove([i.id for i in items], delete_files=True, delete_original=True)
            self._populate_tree()
            self.storage_changed.emit()
            self.status_label.setText(f"Đã xoá cứng {len(items)} file log khỏi máy.")

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        if self._dl_worker and self._dl_worker.isRunning():
            return
        prefix = item.data(0, Qt.UserRole)
        if prefix:
            self._start_download([prefix])

    def download_selected(self):
        prefixes = self._selected_prefixes()
        if prefixes:
            self._start_download(prefixes)

    def _start_download(self, prefixes: list[str]):
        cfg = self._collect_config()
        bucket = self.bucket_combo.currentText().strip() or cfg.bucket
        self.download_btn.setEnabled(False)
        self.delete_local_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.tree.setEnabled(False)
        self.loading_overlay.start("Đang tải gói log từ MinIO…", "Đang khởi tạo kết nối…")

        self._dl_worker = MinioDownloadWorker(cfg, bucket, prefixes, self.library.files_dir)
        _keep_worker_alive(self._dl_worker)
        self._dl_worker.progress.connect(self._on_download_progress)
        self._dl_worker.finished_files.connect(self._on_downloaded)
        self._dl_worker.failed.connect(self._on_download_failed)
        self._dl_worker.start()

    def _on_download_progress(self, msg: str):
        self.status_label.setText(msg)
        self.loading_overlay.set_status(msg)

    def _on_downloaded(self, paths: list[Path]):
        self.loading_overlay.stop()
        self.tree.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self._update_buttons()
        self.files_downloaded.emit([str(p) for p in paths])
        self.accept()

    def _on_download_failed(self, err: str):
        self.loading_overlay.stop()
        self.tree.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self._update_buttons()
        self.status_label.setText("Tải file thất bại")
        QMessageBox.critical(self, "Lỗi khi tải từ MinIO", err)

    def done(self, result: int):
        self.loading_overlay.stop()
        for w in (self._list_worker, self._dl_worker):
            if w and w.isRunning():
                w.blockSignals(True)
                w.wait(3000)
        super().done(result)

