"""Embedded ChatGPT browser tab driven by JavaScript injection.

Uses :class:`PyQt6.QtWebEngineWidgets.QWebEngineView` with a *persistent*
profile so the user logs in to ChatGPT once and the cookies survive
restarts. From the host side we call into the page via
``page().runJavaScript`` to attach a screenshot, type the question and
read back the assistant's reply.

This is the "ChatGPT via login" mode — no API key required.
"""

from __future__ import annotations

import base64
import json
from importlib import resources
from typing import Optional

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEnginePage,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from .settings_store import ensure_browser_profile_dir


CHATGPT_URL = "https://chatgpt.com/"
PARTIAL_PREFIX = "AURA_PARTIAL:"


def _load_inject_js() -> str:
    """Read the JS bridge file shipped inside the package."""
    return resources.files("desktop_app.resources").joinpath(
        "chatgpt_inject.js"
    ).read_text(encoding="utf-8")


class _BridgePage(QWebEnginePage):
    """QWebEnginePage that re-emits partial JS messages to Python signals."""

    def __init__(self, profile: QWebEngineProfile, parent) -> None:
        super().__init__(profile, parent)
        self._partial_callback = None

    def set_partial_callback(self, cb) -> None:
        self._partial_callback = cb

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Intercept ``console.log("AURA_PARTIAL:" + text)`` from the bridge
        # script and route it to the Python-side partial-response signal.
        if isinstance(message, str) and message.startswith(PARTIAL_PREFIX):
            if self._partial_callback is not None:
                try:
                    self._partial_callback(message[len(PARTIAL_PREFIX):])
                except Exception:
                    pass
            return
        super().javaScriptConsoleMessage(level, message, line_number, source_id)


class ChatGPTBrowser(QWidget):
    """Container widget hosting an embedded ChatGPT session.

    Emits :pyattr:`partial_response` while the model is streaming and
    :pyattr:`final_response` once the assistant message stabilizes.
    """

    partial_response = pyqtSignal(str)
    final_response = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    page_ready_changed = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        profile_dir = ensure_browser_profile_dir()
        # Named profile = persistent (cookies, localStorage, IndexedDB).
        self._profile = QWebEngineProfile("aura-desktop-chatgpt", self)
        self._profile.setPersistentStoragePath(str(profile_dir))
        self._profile.setCachePath(str(profile_dir / "cache"))
        self._profile.setHttpUserAgent(_modern_user_agent())
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )

        self._page = _BridgePage(self._profile, self)
        self._page.set_partial_callback(self._emit_partial)
        s = self._page.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True
        )

        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self._page.loadFinished.connect(self._on_load_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._inject_js = _load_inject_js()
        self._page_ready = False

        self._view.setUrl(QUrl(CHATGPT_URL))

    # ------------------------------------------------------------------ helpers

    def reload(self) -> None:
        self._view.reload()

    def go_home(self) -> None:
        self._view.setUrl(QUrl(CHATGPT_URL))

    def is_ready(self) -> bool:
        return self._page_ready

    # ------------------------------------------------------------------ events

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            self.error_occurred.emit("ChatGPT page failed to load.")
            return
        # Re-inject our bridge after every navigation.
        self._page.runJavaScript(self._inject_js)
        self._page.runJavaScript(
            "Boolean(window.auraIsReady && window.auraIsReady());",
            self._update_ready,
        )

    def _update_ready(self, value: object) -> None:
        ready = bool(value)
        if ready != self._page_ready:
            self._page_ready = ready
            self.page_ready_changed.emit(ready)

    # ------------------------------------------------------------------ public

    def _emit_partial(self, text: str) -> None:
        """Forward intercepted JS partials to the public Qt signal."""
        if text:
            self.partial_response.emit(text)

    def send_screenshot(
        self,
        png_bytes: bytes,
        question: str,
    ) -> None:
        """Send a screenshot + question to ChatGPT.

        Streaming partials are emitted on :pyattr:`partial_response`;
        the final answer arrives on :pyattr:`final_response`. Connect
        those signals once at construction time — there is no per-call
        callback parameter (it would leak slots).
        """
        b64 = base64.standard_b64encode(png_bytes).decode("ascii")
        # Escape the question safely for embedding in a JS literal.
        question_literal = json.dumps(question or "")
        b64_literal = json.dumps(b64)

        # Install the partial-response forwarder. ``_BridgePage``
        # intercepts the ``AURA_PARTIAL:`` console messages and emits
        # :pyattr:`partial_response` for us.
        self._page.runJavaScript(
            "window.auraOnPartial = function(t){"
            "  try { console.log('AURA_PARTIAL:' + t); } catch (_) {}"
            "};"
        )

        script = (
            "(async () => {"
            "  try {"
            f"    const r = await window.auraSendScreenshot({b64_literal}, "
            f"{question_literal});"
            "    return { ok: true, text: r };"
            "  } catch (e) {"
            "    return { ok: false, error: String(e && e.message || e) };"
            "  }"
            "})();"
        )
        self._page.runJavaScript(script, self._on_response)

    def _on_response(self, value: object) -> None:
        if not isinstance(value, dict):
            self.error_occurred.emit("Unexpected response from ChatGPT bridge.")
            return
        if value.get("ok"):
            self.final_response.emit(str(value.get("text") or ""))
        else:
            self.error_occurred.emit(
                str(value.get("error") or "ChatGPT bridge error")
            )


def _modern_user_agent() -> str:
    """Use a desktop Chrome-ish UA so ChatGPT serves the regular UI."""
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
