"""CPU usage bar — animated bar graph, tooltip carries the answer."""

from __future__ import annotations

import random

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget

from ._base import DisguiseWidget


class CpuBarDisguise(DisguiseWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(160, 40)
        self._cores = [random.randint(15, 80) for _ in range(8)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(800)

    def _tick(self) -> None:
        for i in range(len(self._cores)):
            delta = random.randint(-12, 12)
            self._cores[i] = max(2, min(99, self._cores[i] + delta))
        self.update()

    def set_answer(self, text: str) -> None:
        self.setToolTip(text)
        super().set_answer(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#020617"))

        # Mini grid background.
        p.setPen(QColor("#0f172a"))
        for x in range(0, self.width(), 8):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 8):
            p.drawLine(0, y, self.width(), y)

        n = len(self._cores)
        margin = 4
        bar_w = (self.width() - margin * (n + 1)) / n
        for i, lvl in enumerate(self._cores):
            x = margin + i * (bar_w + margin)
            h = (self.height() - 8) * (lvl / 100.0)
            rect = QRectF(x, self.height() - 4 - h, bar_w, h)
            color = QColor("#22d3ee")
            if lvl > 75:
                color = QColor("#f97316")
            if lvl > 90:
                color = QColor("#ef4444")
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 1, 1)

        p.setPen(QColor("#94a3b8"))
        font = QFont("Consolas", max(7, self.height() // 6))
        p.setFont(font)
        p.drawText(self.rect().adjusted(4, 0, -4, 0),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                   "CPU")
