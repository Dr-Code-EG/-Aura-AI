"""Floating control window — the main UI of Aura Desktop.

Always-on-top, frameless on request, with three tabs:

* **Answer** — the big "📸 Answer the question" button + the response area.
* **ChatGPT** — embedded ChatGPT browser tab (log in once, stay logged in).
* **Settings** — provider configuration.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QStyle,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .capture import capture_primary_screen
from .chatgpt_browser import ChatGPTBrowser
from .settings_dialog import SettingsDialog
from .settings_store import Settings
from .worker import run_gemini_async


class OverlayWindow(QMainWindow):
    """Always-on-top floating control window."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._gemini_thread = None  # keep refs alive while running
        self._gemini_worker = None
        self._chatgpt_in_flight = False
        self._chatgpt_watchdog: Optional[QTimer] = None
        # Set as soon as trigger_answer accepts a request, cleared when
        # _capture_and_send actually starts. Closes the re-entry window
        # between the in-flight check and the deferred QTimer fire.
        self._capture_pending = False

        self.setWindowTitle("Aura Desktop")
        self.resize(QSize(820, 560))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._build_ui()
        self._wire_shortcuts()
        self._apply_settings_to_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(8, 8, 8, 8)

        toolbar = QToolBar("main", self)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        style = self.style()
        self._answer_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogYesButton),
            "📸 Answer (Ctrl+Shift+A)",
            self,
        )
        self._answer_action.triggered.connect(self.trigger_answer)
        toolbar.addAction(self._answer_action)

        toolbar.addSeparator()
        self._provider_box = QComboBox(self)
        self._provider_box.addItem("Gemini", userData="gemini")
        self._provider_box.addItem("ChatGPT (login)", userData="chatgpt")
        self._provider_box.currentIndexChanged.connect(self._on_provider_change)
        toolbar.addWidget(QLabel(" Provider: "))
        toolbar.addWidget(self._provider_box)

        toolbar.addSeparator()
        settings_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "Settings",
            self,
        )
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

        pin_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_TitleBarShadeButton),
            "Toggle Always-on-Top",
            self,
        )
        pin_action.triggered.connect(self._toggle_always_on_top)
        toolbar.addAction(pin_action)

        # Tabs
        self._tabs = QTabWidget(self)
        outer.addWidget(self._tabs)

        # Tab 1 — Answer
        answer_tab = QWidget()
        answer_layout = QVBoxLayout(answer_tab)

        big_button_row = QHBoxLayout()
        self._answer_button = QPushButton("📸  Answer the question")
        self._answer_button.setMinimumHeight(56)
        self._answer_button.setStyleSheet(
            "QPushButton { font-size: 18px; font-weight: 600; }"
        )
        self._answer_button.clicked.connect(self.trigger_answer)
        big_button_row.addWidget(self._answer_button)
        answer_layout.addLayout(big_button_row)

        answer_layout.addWidget(QLabel("Response:"))
        self._response_view = QPlainTextEdit()
        self._response_view.setReadOnly(True)
        self._response_view.setPlaceholderText(
            "Click the button (or press your hotkey) while your exam question "
            "is on screen — the answer will appear here."
        )
        answer_layout.addWidget(self._response_view, stretch=1)

        self._tabs.addTab(answer_tab, "Answer")

        # Tab 2 — ChatGPT browser
        self._chatgpt = ChatGPTBrowser()
        self._chatgpt.partial_response.connect(self._show_partial_response)
        self._chatgpt.final_response.connect(self._show_final_response)
        self._chatgpt.error_occurred.connect(self._show_error)
        self._chatgpt.page_ready_changed.connect(self._on_chatgpt_ready)
        self._tabs.addTab(self._chatgpt, "ChatGPT login")

        # Status bar
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        self._status_label = QLabel("Ready.")
        sb.addWidget(self._status_label)

    def _wire_shortcuts(self) -> None:
        # Local (window-focus) shortcut. The cross-app global hotkey is
        # registered separately in app.py via pynput.
        QShortcut(QKeySequence("Ctrl+Shift+A"), self, activated=self.trigger_answer)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.open_settings)

    def _apply_settings_to_ui(self) -> None:
        idx = 1 if self._settings.default_provider == "chatgpt" else 0
        self._provider_box.setCurrentIndex(idx)

    # ------------------------------------------------------------------ slots
    def _toggle_always_on_top(self) -> None:
        flag = Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlag(flag, not bool(self.windowFlags() & flag))
        self.show()

    def _on_provider_change(self) -> None:
        provider = self._provider_box.currentData() or "gemini"
        self._settings.default_provider = provider
        self._settings.save()
        self._status_label.setText(f"Provider: {provider}")

    def _on_chatgpt_ready(self, ready: bool) -> None:
        if ready:
            self._status_label.setText(
                "ChatGPT logged in — ready to send screenshots."
            )
        else:
            self._status_label.setText(
                "ChatGPT not signed in — open the ChatGPT login tab and log in."
            )

    def open_settings(self) -> None:
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self._settings = dlg.updated_settings()
            self._settings.save()
            self._apply_settings_to_ui()
            self._status_label.setText("Settings saved.")
            # Notify the application that the hotkey may have changed.
            if hasattr(self, "settings_changed_callback") and callable(
                self.settings_changed_callback
            ):
                self.settings_changed_callback(self._settings)  # type: ignore[misc]

    def settings(self) -> Settings:
        return self._settings

    # ------------------------------------------------------------------ core
    def trigger_answer(self) -> None:
        """Called by the toolbar button, the local shortcut, and the global hotkey."""
        # Guard against re-entry: a Gemini request in flight must finish
        # before we kick off another one. Otherwise the QThread reference
        # gets overwritten and the still-running thread is destroyed by GC,
        # which crashes Qt.
        if self._is_request_in_flight():
            self._status_label.setText(
                "Still working on the previous question — please wait."
            )
            return

        # Mark immediately — the actual capture is deferred via
        # QTimer.singleShot below, and the global hotkey can re-enter
        # during that delay.
        self._capture_pending = True

        provider = self._provider_box.currentData() or "gemini"
        self._response_view.setPlainText("")
        self._status_label.setText("Capturing screen…")
        self._set_answer_controls_enabled(False)

        if self._settings.auto_hide_window:
            self.showMinimized()

        QTimer.singleShot(
            max(50, int(self._settings.capture_delay_ms)),
            lambda: self._capture_and_send(provider),
        )

    def _capture_and_send(self, provider: str) -> None:
        # The real request is starting now; release the pre-fire guard.
        # Either the gemini thread or _chatgpt_in_flight will take over
        # tracking from here.
        self._capture_pending = False
        try:
            shot = capture_primary_screen()
        except Exception as exc:
            self._restore_window()
            self._show_error(f"Screen capture failed: {exc}")
            return

        # Always restore visibility so the user can read the response.
        self._restore_window()

        if provider == "chatgpt":
            if not self._chatgpt.is_ready():
                self._tabs.setCurrentWidget(self._chatgpt)
                self._show_error(
                    "ChatGPT isn't ready yet. Log in via the ChatGPT tab and try "
                    "again."
                )
                return
            self._status_label.setText("Sending screenshot to ChatGPT…")
            self._chatgpt_in_flight = True
            self._start_chatgpt_watchdog()
            self._chatgpt.send_screenshot(
                shot.png_bytes,
                self._settings.extra_question or "Answer the question on screen.",
            )
        else:
            self._send_to_gemini(shot.png_bytes)

    def _start_chatgpt_watchdog(self) -> None:
        """Re-enable the answer controls if ChatGPT never calls back.

        The injected JS bridge is supposed to emit ``final_response`` or
        ``error_occurred`` for every screenshot we send. If the page
        crashes, navigates away, or OpenAI changes their DOM, neither
        signal fires and the user would be stuck with disabled controls.
        This watchdog forces a recovery after a generous timeout.
        """
        self._stop_chatgpt_watchdog()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(180_000)  # 3 minutes — generous for slow models
        timer.timeout.connect(self._on_chatgpt_watchdog_fired)
        timer.start()
        self._chatgpt_watchdog = timer

    def _stop_chatgpt_watchdog(self) -> None:
        timer = self._chatgpt_watchdog
        if timer is None:
            return
        try:
            timer.stop()
        except RuntimeError:
            pass
        self._chatgpt_watchdog = None

    def _on_chatgpt_watchdog_fired(self) -> None:
        if not self._chatgpt_in_flight:
            return
        self._chatgpt_in_flight = False
        self._stop_chatgpt_watchdog()
        self._set_answer_controls_enabled(True)
        self._status_label.setText(
            "ChatGPT didn't respond \u2014 try again or reload the ChatGPT tab."
        )

    def _is_request_in_flight(self) -> bool:
        if self._capture_pending:
            return True
        """True while a Gemini QThread is still running OR a ChatGPT bridge call is pending."""
        if self._chatgpt_in_flight:
            return True
        thread = self._gemini_thread
        if thread is None:
            return False
        try:
            return bool(thread.isRunning())
        except RuntimeError:
            # Underlying C++ object already deleted.
            return False

    def _set_answer_controls_enabled(self, enabled: bool) -> None:
        """Toggle the Answer button + toolbar action together."""
        self._answer_button.setEnabled(enabled)
        self._answer_action.setEnabled(enabled)

    def _send_to_gemini(self, png_bytes: bytes) -> None:
        if not self._settings.gemini_api_key:
            self._show_error(
                "No Gemini API key configured. Open Settings (Ctrl+,) to add one."
            )
            return
        self._status_label.setText(
            f"Asking Gemini ({self._settings.gemini_model})…"
        )

        thread, worker = run_gemini_async(
            api_key=self._settings.gemini_api_key,
            model=self._settings.gemini_model,
            png_bytes=png_bytes,
            question=self._settings.extra_question
            or "Answer the question on the screen.",
            on_done=self._show_final_response,
            on_error=self._show_error,
            system_instruction=(
                "You are an expert tutor helping a user answer the question "
                "shown in the attached screenshot. Be precise. If multiple "
                "choice, give the answer letter and a 1-2 line justification."
            ),
        )
        # keep refs alive so they aren't garbage-collected mid-flight
        self._gemini_thread = thread
        self._gemini_worker = worker

    # ------------------------------------------------------------------ result
    def _restore_window(self) -> None:
        if self.isMinimized() or not self.isVisible():
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _show_partial_response(self, text: str) -> None:
        if not text:
            return
        self._response_view.setPlainText(text)
        self._status_label.setText("Streaming…")

    def _show_final_response(self, text: str) -> None:
        self._capture_pending = False
        self._response_view.setPlainText(text or "(empty response)")
        self._status_label.setText("Done.")
        self._set_answer_controls_enabled(True)
        self._chatgpt_in_flight = False
        self._stop_chatgpt_watchdog()
        self._cleanup_gemini_thread()

    def _show_error(self, message: str) -> None:
        self._capture_pending = False
        self._set_answer_controls_enabled(True)
        self._status_label.setText("Error.")
        self._chatgpt_in_flight = False
        self._stop_chatgpt_watchdog()
        self._cleanup_gemini_thread()
        QMessageBox.warning(self, "Aura Desktop", message)

    def _cleanup_gemini_thread(self) -> None:
        """Drop the stored thread reference once the request has finished."""
        thread = self._gemini_thread
        if thread is None:
            return
        try:
            if thread.isRunning():
                # Don't drop a still-running thread; let it finish and call
                # us again via final/error.
                return
        except RuntimeError:
            pass
        self._gemini_thread = None
        self._gemini_worker = None
