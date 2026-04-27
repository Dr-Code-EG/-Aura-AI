"""Settings dialog — one screen instead of editing .env / json files."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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


GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aura Desktop — Settings")
        self.setModal(True)
        self.resize(520, 460)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "<b>How Aura Desktop works:</b><br>"
                "Press the <i>Answer</i> button (or your hotkey) and the app "
                "captures your screen, sends it to the selected AI provider, "
                "and shows the answer here. Configure the provider below."
            )
        )

        form = QFormLayout()

        self._provider_box = QComboBox()
        self._provider_box.addItem("Gemini (API key)", userData="gemini")
        self._provider_box.addItem("ChatGPT (login in browser)", userData="chatgpt")
        if settings.default_provider == "chatgpt":
            self._provider_box.setCurrentIndex(1)
        form.addRow("Default provider:", self._provider_box)

        self._gemini_key = QLineEdit(settings.gemini_api_key)
        self._gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._gemini_key.setPlaceholderText("AIza…  (get one at aistudio.google.com)")
        form.addRow("Gemini API key:", self._gemini_key)

        self._gemini_model = QComboBox()
        self._gemini_model.setEditable(True)
        for m in GEMINI_MODELS:
            self._gemini_model.addItem(m)
        self._gemini_model.setCurrentText(settings.gemini_model)
        form.addRow("Gemini model:", self._gemini_model)

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
            gemini_api_key=self._gemini_key.text().strip(),
            gemini_model=self._gemini_model.currentText().strip()
            or "gemini-2.0-flash",
            default_provider=self._provider_box.currentData() or "gemini",
            hotkey=self._hotkey.text().strip() or "ctrl+shift+a",
            extra_question=self._question.toPlainText().strip(),
            auto_hide_window=self._auto_hide.isChecked(),
            capture_delay_ms=int(self._delay.value()),
        )
