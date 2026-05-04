"""Wi-Fi signal indicator. Answer plumbed via tooltip."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ._base import DisguiseWidget


class WifiDisguise(DisguiseWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(48, 48)

    def set_answer(self, text: str) -> None:
        self.setToolTip(text)
        super().set_answer(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        side = min(self.width(), self.height())
        cx = self.width() / 2
        cy = self.height() * 0.7
        # Three nested arcs + center dot, matching the OS-level icon.
        for i, radius in enumerate((side * 0.18, side * 0.32, side * 0.46)):
            color = QColor("#2563eb")
            color.setAlpha(255 - i * 40)
            pen = QPen(color, max(2.0, side * 0.06))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            rect = (
                cx - radius, cy - radius,
                radius * 2, radius * 2,
            )
            # 16ths-of-a-degree as Qt expects.
            p.drawArc(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]),
                      45 * 16, 90 * 16)
        p.setBrush(QColor("#2563eb"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), side * 0.06, side * 0.06)
        # Suppress unused-import warning under newer linters.
        _ = math
