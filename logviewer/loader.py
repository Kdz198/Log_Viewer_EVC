"""Read a log bundle (zip of hourly .tar.gz, a single archive, a folder or a plain file)
and return its text chunks in chronological order."""
import gzip
import io
import re
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

# accountant_logs_2026-09-29_13-00.tar.gz -> date + hour + minute
HOUR_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[_T ](\d{2})-(\d{2})")
# Rolled-over files inside an hourly archive, e.g. accountant-service.log.2026-09-29.0.gz
# (logback: .0 is older than .1) or app.log.2 (log4j: .2 is older than .1). They hold
# the start of that hour, so they come before the live app.log.
ROLLED_DATED_RE = re.compile(r"\.(\d{4}-\d{2}-\d{2})\.(\d+)(?:\.gz)?$")
ROLLED_NUM_RE = re.compile(r"\.log\.(\d+)(?:\.gz)?$")

GZIP_MAGIC = bytes([0x1F, 0x8B])
LOG_EXTS = (".tar.gz", ".tgz", ".tar", ".gz", ".log", ".txt", ".out")

Chunk = tuple[str, str]  # (source name, text)
Progress = Callable[[str], None]


def _hour_key(name: str):
    m = HOUR_RE.search(name)
    return (0, m.groups(), name) if m else (1, (), name)


def _rotation_key(name: str):
    if m := ROLLED_DATED_RE.search(name):
        return (0, m.group(1), int(m.group(2)), name)
    if m := ROLLED_NUM_RE.search(name):
        return (0, "", -int(m.group(1)), name)
    return (1, "", 0, name)


def _decode(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode("utf-8", errors="replace")


def _read_archive(data: bytes, label: str) -> list[Chunk]:
    """A .tar.gz / .tar / plain .gz blob -> text chunks."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
            members = [m for m in tf.getmembers() if m.isfile() and m.size > 0]
            members.sort(key=lambda m: _rotation_key(m.name))
            chunks = []
            for m in members:
                f = tf.extractfile(m)
                if f is None:
                    continue
                raw = f.read()
                if raw[:2] == GZIP_MAGIC:  # rolled-over file, gzipped inside the tar
                    raw = gzip.decompress(raw)
                if raw.strip():
                    chunks.append((f"{label}/{m.name.removeprefix('./')}", _decode(raw)))
            return chunks
    except tarfile.ReadError:
        if data[:2] == b"\x1f\x8b":  # gzip but not tar
            return [(label, _decode(gzip.decompress(data)))]
        return [(label, _decode(data))]


def _read_blob(name: str, data: bytes) -> list[Chunk]:
    low = name.lower()
    if low.endswith((".tar.gz", ".tgz", ".tar", ".gz")):
        return _read_archive(data, Path(name).name)
    return [(Path(name).name, _decode(data))]


def load_source(path: str | Path, progress: Progress = lambda _: None) -> list[Chunk]:
    path = Path(path)
    chunks: list[Chunk] = []

    if path.is_dir():
        files = sorted((p for p in path.rglob("*") if p.is_file() and p.name.lower().endswith(LOG_EXTS)),
                       key=lambda p: _hour_key(p.name))
        for i, p in enumerate(files, 1):
            progress(f"Đang đọc {p.name} ({i}/{len(files)})")
            chunks += _read_blob(p.name, p.read_bytes())

    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = sorted((n for n in zf.namelist() if not n.endswith("/") and n.lower().endswith(LOG_EXTS)),
                           key=lambda n: _hour_key(Path(n).name))
            for i, n in enumerate(names, 1):
                progress(f"Đang giải nén {Path(n).name} ({i}/{len(names)})")
                chunks += _read_blob(n, zf.read(n))

    else:
        progress(f"Đang đọc {path.name}")
        chunks += _read_blob(path.name, path.read_bytes())

    # the same rolled-over file can be shipped again in the next hour's archive
    seen, unique = set(), []
    for name, text in chunks:
        key = (Path(name).name, hash(text))
        if key not in seen:
            seen.add(key)
            unique.append((name, text))
    chunks = unique

    if not chunks:
        raise ValueError("Không tìm thấy file log nào trong nguồn đã chọn.")
    return chunks


def merged_text(chunks: list[Chunk]) -> str:
    return "".join(t if t.endswith("\n") else t + "\n" for _, t in chunks)
