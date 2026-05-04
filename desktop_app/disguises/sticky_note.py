"""Sticky note disguise. Body text is the answer (great for long answers)."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPolygonF
from PyQt6.QtWidgets import QWidget

from ._base import DisguiseWidget


class StickyNoteDisguise(DisguiseWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(180, 140)
        self._answer = ""

    def set_answer(self, text: str) -> None:
        self._answer = text
        self.update()
        super().set_answer(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Note body with a folded-over corner.
        body = QPolygonF([
            QPointF(0, 0),
            QPointF(self.width(), 0),
            QPointF(self.width(), self.height() - 20),
            QPointF(self.width() - 20, self.height()),
            QPointF(0, self.height()),
        ])
        p.setBrush(QColor("#fde68a"))
        p.setPen(QColor("#92400e"))
        p.drawPolygon(body)

        # Folded-corner triangle gives the post-it look.
        fold = QPolygonF([
            QPointF(self.width(), self.height() - 20),
            QPointF(self.width() - 20, self.height()),
            QPointF(self.width() - 20, self.height() - 20),
        ])
        p.setBrush(QColor("#fbbf24"))
        p.drawPolygon(fold)

        # Title row.
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#92400e"))
        p.drawText(
            self.rect().adjusted(8, 6, -8, -(self.height() - 24)),
            Qt.AlignmentFlag.AlignLeft,
            "Notes",
        )

        # Body text.
        body_font = QFont("Segoe UI", max(8, self.height() // 14))
        p.setFont(body_font)
        p.setPen(QColor("#3f2e0a"))
        text = self._answer or "Tap to add a note\u2026"
        p.drawText(
            self.rect().adjusted(8, 24, -8, -8),
            int(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap
            ),
            text,
        )
