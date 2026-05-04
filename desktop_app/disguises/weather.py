"""Weather widget disguise. Answer replaces the conditions text."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget

from ._base import DisguiseWidget


class WeatherDisguise(DisguiseWidget):
    """Card with temperature on the left, conditions on the right."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(180, 80)
        self._answer = ""

    def set_answer(self, text: str) -> None:
        self._answer = text
        self.update()
        super().set_answer(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#1e3a8a"))

        # Sun icon (top-left).
        p.setBrush(QColor("#fde68a"))
        p.setPen(Qt.PenStyle.NoPen)
        sun_r = self.height() * 0.22
        p.drawEllipse(int(8), int(8), int(sun_r * 2), int(sun_r * 2))

        font = QFont("Segoe UI", max(14, self.height() // 3))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#f8fafc"))
        p.drawText(
            self.rect().adjusted(int(sun_r * 2 + 16), 4, -8, -self.height() // 2),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            "27\u00b0",
        )

        sub_font = QFont("Segoe UI", max(8, self.height() // 6))
        p.setFont(sub_font)
        p.setPen(QColor("#cbd5f5"))
        sub_text = self._answer or "Sunny / Light wind"
        p.drawText(
            self.rect().adjusted(8, self.height() // 2, -8, -4),
            int(Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
                | Qt.TextFlag.TextWordWrap),
            sub_text,
        )
