"""Custom painting for the log table: level-tinted rows, colored accent stripes,
modern level pills, muted monospace timestamps, and crisp multiline badges.
"""
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ..models import LogTableModel
from .theme import Theme

LEVEL_COLORS = {
    "ERROR": QColor(Theme.ERROR),
    "WARN": QColor(Theme.WARN),
    "INFO": QColor(Theme.INFO),
    "DEBUG": QColor(Theme.DEBUG),
}


def _alpha(c: QColor, a: int) -> QColor:
    c = QColor(c)
    c.setAlpha(a)
    return c


ROW_TINT = {
    "ERROR": _alpha(LEVEL_COLORS["ERROR"], 28),
    "WARN": _alpha(LEVEL_COLORS["WARN"], 22),
}

PAD = 10


class LogDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.hover_row = -1

        # Monospace font for timestamps
        self.mono = QFont("Cascadia Code")
        if not self.mono.exactMatch():
            self.mono = QFont("Consolas")
        self.mono.setStyleHint(QFont.Monospace)
        self.mono.setPointSizeF(view.font().pointSizeF())

        self.mono_bold = QFont(self.mono)
        self.mono_bold.setWeight(QFont.DemiBold)

        self.pill_font = QFont(view.font())
        self.pill_font.setPointSizeF(max(7.5, view.font().pointSizeF() - 1.5))
        self.pill_font.setBold(True)

        self.badge_font = QFont(view.font())
        self.badge_font.setPointSizeF(max(7.5, view.font().pointSizeF() - 1.5))
        self.badge_font.setWeight(QFont.Medium)

    def set_hover_row(self, row: int):
        if row != self.hover_row:
            self.hover_row = row
            self.view.viewport().update()

    def paint(self, p: QPainter, opt, index):
        model: LogTableModel = index.model()
        e = model.entry_at(index.row())
        col = index.column()
        pal = opt.palette
        text_color = pal.text().color()
        muted = _alpha(text_color, 140)
        level_color = LEVEL_COLORS.get(e.level, LEVEL_COLORS["INFO"])
        r = opt.rect

        p.save()
        p.setRenderHint(QPainter.Antialiasing)

        # Background rendering
        if opt.state & QStyle.State_Selected:
            p.fillRect(r, _alpha(pal.highlight().color(), 90))
        elif index.row() == self.hover_row:
            p.fillRect(r, _alpha(text_color, 20))
        elif e.level in ROW_TINT:
            p.fillRect(r, ROW_TINT[e.level])

        # Bottom separator between rows
        p.setPen(_alpha(text_color, 18))
        p.drawLine(r.bottomLeft(), r.bottomRight())

        # Colored left accent indicator bar on first column
        if col == LogTableModel.COL_TIME:
            if opt.state & QStyle.State_Selected:
                # Highlight bar for active row
                bar_rect = QRectF(r.left(), r.top() + 1, 3.5, r.height() - 2)
                p.fillRect(bar_rect, pal.highlight().color())
            elif e.level in ("ERROR", "WARN"):
                bar_rect = QRectF(r.left(), r.top() + 1, 3.5, r.height() - 2)
                p.fillRect(bar_rect, level_color)

        inner = r.adjusted(PAD, 0, -PAD, 0)

        # Column 0: Formatted Timestamp
        if col == LogTableModel.COL_TIME:
            self._paint_time(p, inner, index.data(), text_color, muted)

        # Column 1: Modern Level Pill Badge
        elif col == LogTableModel.COL_LEVEL and e.level:
            p.setFont(self.pill_font)
            fm = p.fontMetrics()
            w, h = fm.horizontalAdvance(e.level) + 16, fm.height() + 4
            pill = QRectF(inner.left(), r.center().y() - h / 2.0, w, h)

            # Draw background pill
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(level_color, 45))
            p.drawRoundedRect(pill, h / 2.0, h / 2.0)

            # Draw subtle border
            p.setPen(_alpha(level_color, 120))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(pill, h / 2.0, h / 2.0)

            # Draw level text
            p.setPen(level_color)
            p.drawText(pill, Qt.AlignCenter, e.level)

        # Column 2: Message & Multiline Badge
        elif col == LogTableModel.COL_MESSAGE:
            if e.extra_count:
                p.setFont(self.badge_font)
                fm = p.fontMetrics()
                label = f"+{e.extra_count} dòng"
                w, h = fm.horizontalAdvance(label) + 14, fm.height() + 3
                badge = QRectF(inner.right() - w, r.center().y() - h / 2.0, w, h)

                p.setPen(Qt.NoPen)
                p.setBrush(_alpha(text_color, 26))
                p.drawRoundedRect(badge, 4.0, 4.0)

                p.setPen(_alpha(text_color, 70))
                p.drawRoundedRect(badge, 4.0, 4.0)

                p.setPen(muted)
                p.drawText(badge, Qt.AlignCenter, label)
                inner.setRight(int(badge.left() - 8))

            p.setFont(opt.font)
            if e.level == "ERROR":
                p.setPen(level_color)
            elif e.level == "WARN":
                p.setPen(_alpha(level_color, 230))
            else:
                p.setPen(text_color)

            text = p.fontMetrics().elidedText(index.data(), Qt.ElideRight, inner.width())
            p.drawText(inner, Qt.AlignVCenter | Qt.AlignLeft, text)

        p.restore()

    def _paint_time(self, p: QPainter, rect: QRect, s: str, strong: QColor, muted: QColor):
        """'2026-09-29 15:13:37.290' -> dim '29/09', bright '15:13:37', dim '.290'."""
        if len(s) < 19:
            p.setFont(self.mono)
            p.setPen(strong)
            p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, s)
            return
        x = rect.left()
        for text, font, color in (
            (f"{s[8:10]}/{s[5:7]} ", self.mono, muted),
            (s[11:19], self.mono_bold, strong),
            (s[19:], self.mono, muted),
        ):
            p.setFont(font)
            p.setPen(color)
            w = p.fontMetrics().horizontalAdvance(text)
            p.drawText(QRect(x, rect.top(), w + 2, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
            x += w
