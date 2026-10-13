"""Modern translucent loading overlay with a smooth animated spinner card and progress bar."""
import re

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget

PCT_RE = re.compile(r"(\d{1,3})\s*%")
FRAC_RE = re.compile(r"\((\d+)\s*/\s*(\d+)\)")
ACCENT = QColor("#3b82f6")
ACCENT_TRACK = QColor(59, 130, 246, 45)


class SpinnerWidget(QWidget):
    """Smooth custom-painted dual-arc loading spinner."""

    def __init__(self, size: int = 44, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self, interval=16)  # ~60 FPS
        self._timer.timeout.connect(self._tick)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        margin = 4.5
        rect = QRectF(margin, margin, w - margin * 2, h - margin * 2)

        # Track circle
        track_pen = QPen(ACCENT_TRACK, 3.8)
        track_pen.setCapStyle(Qt.RoundCap)
        p.setPen(track_pen)
        p.drawEllipse(rect)

        # Primary spinning arc
        arc_pen = QPen(ACCENT, 3.8)
        arc_pen.setCapStyle(Qt.RoundCap)
        p.setPen(arc_pen)
        p.drawArc(rect, int(-self._angle * 16), int(-110 * 16))


class LoadingOverlay(QWidget):
    """Translucent overlay covering its parent widget with a centered status card."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.hide()
        parent.installEventFilter(self)

        # Centered card
        self.card = QFrame(self)
        self.card.setObjectName("loadingCard")
        self.card.setFixedWidth(380)
        self.card.setStyleSheet(
            "#loadingCard {"
            "  background-color: palette(base);"
            "  border: 1px solid palette(mid);"
            "  border-radius: 12px;"
            "}"
        )

        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(24, 22, 24, 22)
        card_lay.setSpacing(10)
        card_lay.setAlignment(Qt.AlignCenter)

        self.spinner = SpinnerWidget(44, self.card)

        self.title_label = QLabel("Đang xử lý…", self.card)
        t_font = QFont(self.title_label.font())
        t_font.setPointSizeF(t_font.pointSizeF() + 1.5)
        t_font.setBold(True)
        self.title_label.setFont(t_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)

        self.detail_label = QLabel("", self.card)
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setStyleSheet("color: gray; font-size: 12px;")
        self.detail_label.setWordWrap(True)

        self.progress = QProgressBar(self.card)
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)  # indeterminate by default
        self.progress.setStyleSheet(
            "QProgressBar {"
            "  background-color: rgba(128, 128, 128, 35);"
            "  border: none;"
            "  border-radius: 4px;"
            "}"
            "QProgressBar::chunk {"
            "  background-color: #3b82f6;"
            "  border-radius: 4px;"
            "}"
        )

        self.pct_label = QLabel("", self.card)
        self.pct_label.setAlignment(Qt.AlignCenter)
        self.pct_label.setStyleSheet("color: #3b82f6; font-weight: 600; font-size: 11px;")

        card_lay.addWidget(self.spinner, 0, Qt.AlignHCenter)
        card_lay.addSpacing(2)
        card_lay.addWidget(self.title_label)
        card_lay.addWidget(self.detail_label)
        card_lay.addSpacing(4)
        card_lay.addWidget(self.progress)
        card_lay.addWidget(self.pct_label)

    def start(self, title: str = "Đang tải dữ liệu…", detail: str = ""):
        self.title_label.setText(title)
        self.set_status(detail)
        self._sync_geometry()
        self.raise_()
        self.show()
        self.spinner.start()

    def set_status(self, text: str):
        self.detail_label.setText(text)
        # Automatically extract progress percentage or (current/total) fraction if present
        if m_pct := PCT_RE.search(text):
            pct = max(0, min(100, int(m_pct.group(1))))
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
            self.pct_label.setText(f"{pct}%")
            self.pct_label.show()
        elif m_frac := FRAC_RE.search(text):
            cur, total = int(m_frac.group(1)), int(m_frac.group(2))
            if total > 0:
                pct = max(0, min(100, cur * 100 // total))
                self.progress.setRange(0, 100)
                self.progress.setValue(pct)
                self.pct_label.setText(f"{cur}/{total} ({pct}%)")
                self.pct_label.show()
        else:
            self.progress.setRange(0, 0)
            self.pct_label.hide()
        self._center_card()

    def stop(self):
        self.spinner.stop()
        self.hide()

    def _sync_geometry(self):
        if p := self.parentWidget():
            self.setGeometry(p.rect())
            self._center_card()

    def _center_card(self):
        self.card.adjustSize()
        x = (self.width() - self.card.width()) // 2
        y = (self.height() - self.card.height()) // 2
        self.card.move(max(0, x), max(0, y))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_card()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Resize:
            self._sync_geometry()
        return super().eventFilter(obj, event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(15, 23, 42, 95))
