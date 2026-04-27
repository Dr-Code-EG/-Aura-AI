"""Cross-platform global hotkey listener.

Built on top of ``pynput`` because it works on Windows, macOS and Linux
without elevated privileges. The listener runs on its own daemon thread
and re-emits to the Qt main thread via a callback that should be
``QMetaObject.invokeMethod``-safe (i.e. emit a Qt signal).
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

try:
    from pynput import keyboard
except ImportError:  # pragma: no cover - import-time guard
    keyboard = None  # type: ignore[assignment]


class GlobalHotkey:
    """Register a single global hotkey, e.g. ``ctrl+shift+a``."""

    def __init__(self, combo: str, on_activate: Callable[[], None]) -> None:
        self._combo = _normalize(combo)
        self._on_activate = on_activate
        self._listener: Optional["keyboard.GlobalHotKeys"] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if keyboard is None:
            return
        with self._lock:
            self.stop()
            try:
                self._listener = keyboard.GlobalHotKeys(
                    {self._combo: self._on_activate}
                )
                self._listener.daemon = True
                self._listener.start()
            except Exception as exc:  # pragma: no cover - platform specific
                print(f"[aura-desktop] failed to register hotkey {self._combo}: {exc}")
                self._listener = None

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None


def _normalize(combo: str) -> str:
    """Convert ``ctrl+shift+a`` → ``<ctrl>+<shift>+a`` for pynput."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    out = []
    for p in parts:
        if p in {"ctrl", "alt", "shift", "cmd", "win", "super"}:
            out.append(f"<{p}>")
        elif len(p) == 1:
            out.append(p)
        else:
            out.append(f"<{p}>")
    return "+".join(out)
