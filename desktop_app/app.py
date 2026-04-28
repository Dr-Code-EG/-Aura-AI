"""Aura Desktop entry point.

Wires together: QApplication → :class:`OverlayWindow` → global hotkey.
"""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from .hotkey import GlobalHotkey
from .overlay_window import OverlayWindow
from .settings_store import Settings


class _HotkeyBridge(QObject):
    """Marshals callbacks from the pynput thread onto the Qt main thread."""

    triggered = pyqtSignal()


def _set_high_dpi_attributes() -> None:
    # Qt 6 sets these by default; harmless on older Qt.
    for attr in (
        "AA_EnableHighDpiScaling",
        "AA_UseHighDpiPixmaps",
        # Required for QtWebEngine — must be set BEFORE QApplication.
        "AA_ShareOpenGLContexts",
    ):
        flag = getattr(Qt.ApplicationAttribute, attr, None)
        if flag is not None:
            try:
                QApplication.setAttribute(flag, True)
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _set_high_dpi_attributes()

    # Some Linux/WSL environments need Chromium flags for QtWebEngine to
    # render at all. On Windows the defaults are fine, and forcing
    # --disable-gpu-sandbox / UseOzonePlatform off can actively *break*
    # the embedded browser (chatgpt.com renders as a blank page in some
    # frozen PyInstaller builds), so only set the flags on Linux.
    if sys.platform.startswith("linux"):
        os.environ.setdefault(
            "QTWEBENGINE_CHROMIUM_FLAGS",
            "--no-sandbox --disable-gpu-sandbox --disable-features=UseOzonePlatform",
        )

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Aura Desktop")
    app.setOrganizationName("Aura")
    app.setQuitOnLastWindowClosed(True)

    settings = Settings.load()
    window = OverlayWindow(settings)

    bridge = _HotkeyBridge()
    bridge.triggered.connect(window.trigger_answer)

    initial_hotkey = GlobalHotkey(settings.hotkey, bridge.triggered.emit)
    initial_hotkey.start()
    # Mutable single-element holder so settings changes can swap the active
    # listener without leaking the previous one.
    _hotkey_holder: list[GlobalHotkey] = [initial_hotkey]

    def _on_settings_changed(new_settings: Settings) -> None:
        _hotkey_holder[0].stop()
        new_hotkey = GlobalHotkey(new_settings.hotkey, bridge.triggered.emit)
        new_hotkey.start()
        _hotkey_holder[0] = new_hotkey
    window.settings_changed_callback = _on_settings_changed  # type: ignore[attr-defined]

    window.show()

    if not settings.gemini_api_key and settings.default_provider == "gemini":
        QMessageBox.information(
            window,
            "Welcome to Aura Desktop",
            "No Gemini API key is configured yet.\n\n"
            "Open Settings (Ctrl+,) to paste one in, or switch to the "
            "ChatGPT tab and sign in to use the login-based provider.",
        )

    try:
        return app.exec()
    finally:
        _hotkey_holder[0].stop()


if __name__ == "__main__":
    raise SystemExit(main())
