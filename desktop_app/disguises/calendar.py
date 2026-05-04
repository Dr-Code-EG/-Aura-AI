"""Mini calendar widget. Answer takes over the bottom note line."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget

from ._base import DisguiseWidget


class CalendarDisguise(DisguiseWidget):
    """Big day-of-month card with the month name above it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(120, 130)
        self._answer = ""

    def set_answer(self, text: str) -> None:
        self._answer = text
        self.update()
        super().set_answer(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#fef3c7"))

        today = date.today()
        # Header strip.
        header_h = self.height() // 4
        p.fillRect(0, 0, self.width(), header_h, QColor("#dc2626"))
        font = QFont("Segoe UI", max(8, header_h // 2))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#fef2f2"))
        p.drawText(
            self.rect().adjusted(0, 0, 0, -(self.height() - header_h)),
            Qt.AlignmentFlag.AlignCenter,
            today.strftime("%B %Y").upper(),
        )

        big_font = QFont("Segoe UI", max(20, self.height() // 3))
        big_font.setBold(True)
        p.setFont(big_font)
        p.setPen(QColor("#7c2d12"))
        p.drawText(
            self.rect().adjusted(0, header_h, 0, -(self.height() // 4)),
            Qt.AlignmentFlag.AlignCenter,
            f"{today.day}",
        )

        small_font = QFont("Segoe UI", max(7, self.height() // 11))
        p.setFont(small_font)
        p.setPen(QColor("#7c2d12"))
        text = self._answer or today.strftime("%A")
        p.drawText(
            self.rect().adjusted(8, self.height() - self.height() // 4, -8, -4),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            text,
        )
