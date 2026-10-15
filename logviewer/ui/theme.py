"""Unified modern theme system for Log Viewer.
Supports both dark and light modes with DevTools-inspired palettes,
sleek scrollbars, modern pill badges, and refined typography.
"""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def is_dark_mode() -> bool:
    app = QApplication.instance()
    if app:
        pal = app.palette()
        return pal.color(QPalette.Window).lightness() < 128
    return True


class Theme:
    """Color tokens for the app."""
    # Accents
    PRIMARY = "#3b82f6"       # Blue 500
    PRIMARY_HOVER = "#2563eb" # Blue 600
    PRIMARY_LIGHT = "#60a5fa" # Blue 400

    # Semantic levels
    ERROR = "#ef4444"         # Red 500
    ERROR_BG_DARK = "#450a0a"
    ERROR_BG_LIGHT = "#fee2e2"
    ERROR_TEXT_DARK = "#fca5a5"
    ERROR_TEXT_LIGHT = "#991b1b"

    WARN = "#f59e0b"          # Amber 500
    WARN_BG_DARK = "#451a03"
    WARN_BG_LIGHT = "#fef3c7"
    WARN_TEXT_DARK = "#fcd34d"
    WARN_TEXT_LIGHT = "#92400e"

    INFO = "#3b82f6"          # Blue 500
    INFO_BG_DARK = "#172554"
    INFO_BG_LIGHT = "#dbeafe"
    INFO_TEXT_DARK = "#93c5fd"
    INFO_TEXT_LIGHT = "#1e40af"

    DEBUG = "#64748b"         # Slate 500
    DEBUG_BG_DARK = "#1e293b"
    DEBUG_BG_LIGHT = "#f1f5f9"
    DEBUG_TEXT_DARK = "#cbd5e1"
    DEBUG_TEXT_LIGHT = "#475569"

    # Syntax colors for JSON & Logs (Dark Mode)
    DARK_JSON_KEY = "#38bdf8"       # Sky 400
    DARK_JSON_STRING = "#4ade80"    # Emerald 400
    DARK_JSON_NUMBER = "#fbbf24"    # Amber 400
    DARK_JSON_BOOLEAN = "#c084fc"   # Purple 400
    DARK_JSON_NULL = "#f472b6"      # Pink 400
    DARK_HTTP_METHOD_GET = "#60a5fa"
    DARK_HTTP_METHOD_POST = "#34d399"
    DARK_HTTP_METHOD_PUT = "#fbbf24"
    DARK_HTTP_METHOD_DELETE = "#f87171"
    DARK_SECTION_LABEL = "#818cf8"  # Indigo 400
    DARK_TRACE_ID = "#2dd4bf"       # Teal 400
    DARK_URL = "#38bdf8"
    DARK_STACKTRACE = "#f87171"
    DARK_PUNCTUATION = "#94a3b8"

    # Syntax colors for JSON & Logs (Light Mode)
    LIGHT_JSON_KEY = "#0284c7"      # Sky 600
    LIGHT_JSON_STRING = "#15803d"   # Emerald 700
    LIGHT_JSON_NUMBER = "#d97706"   # Amber 600
    LIGHT_JSON_BOOLEAN = "#7e22ce"  # Purple 700
    LIGHT_JSON_NULL = "#be185d"     # Pink 700
    LIGHT_HTTP_METHOD_GET = "#2563eb"
    LIGHT_HTTP_METHOD_POST = "#059669"
    LIGHT_HTTP_METHOD_PUT = "#d97706"
    LIGHT_HTTP_METHOD_DELETE = "#dc2626"
    LIGHT_SECTION_LABEL = "#4f46e5" # Indigo 600
    LIGHT_TRACE_ID = "#0d9488"      # Teal 600
    LIGHT_URL = "#0284c7"
    LIGHT_STACKTRACE = "#b91c1c"
    LIGHT_PUNCTUATION = "#64748b"


def get_syntax_colors(dark: bool | None = None) -> dict[str, QColor]:
    if dark is None:
        dark = is_dark_mode()
    if dark:
        return {
            "key": QColor(Theme.DARK_JSON_KEY),
            "string": QColor(Theme.DARK_JSON_STRING),
            "number": QColor(Theme.DARK_JSON_NUMBER),
            "boolean": QColor(Theme.DARK_JSON_BOOLEAN),
            "null": QColor(Theme.DARK_JSON_NULL),
            "get": QColor(Theme.DARK_HTTP_METHOD_GET),
            "post": QColor(Theme.DARK_HTTP_METHOD_POST),
            "put": QColor(Theme.DARK_HTTP_METHOD_PUT),
            "delete": QColor(Theme.DARK_HTTP_METHOD_DELETE),
            "section": QColor(Theme.DARK_SECTION_LABEL),
            "trace_id": QColor(Theme.DARK_TRACE_ID),
            "url": QColor(Theme.DARK_URL),
            "stacktrace": QColor(Theme.DARK_STACKTRACE),
            "punctuation": QColor(Theme.DARK_PUNCTUATION),
            "text": QColor("#e2e8f0"),
        }
    else:
        return {
            "key": QColor(Theme.LIGHT_JSON_KEY),
            "string": QColor(Theme.LIGHT_JSON_STRING),
            "number": QColor(Theme.LIGHT_JSON_NUMBER),
            "boolean": QColor(Theme.LIGHT_JSON_BOOLEAN),
            "null": QColor(Theme.LIGHT_JSON_NULL),
            "get": QColor(Theme.LIGHT_HTTP_METHOD_GET),
            "post": QColor(Theme.LIGHT_HTTP_METHOD_POST),
            "put": QColor(Theme.LIGHT_HTTP_METHOD_PUT),
            "delete": QColor(Theme.LIGHT_HTTP_METHOD_DELETE),
            "section": QColor(Theme.LIGHT_SECTION_LABEL),
            "trace_id": QColor(Theme.LIGHT_TRACE_ID),
            "url": QColor(Theme.LIGHT_URL),
            "stacktrace": QColor(Theme.LIGHT_STACKTRACE),
            "punctuation": QColor(Theme.LIGHT_PUNCTUATION),
            "text": QColor("#1e293b"),
        }


def get_app_stylesheet(dark: bool | None = None) -> str:
    """Returns a polished application stylesheet with modern scrollbars, cards, and buttons."""
    if dark is None:
        dark = is_dark_mode()

    if dark:
        bg_main = "#181825"
        bg_surface = "#1e1e2e"
        bg_surface_alt = "#262638"
        border = "#313244"
        border_light = "#45475a"
        text_primary = "#cdd6f4"
        text_muted = "#a6adc8"
        text_dim = "#6c7086"
        scroll_thumb = "rgba(255, 255, 255, 0.18)"
        scroll_thumb_hover = "rgba(255, 255, 255, 0.32)"
        table_hover = "rgba(255, 255, 255, 0.04)"
        table_sel = "rgba(59, 130, 246, 0.25)"
    else:
        bg_main = "#f8fafc"
        bg_surface = "#ffffff"
        bg_surface_alt = "#f1f5f9"
        border = "#e2e8f0"
        border_light = "#cbd5e1"
        text_primary = "#0f172a"
        text_muted = "#475569"
        text_dim = "#94a3b8"
        scroll_thumb = "rgba(0, 0, 0, 0.18)"
        scroll_thumb_hover = "rgba(0, 0, 0, 0.35)"
        table_hover = "rgba(0, 0, 0, 0.03)"
        table_sel = "rgba(59, 130, 246, 0.15)"

    return f"""
    QMainWindow {{
        background-color: {bg_main};
    }}

    QSplitter::handle {{
        background-color: {border};
    }}
    QSplitter::handle:hover {{
        background-color: #3b82f6;
    }}
    QSplitter::handle:horizontal {{
        width: 3px;
    }}
    QSplitter::handle:vertical {{
        height: 3px;
    }}

    /* Sleek Modern Scrollbars */
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {scroll_thumb};
        min-height: 28px;
        border-radius: 4px;
        margin: 1px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {scroll_thumb_hover};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
        background: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {scroll_thumb};
        min-width: 28px;
        border-radius: 4px;
        margin: 1px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {scroll_thumb_hover};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
        background: none;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}

    /* Tooltips */
    QToolTip {{
        background-color: {bg_surface_alt};
        color: {text_primary};
        border: 1px solid {border_light};
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 12px;
    }}

    /* Menus */
    QMenu {{
        background-color: {bg_surface};
        color: {text_primary};
        border: 1px solid {border};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 24px 6px 12px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: #3b82f6;
        color: #ffffff;
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {border};
        margin: 4px 6px;
    }}

    /* Status Bar */
    QStatusBar {{
        background-color: {bg_surface};
        color: {text_muted};
        border-top: 1px solid {border};
        font-size: 11px;
    }}
    QStatusBar QLabel {{
        padding: 2px 8px;
    }}
    """
