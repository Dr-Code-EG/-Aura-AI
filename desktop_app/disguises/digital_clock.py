"""Digital clock disguise. The answer briefly replaces the digits."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget

from ._base import DisguiseWidget


class DigitalClockDisguise(DisguiseWidget):
    """A 7-segment style HH:MM digital clock."""

    _BG = QColor("#0a0a0d")
    _FG = QColor("#33ff66")
    _GHOST = QColor("#1a3a22")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(120, 60)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(1000)
        self._answer = ""

    def set_answer(self, text: str) -> None:
        self._answer = text
        self.update()
        super().set_answer(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), self._BG)

        if self._answer:
            font = QFont("Consolas", max(10, self.height() // 5))
            p.setPen(self._FG)
            p.setFont(font)
            p.drawText(
                self.rect().adjusted(8, 4, -8, -4),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._answer,
            )
            return

        now = datetime.now()
        text = now.strftime("%H:%M")
        font = QFont("Consolas", max(14, self.height() // 2))
        font.setBold(True)
        p.setFont(font)
        p.setPen(self._FG)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)
