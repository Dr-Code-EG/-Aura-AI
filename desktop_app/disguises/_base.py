"""Shared base for disguise widgets.

Every disguise widget:

* emits :pyattr:`clicked` when single-clicked (so the overlay window
  can trigger a screenshot regardless of disguise)
* honours :meth:`set_answer` to take a freshly-arrived answer string
  and plumb it into whichever surface this particular disguise uses
  (title bar, tooltip, inline label, …)

The actual visual painting / layout lives in each subclass.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QWidget


class DisguiseWidget(QWidget):
    """Base class for every disguise."""

    clicked = pyqtSignal()
    answer_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Disguises render their own background — keep Qt's default
        # backing fill out of the way so transparency works.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    # The overlay calls this every time a new answer arrives. Default
    # behaviour: just re-broadcast through ``answer_changed`` so the
    # overlay can route the text to wherever the registry says (title
    # bar, tooltip, etc). Subclasses that paint the answer inline
    # (digital clock, sticky note, …) override this to also redraw.
    def set_answer(self, text: str) -> None:
        self.answer_changed.emit(text)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
