"""Volume mixer disguise: bars + speaker icon, answer via tooltip."""

from __future__ import annotations

import random

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

from ._base import DisguiseWidget


class VolumeMixerDisguise(DisguiseWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(160, 60)
        self._levels = [random.randint(20, 90) for _ in range(8)]

    def set_answer(self, text: str) -> None:
        self.setToolTip(text)
        super().set_answer(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#0f172a"))

        n = len(self._levels)
        margin = 6
        bar_w = (self.width() - margin * (n + 1)) / n
        h = self.height() - margin * 2
        for i, lvl in enumerate(self._levels):
            x = margin + i * (bar_w + margin)
            full = QRectF(x, margin, bar_w, h)
            p.setBrush(QColor("#1e293b"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(full, 2, 2)
            fill_h = h * (lvl / 100.0)
            fill = QRectF(x, margin + (h - fill_h), bar_w, fill_h)
            color = QColor("#22d3ee") if lvl < 75 else QColor("#f97316")
            p.setBrush(color)
            p.drawRoundedRect(fill, 2, 2)
