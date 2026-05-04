"""First-launch activation dialog.

Shown by ``app.main`` before the clock window appears. Blocks the
event loop until either:

* the user enters a valid activation code (``QDialog.Accepted``)
* the device gets blocked / the user closes the dialog
  (``QDialog.Rejected``) — in that case ``main`` exits.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .firebase.activation import ActivationResult, ActivationService
from .firebase.config import MAX_BAD_ATTEMPTS


_HUMAN_ERRORS = {
    ActivationResult.INVALID_CODE: (
        "That activation code does not exist. Please double-check it."
    ),
    ActivationResult.REVOKED: (
        "This activation code has been revoked. Contact the "
        "administrator to receive a new one."
    ),
    ActivationResult.USED_BY_OTHER_DEVICE: (
        "This activation code is already in use on a different device. "
        "Each code is locked to one device."
    ),
    ActivationResult.NETWORK: (
        "Could not reach the activation server. Please check your "
        "internet connection and try again."
    ),
}


class ActivationDialog(QDialog):
    def __init__(self, service: ActivationService) -> None:
        super().__init__()
        self.setWindowTitle("Dr Code — Activation")
        self.setModal(True)
        self.resize(480, 240)
        self._service = service

        layout = QVBoxLayout(self)

        title = QLabel("Activate your copy of Dr Code")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(14)
        title.setFont(title_font)
        layout.addWidget(title)

        msg = QLabel(
            "Enter your activation code below. Each code is locked to "
            "the first device it is used on."
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self._input = QLineEdit()
        self._input.setPlaceholderText("DRCD-XXXX-XXXX-XXXX")
        self._input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._input.setMaxLength(32)
        layout.addWidget(self._input)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #b00020;")
        layout.addWidget(self._status)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._cancel_btn = QPushButton("Quit")
        self._cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self._cancel_btn)
        self._activate_btn = QPushButton("Activate")
        self._activate_btn.setDefault(True)
        self._activate_btn.clicked.connect(self._on_activate)
        button_row.addWidget(self._activate_btn)
        layout.addLayout(button_row)

    def _on_activate(self) -> None:
        raw = self._input.text().strip()
        if not raw:
            self._status.setText("Please enter an activation code.")
            return

        self._activate_btn.setEnabled(False)
        self._activate_btn.setText("Checking…")
        self._status.setText("")

        result = self._service.try_activate(raw)

        self._activate_btn.setEnabled(True)
        self._activate_btn.setText("Activate")

        if result == ActivationResult.OK:
            self.accept()
            return

        if result == ActivationResult.DEVICE_BLOCKED:
            QMessageBox.critical(
                self,
                "Device blocked",
                (
                    f"Too many invalid attempts ({MAX_BAD_ATTEMPTS}). "
                    "This device is now permanently blocked. Contact "
                    "the administrator to unblock it."
                ),
            )
            self.reject()
            return

        remaining = max(
            MAX_BAD_ATTEMPTS - self._service.state.bad_attempts, 0
        )
        msg = _HUMAN_ERRORS.get(result, "Activation failed.")
        if result != ActivationResult.NETWORK and remaining > 0:
            msg += f"  ({remaining} attempt(s) left.)"
        self._status.setText(msg)
