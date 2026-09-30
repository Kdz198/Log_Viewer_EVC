"""Saved days: every imported source is copied into the app data folder and listed
in library.json so it can be reopened later."""
import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

APP_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LogViewer"


@dataclass
class LibraryItem:
    id: str
    name: str
    date: str           # YYYY-MM-DD, used for sorting
    file: str           # file name inside the library folder
    original: str       # original file name
    sha1: str
    imported_at: str
    entries: int = 0
    errors: int = 0
    warns: int = 0


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class Library:
    def __init__(self, root: Path = APP_DIR / "library"):
        self.root = root
        self.files_dir = root / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = root / "library.json"
        self.items: list[LibraryItem] = []
        self._load()

    # ---------- persistence ----------
    def _load(self):
        if not self.index_path.exists():
            return
        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        known = {f.name for f in fields(LibraryItem)}
        self.items = [LibraryItem(**{k: v for k, v in d.items() if k in known}) for d in data.get("items", [])]

    def save(self):
        data = {"items": [asdict(i) for i in self.items]}
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    # ---------- items ----------
    def get(self, item_id: str) -> LibraryItem | None:
        return next((i for i in self.items if i.id == item_id), None)

    def path_of(self, item: LibraryItem) -> Path:
        return self.files_dir / item.file

    def import_source(self, source: Path, date: str, stats: dict) -> tuple[LibraryItem, bool]:
        """Copy `source` into the library. Returns (item, is_new); an identical file
        that was imported before is reused instead of stored twice."""
        item_id = uuid.uuid4().hex[:12]
        if source.is_dir():
            archive = shutil.make_archive(str(self.files_dir / item_id), "zip", source)
            stored = Path(archive)
            sha1 = file_sha1(stored)
        else:
            sha1 = file_sha1(source)
            existing = next((i for i in self.items if i.sha1 == sha1), None)
            if existing:
                return existing, False
            suffix = "".join(source.suffixes[-2:]) if source.name.lower().endswith(".tar.gz") else source.suffix
            stored = self.files_dir / f"{item_id}{suffix}"
            shutil.copy2(source, stored)

        name = self._default_name(date)
        item = LibraryItem(id=item_id, name=name, date=date, file=stored.name, original=source.name,
                           sha1=sha1, imported_at=datetime.now().isoformat(timespec="seconds"), **stats)
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

    def remove(self, item_ids: list[str]):
        for i in [i for i in self.items if i.id in item_ids]:
            self.path_of(i).unlink(missing_ok=True)
            self.items.remove(i)
        self.save()
