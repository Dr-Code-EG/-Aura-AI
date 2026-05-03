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
    QMainWindow,
    QMenu,
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
        # The ChatGPT browser stays mounted in the same window all
        # the time so its JS bridge keeps running. We just toggle the
        # bottom splitter pane between "very tall" and "1 px" so the
        # user only sees the clock unless they opt in.
        self._showing_browser = False

        self.setWindowTitle("Clock")
        self.resize(QSize(360, 380))
        # Window itself can shrink to a small clock-only size.
        self.setMinimumSize(80, 80)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._build_ui()
        self._wire_shortcuts()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        # The main window only ever shows the clock. The ChatGPT
        # browser lives in a separate top-level Qt::Tool window that
        # is *always* visible at full 800x600 size, just positioned
        # off-screen by default. That way Chromium renders chatgpt.com
        # at a real viewport (the editor element is in the DOM, the
        # JS bridge can find it) and the user never sees the browser
        # unless they explicitly bring it on-screen via the right-
        # click menu.
        from PyQt6.QtWidgets import QSizePolicy

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        self._clock = ClockWidget(self)
        self._clock.clicked.connect(self.trigger_answer)
        self._clock.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._clock.customContextMenuRequested.connect(self._show_clock_menu)
        self._clock.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._clock, 1)

        # --- ChatGPT browser in its own offscreen window -----------
        self._chatgpt_window = QWidget()
        # Tool window: no taskbar entry, no Alt-Tab presence — keeps
        # the disguise even though the window technically exists.
        self._chatgpt_window.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
        )
        self._chatgpt_window.setWindowTitle("ChatGPT")
        chatgpt_layout = QVBoxLayout(self._chatgpt_window)
        chatgpt_layout.setContentsMargins(0, 0, 0, 0)

        self._chatgpt = ChatGPTBrowser()
        self._chatgpt.partial_response.connect(self._show_partial_response)
        self._chatgpt.final_response.connect(self._show_final_response)
        self._chatgpt.error_occurred.connect(self._on_chatgpt_error)
        self._chatgpt.page_ready_changed.connect(self._on_chatgpt_ready)
        chatgpt_layout.addWidget(self._chatgpt, 1)

        # Real, full-sized viewport so chatgpt.com lays itself out
        # the way the inject script expects.
        self._chatgpt_window.resize(QSize(900, 700))

        # Default: parked off-screen so the user only sees the clock.
        self._chatgpt_window.move(-30000, -30000)
        # Always visible to Qt — that's what keeps Chromium from
        # throttling / suspending the page.
        self._chatgpt_window.show()

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

        # Toggle the bottom ChatGPT panel. The browser is always
        # mounted; this just expands or collapses its splitter pane.
        toggle_label = (
            "Hide ChatGPT panel"
            if self._showing_browser
            else "Show ChatGPT panel"
        )
        toggle = QAction(toggle_label, self)
        toggle.triggered.connect(self._toggle_browser)
        menu.addAction(toggle)

        # Same as Show panel, but explicit — the very first time you
        # need to log in.
        if not self._showing_browser:
            sign_in = QAction("Sign in to ChatGPT", self)
            sign_in.triggered.connect(
                lambda: self._set_browser_panel_visible(True)
            )
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

    def closeEvent(self, event) -> None:  # noqa: N802
        # The ChatGPT browser is a separate top-level window; close it
        # too so the app actually exits when the clock is closed.
        try:
            self._chatgpt_window.close()
        except Exception:
            pass
        super().closeEvent(event)

    def _toggle_browser(self) -> None:
        self._set_browser_panel_visible(not self._showing_browser)

    def _set_browser_panel_visible(self, visible: bool) -> None:
        self._showing_browser = visible
        # Toggle frameless/Tool window decorations so it picks up a
        # title bar when visible (so the user can move/close it) and
        # is back to invisible-in-the-corner when hidden.
        flags = (
            Qt.WindowType.Tool
            if visible
            else Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        )
        was_visible = self._chatgpt_window.isVisible()
        self._chatgpt_window.setWindowFlags(flags)
        if visible:
            # Park the ChatGPT window directly below the clock at a
            # readable size.
            geom = self.geometry()
            self._chatgpt_window.resize(900, 700)
            self._chatgpt_window.move(geom.x(), geom.y() + geom.height() + 8)
        else:
            # Send it back off-screen. Stays "shown" to Qt so the JS
            # bridge keeps running and the page never hits the
            # visibility-hidden lifecycle.
            self._chatgpt_window.move(-30000, -30000)
        # setWindowFlags() implicitly hides the window on some
        # platforms; we MUST keep it shown so Chromium doesn't pause
        # the page, otherwise the bridge would stop responding.
        if was_visible or True:
            self._chatgpt_window.show()

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
