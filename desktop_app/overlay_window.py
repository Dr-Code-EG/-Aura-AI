"""Main floating window — disguised as an analog desk clock.

The whole user-facing surface is the clock. The embedded ChatGPT
browser still does the heavy lifting in the background but is never
visible to anyone looking over the user's shoulder. Clicking the
clock face captures the screen and asks ChatGPT to answer. The
result is shown in the window's title bar text — i.e. *replacing*
what would normally be the app's name — so the user can read it at
a glance without anything that looks like a chat panel popping up.

A right-click on the clock exposes the rest of the controls
(settings, ChatGPT login, pin, quit) under clock-themed labels so
the surface stays minimal.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QSize, QPoint
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .capture import capture_primary_screen
from .chatgpt_browser import ChatGPTBrowser
from .clock_widget import ClockWidget
from .settings_dialog import SettingsDialog
from .settings_store import Settings


# How many characters of the answer fit in the title bar before we
# start ellipsising. Most desktop title bars cut off well before
# this, but we leave the full text in place so the user can hover or
# resize and see more.
_TITLE_MAX = 240


class OverlayWindow(QMainWindow):
    """Always-on-top clock surface."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._chatgpt_in_flight = False
        self._chatgpt_watchdog: Optional[QTimer] = None
        # Set as soon as the clock is clicked, cleared once the
        # actual capture starts. Closes the re-entry window between
        # the in-flight check and the deferred QTimer fire.
        self._capture_pending = False
        # When the user wants to log in to ChatGPT they swap the
        # central widget from the clock to the embedded browser via
        # the right-click menu. We keep both alive and just toggle
        # which is shown.
        self._showing_browser = False

        self.setWindowTitle("Clock")
        self.resize(QSize(360, 380))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._build_ui()
        self._wire_shortcuts()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        # The central widget is a stack: page 0 is the clock face, and
        # page 1 is the embedded ChatGPT browser used only for the
        # initial sign-in. By default we only ever show page 0.
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, stretch=1)

        # Page 0 — the clock.
        clock_page = QWidget()
        clock_layout = QHBoxLayout(clock_page)
        clock_layout.setContentsMargins(0, 0, 0, 0)
        self._clock = ClockWidget(self)
        self._clock.clicked.connect(self.trigger_answer)
        # Right-click on the clock opens the hidden control menu.
        self._clock.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._clock.customContextMenuRequested.connect(self._show_clock_menu)
        clock_layout.addStretch(1)
        clock_layout.addWidget(self._clock)
        clock_layout.addStretch(1)
        self._stack.addWidget(clock_page)

        # Page 1 — the embedded ChatGPT browser. Created once so its
        # cookies / login session persist across page swaps. Never
        # shown unless the user explicitly chooses "Sign in" from
        # the clock menu.
        self._chatgpt = ChatGPTBrowser()
        self._chatgpt.partial_response.connect(self._show_partial_response)
        self._chatgpt.final_response.connect(self._show_final_response)
        self._chatgpt.error_occurred.connect(self._on_chatgpt_error)
        self._chatgpt.page_ready_changed.connect(self._on_chatgpt_ready)
        self._stack.addWidget(self._chatgpt)

        self._stack.setCurrentIndex(0)

    def _wire_shortcuts(self) -> None:
        # Local shortcut still works (the global hotkey is registered
        # in app.py). No visible button advertises it, of course.
        QShortcut(QKeySequence("Ctrl+Shift+A"), self,
                  activated=self.trigger_answer)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.open_settings)
        # Quick-toggle between the clock face and the hidden ChatGPT
        # browser, in case the right-click menu is somehow blocked.
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._toggle_browser)

    # ------------------------------------------------------------------ menu
    def _show_clock_menu(self, point: QPoint) -> None:
        menu = QMenu(self)

        sign_in = QAction(
            "Hide clock face" if self._showing_browser else "Sign in",
            self,
        )
        sign_in.triggered.connect(self._toggle_browser)
        menu.addAction(sign_in)

        calibrate = QAction("Calibrate\u2026", self)
        calibrate.triggered.connect(self.open_settings)
        menu.addAction(calibrate)

        pin = QAction("Pin on top", self, checkable=True)
        pin.setChecked(
            bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        )
        pin.triggered.connect(self._toggle_always_on_top)
        menu.addAction(pin)

        menu.addSeparator()
        quit_act = QAction("Stop clock", self)
        quit_act.triggered.connect(self.close)
        menu.addAction(quit_act)

        menu.exec(self._clock.mapToGlobal(point))

    def _toggle_browser(self) -> None:
        self._showing_browser = not self._showing_browser
        self._stack.setCurrentIndex(1 if self._showing_browser else 0)
        # Resize the window for whichever page is visible. The clock
        # is small and squarish; the browser needs a real chunk of
        # space.
        if self._showing_browser:
            self.resize(900, 600)
        else:
            self.resize(360, 380)

    # ------------------------------------------------------------------ slots
    def _toggle_always_on_top(self) -> None:
        flag = Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlag(flag, not bool(self.windowFlags() & flag))
        self.show()

    def _on_chatgpt_ready(self, ready: bool) -> None:
        # We don't surface this in the UI on purpose — the clock is
        # the only thing the user (or anyone behind them) should see.
        pass

    def open_settings(self) -> None:
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self._settings = dlg.updated_settings()
            self._settings.save()
            if hasattr(self, "settings_changed_callback") and callable(
                self.settings_changed_callback
            ):
                self.settings_changed_callback(self._settings)  # type: ignore[misc]

    def settings(self) -> Settings:
        return self._settings

    # ------------------------------------------------------------------ core
    def trigger_answer(self) -> None:
        """Capture the screen and ask ChatGPT to answer it."""
        if self._is_request_in_flight():
            self._set_title_status("Working\u2026")
            return

        self._capture_pending = True
        self._set_title_status("Thinking\u2026")

        if self._settings.auto_hide_window:
            self.showMinimized()

        QTimer.singleShot(
            max(50, int(self._settings.capture_delay_ms)),
            self._capture_and_send,
        )

    def _capture_and_send(self) -> None:
        self._capture_pending = False
        try:
            shot = capture_primary_screen()
        except Exception as exc:
            self._restore_window()
            self._set_title_status(f"Error: {exc}")
            return

        self._restore_window()

        self._set_title_status("Sending\u2026")
        self._chatgpt_in_flight = True
        self._start_chatgpt_watchdog()
        self._chatgpt.send_screenshot(
            shot.png_bytes,
            self._settings.extra_question or "Answer the question on screen.",
        )

    def _start_chatgpt_watchdog(self) -> None:
        """Recover if ChatGPT never calls back after a request."""
        self._stop_chatgpt_watchdog()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(180_000)  # 3 minutes
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
        self._set_title_status("Timed out \u2014 try again.")

    def _is_request_in_flight(self) -> bool:
        return self._capture_pending or self._chatgpt_in_flight

    # ------------------------------------------------------------------ result
    def _restore_window(self) -> None:
        if self.isMinimized() or not self.isVisible():
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _set_title_status(self, text: str) -> None:
        """Show a short status / answer in place of the window title."""
        clean = " ".join(text.split())  # collapse whitespace
        if len(clean) > _TITLE_MAX:
            clean = clean[: _TITLE_MAX - 1] + "\u2026"
        self.setWindowTitle(clean or "Clock")

    def _show_partial_response(self, text: str) -> None:
        if not text:
            return
        self._set_title_status(text)

    def _show_final_response(self, text: str) -> None:
        self._capture_pending = False
        self._chatgpt_in_flight = False
        self._stop_chatgpt_watchdog()
        self._set_title_status(text or "(empty)")

    def _on_chatgpt_error(self, message: str) -> None:
        if self._chatgpt_in_flight:
            self._capture_pending = False
            self._chatgpt_in_flight = False
            self._stop_chatgpt_watchdog()
            # Keep the surface looking innocuous — no popups, just a
            # short note in the title bar that fades into the next
            # successful answer.
            self._set_title_status(f"Try again ({message})")
        # Ambient errors get swallowed silently so the disguise holds.
