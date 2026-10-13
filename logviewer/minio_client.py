"""MinIO Console client (REST API) and configuration loader (.env + local settings)."""
import base64
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

try:
    from .library import APP_DIR
except (ImportError, ValueError):
    # Allow running directly: python logviewer/minio_client.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from logviewer.library import APP_DIR

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_MINIO_URL = "https://prod-minio.evtruyxuatnguongoc.vn/browser/accounting-file-logs"
DEFAULT_BUCKET = "accounting-file-logs"
CONFIG_PATH = APP_DIR / "minio_config.json"


@dataclass
class MinioConfig:
    url: str = DEFAULT_MINIO_URL
    bucket: str = DEFAULT_BUCKET
    username: str = ""
    password: str = ""

    def base_url_and_bucket(self) -> tuple[str, str]:
        raw = (self.url or DEFAULT_MINIO_URL).strip()
        if "://" not in raw:
            raw = "https://" + raw
        parsed = urllib.parse.urlsplit(raw)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        bucket = self.bucket.strip()
        # Extract bucket from /browser/<bucket>[/<prefix>] if present in URL
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) >= 2 and path_parts[0] == "browser":
            url_bucket = urllib.parse.unquote(path_parts[1])
            if not bucket or bucket == DEFAULT_BUCKET:
                bucket = url_bucket
        return base_url, (bucket or DEFAULT_BUCKET)


@dataclass
class MinioItem:
    name: str          # e.g. "2026-07-15/" or "accountant_logs_2026-07-15.tar.gz"
    size: int = 0
    last_modified: str = ""

    @property
    def is_folder(self) -> bool:
        return self.name.endswith("/")

    @property
    def display_name(self) -> str:
        return self.name.rstrip("/").split("/")[-1]


def _candidate_env_paths() -> list[Path]:
    paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        APP_DIR / ".env",
    ]
    if getattr(sys, "frozen", False):
        paths.insert(0, Path(sys.executable).resolve().parent / ".env")
    return paths


def _read_dotenv() -> dict[str, str]:
    env_vars: dict[str, str] = {}
    for p in _candidate_env_paths():
        if p.is_file():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k and k not in env_vars:
                        env_vars[k] = v
            except OSError:
                pass
    return env_vars


def load_minio_config() -> MinioConfig:
    cfg = MinioConfig()
    # 1. Load saved UI config if present
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.url = data.get("url") or cfg.url
            cfg.bucket = data.get("bucket") or cfg.bucket
            cfg.username = data.get("username") or cfg.username
            cfg.password = data.get("password") or cfg.password
        except (OSError, ValueError):
            pass

    # 2. Override with .env / OS environment variables if non-empty
    dotenv = _read_dotenv()

    def get_env(*keys: str) -> str:
        for k in keys:
            val = os.environ.get(k) or dotenv.get(k)
            if val:
                return val.strip()
        return ""

    if env_url := get_env("MINIO_URL", "MINIO_ENDPOINT"):
        cfg.url = env_url
    if env_bucket := get_env("MINIO_BUCKET"):
        cfg.bucket = env_bucket
    if env_user := get_env("MINIO_USERNAME", "MINIO_USER", "MINIO_ACCESS_KEY"):
        cfg.username = env_user
    if env_pass := get_env("MINIO_PASSWORD", "MINIO_PASS", "MINIO_SECRET_KEY"):
        cfg.password = env_pass

    _, cfg.bucket = cfg.base_url_and_bucket()
    return cfg


def save_minio_config(cfg: MinioConfig, save_password: bool = True):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(cfg)
    if not save_password:
        data["password"] = ""
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class MinioConsoleClient:
    """Interact with MinIO Console REST API (/api/v1/login, /objects, /objects/download)."""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cookies = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPSHandler(context=ctx),
        )

    def _request(self, path: str, method: str = "GET", body: object = None, timeout: int | None = None):
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "LogViewer-MinIOClient/1.0",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            return self.opener.open(req, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as e:
            msg = ""
            try:
                err_json = json.loads(e.read().decode("utf-8", errors="replace"))
                msg = err_json.get("detailedMessage") or err_json.get("message") or ""
            except Exception:
                pass
            if e.code in (401, 403):
                raise RuntimeError(f"Không có quyền truy cập hoặc sai tài khoản/mật khẩu ({msg or e.code}).") from e
            raise RuntimeError(f"Lỗi MinIO HTTP {e.code}: {msg or e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Không kết nối được tới {self.base_url}: {e.reason}") from e

    def login(self, username: str, password: str):
        if not username or not password:
            raise ValueError("Vui lòng nhập đầy đủ Username và Password MinIO.")
        with self._request("/api/v1/login", method="POST",
                           body={"accessKey": username, "secretKey": password}) as resp:
            resp.read()

    def list_buckets(self, fallback_bucket: str = "") -> list[str]:
        buckets: list[str] = []
        try:
            with self._request("/api/v1/buckets") as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for b in data.get("buckets") or []:
                    if name := b.get("name"):
                        buckets.append(name)
        except Exception:
            pass
        if fallback_bucket and fallback_bucket not in buckets:
            buckets.insert(0, fallback_bucket)
        return buckets

    def list_objects(self, bucket: str, prefix: str = "") -> list[MinioItem]:
        b_enc = urllib.parse.quote(bucket, safe="")
        params = ["limit=2000"]
        if prefix:
            # MinIO Console REST API accepts base64-encoded prefix or plain prefix depending on version
            b64_prefix = base64.b64encode(prefix.encode("utf-8")).decode("ascii")
            params.append(f"prefix={urllib.parse.quote(b64_prefix, safe='')}")
        query = "?" + "&".join(params)
        with self._request(f"/api/v1/buckets/{b_enc}/objects{query}") as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw_objs = data.get("objects") or []
        if prefix and not raw_objs:
            try:
                q_plain = f"?limit=2000&prefix={urllib.parse.quote(prefix, safe='')}"
                with self._request(f"/api/v1/buckets/{b_enc}/objects{q_plain}") as resp2:
                    data2 = json.loads(resp2.read().decode("utf-8"))
                    raw_objs = data2.get("objects") or []
            except Exception:
                pass

        items: list[MinioItem] = []
        for obj in raw_objs:
            name = obj.get("name") or ""
            if not name:
                continue
            items.append(MinioItem(
                name=name,
                size=int(obj.get("size") or 0),
                last_modified=obj.get("last_modified") or "",
            ))
        # Sort folders / dates newest first
        items.sort(key=lambda x: (x.is_folder, x.name), reverse=True)
        return items

    def download_item(self, bucket: str, prefix: str, dest_path: Path,
                      progress: Callable[[str], None] = lambda _: None) -> Path:
        b_enc = urllib.parse.quote(bucket, safe="")
        p_enc = urllib.parse.quote(prefix, safe="")
        path = f"/api/v1/buckets/{b_enc}/objects/download?prefix={p_enc}"
        label = prefix.rstrip("/").split("/")[-1] or bucket

        try:
            self._stream_to_file(path, dest_path, label, progress, method="GET")
        except Exception:
            # Fallback to download-multiple endpoint for folder zip
            multi_path = f"/api/v1/buckets/{b_enc}/objects/download-multiple"
            self._stream_to_file(multi_path, dest_path, label, progress, method="POST", body=[prefix])
        return dest_path

    def _stream_to_file(self, path: str, dest_path: Path, label: str,
                        progress: Callable[[str], None], method: str = "GET", body: object = None):
        with self._request(path, method=method, body=body, timeout=180) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    mb = downloaded / (1024 * 1024)
                    if total > 0:
                        pct = downloaded * 100 // total
                        progress(f"Đang tải {label} từ MinIO… {pct}% ({mb:.1f} MB)")
                    else:
                        progress(f"Đang tải {label} từ MinIO… ({mb:.1f} MB)")


if __name__ == "__main__":
    cfg = load_minio_config()
    base_url, bucket = cfg.base_url_and_bucket()
    print(f"MinIO URL : {base_url}")
    print(f"Bucket    : {bucket}")
    print(f"Username  : {cfg.username or '(chưa cấu hình)'}")
    if cfg.username and cfg.password:
        client = MinioConsoleClient(base_url)
        client.login(cfg.username, cfg.password)
        items = client.list_objects(bucket)
        print(f"Kết nối thành công! Tìm thấy {len(items)} mục trong '{bucket}':")
        for it in items[:10]:
            print(f"  - {it.name}")
    else:
        print("Hãy điền MINIO_USERNAME và MINIO_PASSWORD trong file .env hoặc chạy main.py để mở giao diện.")


