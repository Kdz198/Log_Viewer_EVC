"""Custom painting for the log table: level-tinted rows, a colored stripe on
ERROR/WARN, level pills, muted monospace timestamps and a "+N dòng" badge."""
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ..models import LogTableModel

LEVEL_COLORS = {
    "ERROR": QColor("#e5484d"),
    "WARN": QColor("#e08a1e"),
    "INFO": QColor("#3b82f6"),
    "DEBUG": QColor("#8b8d98"),
}


def _alpha(c: QColor, a: int) -> QColor:
    c = QColor(c)
    c.setAlpha(a)
    return c


ROW_TINT = {"ERROR": _alpha(LEVEL_COLORS["ERROR"], 26), "WARN": _alpha(LEVEL_COLORS["WARN"], 20)}
PAD = 10


class LogDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.hover_row = -1
        self.mono = QFont("Consolas")
        self.mono.setStyleHint(QFont.Monospace)
        self.mono.setPointSizeF(view.font().pointSizeF())
        self.mono_bold = QFont(self.mono)
        self.mono_bold.setWeight(QFont.DemiBold)
        self.pill_font = QFont(view.font())
        self.pill_font.setPointSizeF(max(7.0, view.font().pointSizeF() - 1.5))
        self.pill_font.setBold(True)
        self.badge_font = QFont(view.font())
        self.badge_font.setPointSizeF(max(7.0, view.font().pointSizeF() - 1.5))

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
        level_color = LEVEL_COLORS.get(e.level)
        r = opt.rect

        p.save()
        p.setRenderHint(QPainter.Antialiasing)

        # background
        if opt.state & QStyle.State_Selected:
            p.fillRect(r, _alpha(pal.highlight().color(), 85))
        elif index.row() == self.hover_row:
            p.fillRect(r, _alpha(text_color, 18))
        elif e.level in ROW_TINT:
            p.fillRect(r, ROW_TINT[e.level])
        # thin separator between rows
        p.setPen(_alpha(text_color, 20))
        p.drawLine(r.bottomLeft(), r.bottomRight())

        if col == LogTableModel.COL_TIME and e.level in ROW_TINT:
            p.fillRect(QRect(r.left(), r.top(), 3, r.height()), level_color)

        inner = r.adjusted(PAD, 0, -PAD, 0)

        if col == LogTableModel.COL_TIME:
            self._paint_time(p, inner, index.data(), text_color, muted)

        elif col == LogTableModel.COL_LEVEL and e.level:
            p.setFont(self.pill_font)
            fm = p.fontMetrics()
            w, h = fm.horizontalAdvance(e.level) + 14, fm.height() + 4
            pill = QRect(inner.left(), r.center().y() - h // 2 + 1, w, h)
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(level_color, 45))
            p.drawRoundedRect(pill, h / 2, h / 2)
            p.setPen(level_color)
            p.drawText(pill, Qt.AlignCenter, e.level)

        elif col == LogTableModel.COL_MESSAGE:
            if e.extra_count:
                p.setFont(self.badge_font)
                fm = p.fontMetrics()
                label = f"+{e.extra_count} dòng"
                w, h = fm.horizontalAdvance(label) + 12, fm.height() + 2
                badge = QRect(inner.right() - w, r.center().y() - h // 2 + 1, w, h)
                p.setPen(Qt.NoPen)
                p.setBrush(_alpha(text_color, 28))
                p.drawRoundedRect(badge, 4, 4)
                p.setPen(muted)
                p.drawText(badge, Qt.AlignCenter, label)
                inner.setRight(badge.left() - 8)
            p.setFont(opt.font)
            p.setPen(level_color if e.level == "ERROR" else text_color)
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
        for text, font, color in ((f"{s[8:10]}/{s[5:7]} ", self.mono, muted),
                                  (s[11:19], self.mono_bold, strong),
                                  (s[19:], self.mono, muted)):
            p.setFont(font)
            p.setPen(color)
            w = p.fontMetrics().horizontalAdvance(text)
            p.drawText(QRect(x, rect.top(), w + 2, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
            x += w
