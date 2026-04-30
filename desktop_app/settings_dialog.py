"""Settings dialog — one screen instead of editing a JSON file."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
)

from .settings_store import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Dr Code — Settings")
        self.setModal(True)
        self.resize(520, 420)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "<b>How Dr Code works:</b><br>"
                "Press the <i>Answer</i> button (or your hotkey) and the "
                "app captures your screen, sends it to the embedded ChatGPT "
                "browser below, and shows the answer inline."
            )
        )

        form = QFormLayout()

        self._hotkey = QLineEdit(settings.hotkey)
        self._hotkey.setPlaceholderText("ctrl+shift+a")
        form.addRow("Global hotkey:", self._hotkey)

        self._delay = QSpinBox()
        self._delay.setRange(0, 5000)
        self._delay.setSuffix(" ms")
        self._delay.setValue(settings.capture_delay_ms)
        form.addRow("Hide-window delay before capture:", self._delay)

        self._auto_hide = QCheckBox(
            "Auto-hide this window before taking the screenshot"
        )
        self._auto_hide.setChecked(settings.auto_hide_window)
        form.addRow("", self._auto_hide)

        layout.addLayout(form)

        layout.addWidget(QLabel("Default question / instructions:"))
        self._question = QPlainTextEdit(settings.extra_question)
        self._question.setMinimumHeight(90)
        layout.addWidget(self._question)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

    def updated_settings(self) -> Settings:
        return Settings(
            hotkey=self._hotkey.text().strip() or "ctrl+shift+a",
            extra_question=self._question.toPlainText().strip(),
            auto_hide_window=self._auto_hide.isChecked(),
            capture_delay_ms=int(self._delay.value()),
        )
