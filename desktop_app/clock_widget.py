"""Analog clock widget — the user-facing surface of Dr Code.

The whole app is disguised as a regular desk clock. The user clicks
on the clock face to ask the question on screen, and the answer is
shown via the parent window's title bar.

The clock is drawn with QPainter from scratch so it doesn't depend
on any image assets and looks identical on every machine.
"""

from __future__ import annotations

import math
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget


class ClockWidget(QWidget):
    """A live analog clock. Clicking emits :pyattr:`clicked`."""

    clicked = pyqtSignal()

    # Brand-neutral, watch-like palette.
    _DIAL_OUTER = QColor("#1a1a1d")
    _DIAL_INNER_TOP = QColor("#fafafa")
    _DIAL_INNER_BOTTOM = QColor("#dcdcdc")
    _MARKER = QColor("#1a1a1d")
    _MINUTE_TICK = QColor("#888888")
    _HAND = QColor("#1a1a1d")
    _SECOND_HAND = QColor("#c62828")
    _CENTER_DOT = QColor("#1a1a1d")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(280, 280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        # 1 Hz is plenty — the second hand jumps once a second like a
        # quartz movement, which is exactly what a real desk clock
        # does. (Smooth-sweep would give the disguise away on most
        # cheap clocks anyway.)
        self._timer.start(1000)

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event) -> None:  # noqa: D401, N802
        side = min(self.width(), self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.translate(self.width() / 2, self.height() / 2)
        # Normalize so the dial radius is exactly 100 units; scale to
        # the actual widget side. Anything smaller than that is just
        # decoration outside the radius-100 dial.
        painter.scale(side / 220.0, side / 220.0)

        self._draw_bezel(painter)
        self._draw_dial(painter)
        self._draw_hour_markers(painter)
        self._draw_minute_ticks(painter)
        self._draw_brand(painter)

        now = datetime.now()
        hour = now.hour % 12
        minute = now.minute
        second = now.second
        self._draw_hour_hand(painter, hour, minute)
        self._draw_minute_hand(painter, minute, second)
        self._draw_second_hand(painter, second)
        self._draw_center_cap(painter)

    def _draw_bezel(self, painter: QPainter) -> None:
        # Outer dark ring giving the clock a watch-like rim.
        painter.save()
        gradient = QRadialGradient(QPointF(0, 0), 110)
        gradient.setColorAt(0.85, QColor("#2b2b30"))
        gradient.setColorAt(1.0, QColor("#0d0d0f"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), 108, 108)
        painter.restore()

    def _draw_dial(self, painter: QPainter) -> None:
        painter.save()
        gradient = QLinearGradient(QPointF(0, -100), QPointF(0, 100))
        gradient.setColorAt(0.0, self._DIAL_INNER_TOP)
        gradient.setColorAt(1.0, self._DIAL_INNER_BOTTOM)
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(self._DIAL_OUTER, 2))
        painter.drawEllipse(QPointF(0, 0), 100, 100)
        painter.restore()

    def _draw_hour_markers(self, painter: QPainter) -> None:
        painter.save()
        font = QFont("Georgia", 14, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QPen(self._MARKER, 2))
        # Roman numerals for the hours give it that classic-clock look.
        numerals = [
            "XII", "I", "II", "III", "IV", "V",
            "VI", "VII", "VIII", "IX", "X", "XI",
        ]
        for i, label in enumerate(numerals):
            angle = math.radians(i * 30 - 90)
            x = math.cos(angle) * 80
            y = math.sin(angle) * 80
            rect = QRectF(x - 14, y - 10, 28, 20)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _draw_minute_ticks(self, painter: QPainter) -> None:
        painter.save()
        for i in range(60):
            angle = math.radians(i * 6 - 90)
            inner = 92 if i % 5 else 88
            outer = 96
            painter.setPen(
                QPen(self._MARKER if i % 5 == 0 else self._MINUTE_TICK,
                     1.6 if i % 5 == 0 else 0.8)
            )
            painter.drawLine(
                QPointF(math.cos(angle) * inner, math.sin(angle) * inner),
                QPointF(math.cos(angle) * outer, math.sin(angle) * outer),
            )
        painter.restore()

    def _draw_brand(self, painter: QPainter) -> None:
        painter.save()
        painter.setPen(QPen(QColor("#888888"), 1))
        painter.setFont(QFont("Georgia", 7, QFont.Weight.Normal,
                              italic=True))
        painter.drawText(QRectF(-40, 28, 80, 14),
                         Qt.AlignmentFlag.AlignCenter, "QUARTZ")
        painter.restore()

    def _draw_hour_hand(self, painter: QPainter, hour: int,
                        minute: int) -> None:
        painter.save()
        angle = (hour + minute / 60.0) * 30 - 90
        painter.rotate(angle)
        painter.setPen(QPen(self._HAND, 6, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(-8, 0), QPointF(50, 0))
        painter.restore()

    def _draw_minute_hand(self, painter: QPainter, minute: int,
                          second: int) -> None:
        painter.save()
        angle = (minute + second / 60.0) * 6 - 90
        painter.rotate(angle)
        painter.setPen(QPen(self._HAND, 4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(-12, 0), QPointF(72, 0))
        painter.restore()

    def _draw_second_hand(self, painter: QPainter, second: int) -> None:
        painter.save()
        angle = second * 6 - 90
        painter.rotate(angle)
        painter.setPen(QPen(self._SECOND_HAND, 1.5,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(-18, 0), QPointF(80, 0))
        # Counter-weight teardrop on the back of the second hand.
        painter.setBrush(QBrush(self._SECOND_HAND))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(-18, 0), 5, 5)
        painter.restore()

    def _draw_center_cap(self, painter: QPainter) -> None:
        painter.save()
        painter.setBrush(QBrush(self._CENTER_DOT))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), 5, 5)
        painter.setBrush(QBrush(self._SECOND_HAND))
        painter.drawEllipse(QPointF(0, 0), 2, 2)
        painter.restore()

    # ------------------------------------------------------------------ click
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # Squelch the click event from propagating; just emit the
            # high-level signal.
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
