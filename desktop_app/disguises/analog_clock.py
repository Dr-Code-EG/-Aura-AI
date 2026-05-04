"""Analog clock disguise — the classic Dr Code surface."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ..clock_widget import ClockWidget
from ._base import DisguiseWidget


class AnalogClockDisguise(DisguiseWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._clock = ClockWidget(self)
        self._clock.clicked.connect(self.clicked.emit)
        # The clock owns its own context-menu policy + size hints, so
        # we just embed it. Forward right-click events to *this*
        # widget so the overlay's context-menu plumbing sees them.
        self._clock.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self._clock)
