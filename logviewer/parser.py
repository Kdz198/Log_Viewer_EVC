"""Split Spring Boot console logs into entries (a header line plus its continuation lines,
e.g. stack traces)."""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo

# 2026-09-29T08:00:08.959Z  INFO 1 --- [evc-accounting] [tomcat-handler-1] c.e.Foo : message
HEADER_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"(?P<level>TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s+(?P<rest>.*)$"
)
SPRING_REST_RE = re.compile(
    r"^\d+\s+---\s+(?:\[(?P<app>[^\]]*)\]\s+)?\[(?P<thread>[^\]]*)\]\s+(?P<logger>\S+)\s*:\s?(?P<msg>.*)$"
)
TRACE_RE = re.compile(r"\[([A-Z]{2,10}-[A-Za-z0-9_-]{10,})\]")

LEVEL_GROUP = {"TRACE": "DEBUG", "DEBUG": "DEBUG", "INFO": "INFO",
               "WARN": "WARN", "WARNING": "WARN", "ERROR": "ERROR", "FATAL": "ERROR"}
LEVELS = ("ERROR", "WARN", "INFO", "DEBUG")

UTC = timezone.utc
VN_TZ = timezone(timedelta(hours=7), "UTC+7")


@dataclass(slots=True)
class LogEntry:
    ts: datetime | None
    ts_raw: str
    level: str          # normalized: ERROR / WARN / INFO / DEBUG / "" (no header)
    thread: str
    logger: str
    message: str        # rest of the header line
    extra: str          # continuation lines (stack trace...)
    extra_count: int
    trace_id: str
    source: str
    raw: str            # original header line

    def raw_text(self) -> str:
        return f"{self.raw}\n{self.extra}" if self.extra else self.raw


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace(",", "."))
    except ValueError:
        return None


def _make_entry(line: str, source: str) -> LogEntry:
    m = HEADER_RE.match(line)
    if not m:
        return LogEntry(None, "", "", "", "", line, "", 0, "", source, line)
    rest = m.group("rest")
    thread = logger = ""
    msg = rest
    sm = SPRING_REST_RE.match(rest)
    if sm:
        thread, logger, msg = sm.group("thread").strip(), sm.group("logger"), sm.group("msg")
    tm = TRACE_RE.search(msg)
    return LogEntry(_parse_ts(m.group("ts")), m.group("ts"), LEVEL_GROUP[m.group("level")],
                    thread, logger, msg, "", 0, tm.group(1) if tm else "", source, line)


def parse_text(text: str, source: str = "") -> list[LogEntry]:
    entries: list[LogEntry] = []
    cur: LogEntry | None = None
    cont: list[str] = []

    def flush():
        if cur is not None:
            if cont:
                cur.extra = "\n".join(cont)
                cur.extra_count = len(cont)
            entries.append(cur)

    for line in text.splitlines():
        if HEADER_RE.match(line) or cur is None:
            flush()
            cur, cont = _make_entry(line, source), []
        else:
            cont.append(line)
    flush()
    return entries


def display_time(e: LogEntry, tz: tzinfo | None) -> str:
    ts = e.ts
    if ts is None:
        return e.ts_raw
    if tz is not None and ts.tzinfo is not None:
        ts = ts.astimezone(tz)
    return ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts.microsecond // 1000:03d}"


def local_hour(e: LogEntry, tz: tzinfo | None) -> int | None:
    if e.ts is None:
        return None
    ts = e.ts.astimezone(tz) if tz is not None and e.ts.tzinfo is not None else e.ts
    return ts.hour


def pretty_message(msg: str) -> str:
    """Pretty-print JSON segments like `Headers: {...} | Payload: [...]`."""
    out = []
    for part in msg.split(" | "):
        key, sep, val = part.partition(": ")
        val = val.strip()
        if sep and val[:1] in "{[":
            try:
                out.append(f"{key}:\n{json.dumps(json.loads(val), indent=2, ensure_ascii=False)}")
                continue
            except ValueError:
                pass
        out.append(part)
    return "\n".join(out)
