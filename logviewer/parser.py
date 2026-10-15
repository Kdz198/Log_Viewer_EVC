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
TRACE_RE = re.compile(r"\[([A-Za-z0-9_-]{12,})\]")

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


LABEL_JSON_RE = re.compile(r"^([A-Za-z0-9_ -]+:\s*)([{\[].*)$")


def split_log_segments(line: str) -> list[str]:
    """Split line by ' | ' only when outside of JSON quotes, braces, and brackets."""
    parts = []
    current = []
    in_str = False
    escape = False
    brace_depth = 0
    bracket_depth = 0
    i = 0
    n = len(line)

    while i < n:
        c = line[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            current.append(c)
            i += 1
            continue

        if c == '"':
            in_str = True
            current.append(c)
            i += 1
        elif c == "{":
            brace_depth += 1
            current.append(c)
            i += 1
        elif c == "}":
            if brace_depth > 0:
                brace_depth -= 1
            current.append(c)
            i += 1
        elif c == "[":
            bracket_depth += 1
            current.append(c)
            i += 1
        elif c == "]":
            if bracket_depth > 0:
                bracket_depth -= 1
            current.append(c)
            i += 1
        elif c == " " and line[i:i+3] == " | " and brace_depth == 0 and bracket_depth == 0:
            parts.append("".join(current).strip())
            current = []
            i += 3
        else:
            current.append(c)
            i += 1

    if current:
        parts.append("".join(current).strip())

    return parts


def _try_format_json(s: str) -> str | None:
    s_strip = s.strip()
    if not (s_strip.startswith("{") and s_strip.endswith("}")) and not (s_strip.startswith("[") and s_strip.endswith("]")):
        return None
    try:
        obj = json.loads(s_strip, strict=False)
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return None


def pretty_message(text: str) -> str:
    """Intelligently detects and pretty-prints JSON segments (single-line or multiline, with or without labels)."""
    if not text:
        return ""

    lines = text.splitlines()
    result_lines: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 1. Pipe-separated log line: e.g. "POST /api | Headers: {...} | Payload: [...]"
        # Use JSON-aware splitting so that ' | ' inside JSON strings (e.g. ticketFace) doesn't break the JSON!
        if " | " in line:
            parts = split_log_segments(line)
            formatted_parts = []
            has_formatted = False
            for part in parts:
                key, sep, val = part.partition(": ")
                val_clean = val.strip()
                if sep and val_clean[:1] in "{[":
                    fmt = _try_format_json(val_clean)
                    if fmt:
                        formatted_parts.append(f"{key}:\n{fmt}")
                        has_formatted = True
                        continue
                formatted_parts.append(part)
            if has_formatted:
                result_lines.append("\n".join(formatted_parts))
                i += 1
                continue

        # 2. Line with "Label: JSON" on same line, e.g. "Payload: [{"eventId": ...}]"
        m = LABEL_JSON_RE.match(line)
        if m:
            prefix, first_part = m.groups()
            open_char = first_part.strip()[0]
            close_char = "}" if open_char == "{" else "]"
            accum = [first_part]
            matched = False
            for j in range(i, min(n, i + 1000)):
                if j > i:
                    accum.append(lines[j])
                candidate = "\n".join(accum).strip()
                if candidate.endswith(close_char):
                    fmt = _try_format_json(candidate)
                    if fmt:
                        result_lines.append(f"{prefix.strip()}\n{fmt}")
                        i = j + 1
                        matched = True
                        break
            if matched:
                continue

        # 3. Label line "Headers:" followed by JSON on next line "{", or standalone JSON block
        label_prefix = ""
        block_start_idx = i
        if stripped.endswith(":") and not stripped.startswith("at ") and not stripped.startswith("Caused by"):
            if i + 1 < n and lines[i + 1].strip()[:1] in "{[":
                label_prefix = line
                block_start_idx = i + 1

        curr_strip = lines[block_start_idx].strip()
        if curr_strip[:1] in ("{", "["):
            open_char = curr_strip[0]
            close_char = "}" if open_char == "{" else "]"
            accum = []
            matched = False
            for j in range(block_start_idx, min(n, block_start_idx + 1000)):
                accum.append(lines[j])
                candidate = "\n".join(accum).strip()
                if candidate.endswith(close_char):
                    fmt = _try_format_json(candidate)
                    if fmt:
                        if label_prefix:
                            result_lines.append(label_prefix)
                        result_lines.append(fmt)
                        i = j + 1
                        matched = True
                        break
            if matched:
                continue

        result_lines.append(line)
        i += 1

    return "\n".join(result_lines)

