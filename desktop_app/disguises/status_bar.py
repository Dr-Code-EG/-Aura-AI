"""Slim horizontal status bar — looks like an OS notification ticker."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PyQt6.QtWidgets import QWidget

from ._base import DisguiseWidget


class StatusBarDisguise(DisguiseWidget):
    """A long thin bar with a clock on the right and message on the left."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(220, 28)
        self._answer = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(1000)

    def set_answer(self, text: str) -> None:
        self._answer = text
        self.update()
        super().set_answer(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0.0, QColor("#1f2937"))
        gradient.setColorAt(1.0, QColor("#111827"))
        p.fillRect(self.rect(), gradient)

        font = QFont("Segoe UI", max(8, self.height() // 3))
        p.setFont(font)

        clock_text = datetime.now().strftime("%H:%M")
        clock_w = p.fontMetrics().horizontalAdvance(clock_text) + 16
        p.setPen(QColor("#e5e7eb"))
        p.drawText(
            self.rect().adjusted(0, 0, -8, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            clock_text,
        )

        message = self._answer or "All systems normal"
        p.setPen(QColor("#a7f3d0") if self._answer else QColor("#9ca3af"))
        p.drawText(
            self.rect().adjusted(10, 0, -clock_w, 0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            message,
        )
