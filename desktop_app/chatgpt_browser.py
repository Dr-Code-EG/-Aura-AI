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
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEnginePage,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .settings_store import ensure_browser_profile_dir


CHATGPT_URL = "https://chatgpt.com/"
PARTIAL_PREFIX = "DRCODE_PARTIAL:"


def _load_inject_js() -> str:
    """Read the JS bridge file shipped inside the package."""
    return resources.files("desktop_app.resources").joinpath(
        "chatgpt_inject.js"
    ).read_text(encoding="utf-8")


class _BridgePage(QWebEnginePage):
    """QWebEnginePage that supports popups + re-emits partial JS messages."""

    def __init__(self, profile: QWebEngineProfile, parent) -> None:
        super().__init__(profile, parent)
        self._partial_callback = None
        self._popup_factory = None

    def set_partial_callback(self, cb) -> None:
        self._partial_callback = cb

    def set_popup_factory(self, factory) -> None:
        """Function called when the page wants to open a new window.

        Receives the requested ``QWebEnginePage.WebWindowType`` and must
        return a :class:`QWebEnginePage` whose view is already shown so
        Chromium can navigate it (used for OAuth login popups, etc).
        """
        self._popup_factory = factory

    def createWindow(self, window_type):
        # Login flows (Google/Microsoft sign-in, OpenAI's auth popup) call
        # ``window.open`` and need a real popup page to navigate into.
        if self._popup_factory is not None:
            try:
                return self._popup_factory(window_type)
            except Exception:
                return None
        return None

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Intercept ``console.log("DRCODE_PARTIAL:" + text)`` from the bridge
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
        self._profile = QWebEngineProfile("drcode-chatgpt", self)
        self._profile.setPersistentStoragePath(str(profile_dir))
        self._profile.setCachePath(str(profile_dir / "cache"))
        self._profile.setHttpUserAgent(_modern_user_agent())
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )

        self._page = _BridgePage(self._profile, self)
        self._page.set_partial_callback(self._emit_partial)
        self._page.set_popup_factory(self._spawn_popup)
        s = self._page.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True
        )
        # Allow the page itself to call ``window.open`` for OAuth popups.
        s.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True
        )
        s.setAttribute(
            QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False
        )
        s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)

        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self._page.loadFinished.connect(self._on_load_finished)

        # Toolbar with manual reload + open-in-system-browser fallbacks for
        # cases where the embedded UA is blocked by an identity provider.
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 0)
        toolbar.setSpacing(6)

        reload_btn = QPushButton("\u21bb Reload", self)
        reload_btn.setToolTip("Reload the ChatGPT page.")
        reload_btn.clicked.connect(self.reload)
        toolbar.addWidget(reload_btn)

        home_btn = QPushButton("Home", self)
        home_btn.setToolTip("Go back to chatgpt.com")
        home_btn.clicked.connect(self.go_home)
        toolbar.addWidget(home_btn)

        clear_btn = QPushButton("Clear cookies", self)
        clear_btn.setToolTip(
            "Wipe the saved ChatGPT session and force a fresh login."
        )
        clear_btn.clicked.connect(self.clear_session)
        toolbar.addWidget(clear_btn)

        external_btn = QPushButton("Open in system browser", self)
        external_btn.setToolTip(
            "Open ChatGPT in your real browser if the embedded login "
            "is being blocked. After signing in there, return to this app "
            "and click Reload."
        )
        external_btn.clicked.connect(self._open_in_system_browser)
        toolbar.addWidget(external_btn)

        toolbar.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self._view, 1)

        self._inject_js = _load_inject_js()
        self._page_ready = False
        # Keep references to popup windows so they aren't garbage-collected
        # before Chromium finishes the auth dance inside them.
        self._popups: list[QDialog] = []

        self._view.setUrl(QUrl(CHATGPT_URL))

    # ------------------------------------------------------------------ helpers

    def reload(self) -> None:
        self._view.reload()

    def go_home(self) -> None:
        self._view.setUrl(QUrl(CHATGPT_URL))

    def is_ready(self) -> bool:
        return self._page_ready

    def clear_session(self) -> None:
        """Wipe persisted cookies + reload, forcing a fresh login."""
        try:
            self._profile.cookieStore().deleteAllCookies()
        except Exception:
            pass
        try:
            self._profile.clearAllVisitedLinks()
        except Exception:
            pass
        self.go_home()

    def _open_in_system_browser(self) -> None:
        """Open ChatGPT in the user's real browser as a fallback."""
        QDesktopServices.openUrl(QUrl(CHATGPT_URL))

    def _spawn_popup(self, window_type) -> Optional[QWebEnginePage]:
        """Create a popup window that shares our profile (for OAuth flows)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("ChatGPT sign-in")
        dlg.resize(900, 700)

        page = _BridgePage(self._profile, dlg)
        # Popups can also open further popups (Microsoft device-code, etc).
        page.set_popup_factory(self._spawn_popup)

        view = QWebEngineView(dlg)
        view.setPage(page)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(view)

        # Closing the popup should drop our reference so it gets GC'd.
        def _on_finished(_result: int) -> None:
            try:
                self._popups.remove(dlg)
            except ValueError:
                pass

        dlg.finished.connect(_on_finished)
        # Auth providers usually redirect back to the embedded ChatGPT page
        # and then call ``window.close()`` — listen for that.
        page.windowCloseRequested.connect(dlg.accept)

        self._popups.append(dlg)
        dlg.show()
        return page

    # ------------------------------------------------------------------ events

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            self.error_occurred.emit("ChatGPT page failed to load.")
            return
        # Re-inject our bridge after every navigation.
        self._page.runJavaScript(self._inject_js)
        self._page.runJavaScript(
            "Boolean(window.drcodeIsReady && window.drcodeIsReady());",
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
        # intercepts the ``DRCODE_PARTIAL:`` console messages and emits
        # :pyattr:`partial_response` for us.
        self._page.runJavaScript(
            "window.drcodeOnPartial = function(t){"
            "  try { console.log('DRCODE_PARTIAL:' + t); } catch (_) {}"
            "};"
        )

        script = (
            "(async () => {"
            "  try {"
            "    if (typeof window.drcodeSendScreenshot !== 'function') {"
            "      return { ok: false, error: 'DRCODE_BRIDGE_NOT_LOADED' };"
            "    }"
            f"    const r = await window.drcodeSendScreenshot({b64_literal}, "
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
            return
        err = str(value.get("error") or "ChatGPT bridge error")
        # The injected JS uses this sentinel to signal "the page is on
        # a login URL or the user is signed out" so the host can
        # surface a more helpful message and switch to the ChatGPT tab.
        if "DRCODE_LOGIN_REQUIRED" in err:
            self.error_occurred.emit(
                "Please log in to ChatGPT \u2014 switching to the ChatGPT tab. "
                "After signing in, click the Answer button again."
            )
            return
        if "DRCODE_BRIDGE_NOT_LOADED" in err:
            self.error_occurred.emit(
                "ChatGPT page hasn't finished loading. Open the ChatGPT tab, "
                "wait for the chat UI to appear, then try again."
            )
            return
        self.error_occurred.emit(err)


def _modern_user_agent() -> str:
    """Desktop Chrome UA so ChatGPT serves the regular UI and OAuth
    providers (Google, Microsoft) don't reject the embedded browser as
    "insecure"."""
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
