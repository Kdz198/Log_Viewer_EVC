"""Saved days: every imported or downloaded source is copied into the configured
storage folder and listed in library.json so it can be reopened or managed later."""
import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

APP_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LogViewer"
DEFAULT_LIBRARY_DIR = APP_DIR / "library"
SETTINGS_PATH = APP_DIR / "settings.json"


def get_configured_storage_dir() -> Path:
    if SETTINGS_PATH.is_file():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if custom := data.get("storage_dir"):
                return Path(custom)
        except (OSError, ValueError):
            pass
    return DEFAULT_LIBRARY_DIR


def save_configured_storage_dir(path: Path):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if SETTINGS_PATH.is_file():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    data["storage_dir"] = str(path.resolve())
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class LibraryItem:
    id: str
    name: str
    date: str           # YYYY-MM-DD, used for sorting
    file: str           # file name inside the storage folder
    original: str       # original file name
    sha1: str
    imported_at: str
    entries: int = 0
    errors: int = 0
    warns: int = 0
    source_path: str = ""  # original external path if imported from disk


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _safe_stem(name: str) -> str:
    stem = re.sub(r'(\.tar\.gz|\.tgz|\.gz|\.zip|\.log|\.txt)$', '', name, flags=re.IGNORECASE)
    stem = re.sub(r'[^A-Za-z0-9._-]+', '_', stem).strip('_')
    return stem[:60] or "log"


class Library:
    def __init__(self, root: Path | None = None):
        self.root = (root or get_configured_storage_dir()).resolve()
        self.files_dir = self.root / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "library.json"
        self.items: list[LibraryItem] = []
        self._load()

    # ---------- persistence ----------
    def _load(self):
        self.items = []
        if not self.index_path.exists():
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            known = {f.name for f in fields(LibraryItem)}
            self.items = [LibraryItem(**{k: v for k, v in d.items() if k in known}) for d in data.get("items", [])]
        except (OSError, ValueError):
            self.items = []

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        data = {"items": [asdict(i) for i in self.items]}
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    # ---------- storage directory migration ----------
    def change_storage_dir(self, new_root: Path) -> int:
        """Change storage directory and copy all existing log files to the new location.
        Returns the number of log files copied."""
        new_root = new_root.resolve()
        if new_root == self.root:
            save_configured_storage_dir(new_root)
            return 0

        new_files_dir = new_root / "files"
        new_files_dir.mkdir(parents=True, exist_ok=True)

        # If target directory already has a library.json, load its items so we don't lose them
        existing_target_items: list[LibraryItem] = []
        target_index = new_root / "library.json"
        if target_index.is_file():
            try:
                data = json.loads(target_index.read_text(encoding="utf-8"))
                known = {f.name for f in fields(LibraryItem)}
                existing_target_items = [
                    LibraryItem(**{k: v for k, v in d.items() if k in known})
                    for d in data.get("items", [])
                ]
            except (OSError, ValueError):
                pass

        copied = 0
        for item in self.items:
            old_path = self.path_of(item)
            new_path = new_files_dir / item.file
            if old_path.is_file() and old_path.resolve() != new_path.resolve():
                shutil.copy2(old_path, new_path)
                copied += 1

        # Merge any items that already existed in new_root
        known_shas = {i.sha1 for i in self.items if i.sha1}
        for ext_item in existing_target_items:
            if ext_item.sha1 not in known_shas and (new_files_dir / ext_item.file).is_file():
                self.items.append(ext_item)
                known_shas.add(ext_item.sha1)

        self.root = new_root
        self.files_dir = new_files_dir
        self.index_path = target_index
        self.save()
        save_configured_storage_dir(new_root)
        return copied

    # ---------- items ----------
    def get(self, item_id: str) -> LibraryItem | None:
        return next((i for i in self.items if i.id == item_id), None)

    def path_of(self, item: LibraryItem) -> Path:
        p = self.files_dir / item.file
        if p.exists():
            return p
        alt = self.root / item.file
        if alt.exists():
            return alt
        return p

    def import_source(self, source: Path, date: str, stats: dict) -> tuple[LibraryItem, bool]:
        """Copy `source` into the configured storage folder. Returns (item, is_new);
        an identical file that was imported before is reused instead of stored twice."""
        source = Path(source).resolve()
        self.files_dir.mkdir(parents=True, exist_ok=True)
        item_id = uuid.uuid4().hex[:8]
        ext_source_path = ""

        if source.is_dir():
            prefix = f"{date}_" if date else ""
            base_name = f"{prefix}{_safe_stem(source.name)}_{item_id}"
            archive = shutil.make_archive(str(self.files_dir / base_name), "zip", source)
            stored = Path(archive)
            sha1 = file_sha1(stored)
        else:
            sha1 = file_sha1(source)
            existing = next((i for i in self.items if i.sha1 == sha1), None)
            if existing:
                # Ensure the file copy exists in the current storage folder
                stored_existing = self.path_of(existing)
                if not stored_existing.is_file() and source.is_file():
                    shutil.copy2(source, stored_existing)
                return existing, False

            suffix = "".join(source.suffixes[-2:]) if source.name.lower().endswith(".tar.gz") else source.suffix
            stem = _safe_stem(source.name)
            prefix = f"{date}_" if date and date not in stem else ""
            target_name = f"{prefix}{stem}_{item_id}{suffix}"
            stored = self.files_dir / target_name

            if source.parent == self.files_dir:
                # File was downloaded directly into files_dir: rename cleanly in-place
                if source != stored:
                    source.replace(stored)
            else:
                # File imported from outside: copy into storage folder and record original path
                shutil.copy2(source, stored)
                ext_source_path = str(source)

        name = self._default_name(date)
        item = LibraryItem(
            id=item_id,
            name=name,
            date=date,
            file=stored.name,
            original=source.name,
            sha1=sha1,
            imported_at=datetime.now().isoformat(timespec="seconds"),
            source_path=ext_source_path,
            **stats,
        )
        self.items.append(item)
        self.save()
        return item, True

    def _default_name(self, date: str) -> str:
        try:
            base = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            base = date or "Không rõ ngày"
        names = {i.name for i in self.items}
        name, n = base, 2
        while name in names:
            name, n = f"{base} ({n})", n + 1
        return name

    def rename(self, item_id: str, name: str):
        if item := self.get(item_id):
            item.name = name
            self.save()

    def remove(self, item_ids: list[str], delete_files: bool = True, delete_original: bool = False):
        """Remove items from the library.
        - delete_files=True: permanently delete the stored file in storage folder (hard delete).
        - delete_original=True: also delete the external source file if it was imported from outside.
        """
        for i in [i for i in self.items if i.id in item_ids]:
            if delete_files:
                self.path_of(i).unlink(missing_ok=True)
            if delete_original and i.source_path:
                try:
                    ext = Path(i.source_path)
                    if ext.is_file():
                        ext.unlink(missing_ok=True)
                except OSError:
                    pass
            self.items.remove(i)
        self.save()
