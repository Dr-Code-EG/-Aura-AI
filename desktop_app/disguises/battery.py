"""Battery indicator. Answer is exposed via tooltip."""

from __future__ import annotations

import random

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget

from ._base import DisguiseWidget


class BatteryDisguise(DisguiseWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(80, 36)
        self._level = random.randint(40, 95)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60_000)  # drift every minute, like a real reading

    def _tick(self) -> None:
        delta = random.choice([-1, 0, 0, 1])
        self._level = max(5, min(99, self._level + delta))
        self.update()

    def set_answer(self, text: str) -> None:
        # Setting a tooltip is what the registry asked for; keep
        # painting the battery untouched so nothing visually changes.
        self.setToolTip(text)
        super().set_answer(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        side = min(self.width() - 16, self.height() * 2)
        h = max(16, self.height() - 8)
        x = (self.width() - side) / 2
        y = (self.height() - h) / 2
        body = QRectF(x, y, side - 6, h)
        cap = QRectF(x + side - 6, y + h * 0.25, 4, h * 0.5)

        p.setPen(QColor("#1f2937"))
        p.setBrush(QColor("#f9fafb"))
        p.drawRoundedRect(body, 3, 3)
        p.setBrush(QColor("#1f2937"))
        p.drawRect(cap)

        fill_w = (body.width() - 4) * (self._level / 100.0)
        fill = QRectF(body.x() + 2, body.y() + 2, fill_w, body.height() - 4)
        if self._level <= 15:
            color = QColor("#dc2626")
        elif self._level <= 30:
            color = QColor("#f59e0b")
        else:
            color = QColor("#16a34a")
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(fill, 2, 2)

        p.setPen(QColor("#1f2937"))
        font = QFont("Segoe UI", max(7, h // 3))
        font.setBold(True)
        p.setFont(font)
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, f"{self._level}%")
